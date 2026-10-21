"""The hit log and the hook's printed output. Every hit is one ASCII JSON line in
<root>/build/hooks/tickets/hits.jsonl, which rotates to .1 past LOG_MAX_BYTES. The only thing ever printed is
a UserPromptSubmit additionalContext object or a PreToolUse deny, and only for a rule id in ENFORCE.

A logged sample of a prompt or a command goes through sample_text(): secrets are masked first (redact()),
then the text is cut to a short ASCII excerpt. Masking comes first, so a secret straddling the cut leaves no
fragment behind."""
import json
import math
import os
import re
import sys
import time

from hooklib import paths

LOG_MAX_BYTES = 5 * 1024 * 1024
BREADCRUMB_TAIL_BYTES = 16 * 1024  # how much of the log's end is checked for repeats of a breadcrumb
BREADCRUMB_REPEAT_MAX = 5  # identical breadcrumbs kept in that tail, so a rule raising every call stops growing the log
EXCERPT_MAX = 160
REDACT_SCAN_MAX = 4096  # a sample is at most EXCERPT_MAX long, so only the head of a huge command is scanned
MASK = "***"

# Names whose value is a secret: password, passwd, pwd, passphrase, secret, token, key, auth, authorization,
# credential(s), cookie, session id - alone or ending a longer name (GITHUB_TOKEN, client_secret, api-key,
# -Password, auth_token), never inside a word (author, keyboard, tokens are not secret names).
SECRET_WORD = (r"(?:passw(?:or)?d|pwd|passphrase|secrets?|tokens?|keys?|auth|authorization|credentials?|"
			   r"cookies?|session[_-]?id)")
SECRET_NAME = r"[A-Za-z0-9_.-]*?" + SECRET_WORD + r"(?:[_.-][A-Za-z0-9_.-]*)?(?![A-Za-z0-9])"
VALUE = r"(\"[^\"]*\"?|'[^']*'?|[^\s,;&|\"']+)"
# name=value, name: value, "name": "value", $env:NAME = value (a name starts a run, never mid-word)
ASSIGN_RE = re.compile(r"(?i)((?<![A-Za-z0-9_.-])" + SECRET_NAME + r")([\"']?\s*[:=]\s*)" + VALUE)
# --name value, -Name value (a command-line flag, then its value)
FLAG_RE = re.compile(r"(?i)((?<![A-Za-z0-9_-])--?" + SECRET_NAME + r")(\s+)(?!-)" + VALUE)
# Authorization: Bearer <token> / Basic <b64> / <token>, and a bare Bearer <token>
AUTH_RE = re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?(?:(?:bearer|basic|digest|token)\s+)?)([^\s\"',;]+)")
BEARER_RE = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{8,})")
# scheme://user:password@host
URL_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^/\s@]+)(@)")
# a long run that looks like a key: base64/url-safe characters
CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/_=-]{16,}")
ENTROPY_MIN = 3.2  # bits per character; random keys sit near 4 to 6, words and identifiers lower
MIXED_MIN = 20     # a run with upper, lower and digits this long is a key ...
PART_MEAN_MIN = 10  # ... unless its '/'-parts average under this, as a path's folder names do
HEX_MIN = 32       # a hex run this long is a key or a hash


def ascii_text(s):
	return str(s).encode("ascii", "replace").decode("ascii")


def excerpt(s, limit=EXCERPT_MAX):
	return ascii_text(" ".join(str(s).split())[:limit])


def entropy(s):
	"""Shannon entropy of `s` in bits per character."""
	if not s:
		return 0.0
	counts = {}
	for ch in s:
		counts[ch] = counts.get(ch, 0) + 1
	n = float(len(s))
	return -sum(c / n * math.log(c / n, 2) for c in counts.values())


def mixed(s):
	return any(c.isupper() for c in s) and any(c.islower() for c in s) and any(c.isdigit() for c in s)


def looks_like_key(run):
	"""True for a run that is probably a key or token: long hex, or long, mixed-case with digits and of high
	entropy. A path is told apart by its short '/'-parts (/c/Users/Name/Python313/x is not a key; base64 with
	a '/' in it is)."""
	if len(run) >= HEX_MIN and re.match(r"^[0-9a-fA-F]+$", run) and re.search(r"[0-9]", run) \
			and re.search(r"[a-fA-F]", run):
		return True
	if len(run) < MIXED_MIN or not mixed(run) or entropy(run) < ENTROPY_MIN:
		return False
	parts = [p for p in run.split("/") if p]
	return bool(parts) and sum(len(p) for p in parts) >= PART_MEAN_MIN * len(parts)


def redact(text):
	"""`text` with likely secrets replaced by MASK: values of secret-like names (assignments, JSON keys,
	flags), Bearer/Basic credentials, URL passwords, and long high-entropy runs. Errs on masking more."""
	s = str(text or "")
	s = URL_CRED_RE.sub(lambda m: m.group(1) + MASK + m.group(3), s)
	s = AUTH_RE.sub(lambda m: m.group(1) + MASK, s)
	s = BEARER_RE.sub(lambda m: m.group(1) + MASK, s)
	s = ASSIGN_RE.sub(lambda m: m.group(1) + m.group(2) + MASK, s)
	s = FLAG_RE.sub(lambda m: m.group(1) + m.group(2) + MASK, s)
	return CANDIDATE_RE.sub(lambda m: MASK if looks_like_key(m.group(0)) else m.group(0), s)


def sample_text(s, limit=EXCERPT_MAX):
	"""A logged sample of a prompt or command: secrets masked, whitespace collapsed, cut to `limit`, ASCII."""
	return excerpt(redact(str(s or "")[:REDACT_SCAN_MAX]), limit)


def now_iso():
	return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def append_rows(root, rows):
	"""Append rows to <root>/build/hooks/tickets/hits.jsonl, one ASCII JSON object per line, rotating first. Writes
	nothing inside a release export's payload/ (paths.runtime_allowed())."""
	if not paths.runtime_allowed(root):
		return
	path = paths.hits_path(root)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	try:
		if os.path.getsize(path) > LOG_MAX_BYTES:
			os.replace(path, path + ".1")
	except OSError:
		pass
	with open(path, "a", encoding="ascii", newline="\n") as fh:
		for row in rows:
			fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def breadcrumb_repeats(root, sample, rule="hook-error"):
	try:
		with open(paths.hits_path(root), "rb") as fh:
			fh.seek(0, os.SEEK_END)
			fh.seek(max(0, fh.tell() - BREADCRUMB_TAIL_BYTES))
			tail = fh.read().decode("ascii", "replace")
	except OSError:
		return 0
	needle = json.dumps([sample], ensure_ascii=True)
	marker = '"rule": %s' % json.dumps(rule)
	return sum(1 for line in tail.splitlines() if marker in line and needle in line)


def breadcrumb(root, module, phase, exc, event=None):
	"""One row when a rule module raised and was skipped: module, phase and the exception TYPE, never its
	message. Capped by BREADCRUMB_REPEAT_MAX. Never raises."""
	try:
		name = module if isinstance(module, str) else str(getattr(module, "__name__", None) or type(module).__name__)
		sample = excerpt("%s %s %s" % (name, phase, type(exc).__name__))
		if breadcrumb_repeats(root, sample) >= BREADCRUMB_REPEAT_MAX:
			return
		event = event if isinstance(event, dict) else {}
		append_rows(root, [{"ts": now_iso(), "mode": "error", "rule": "hook-error",
							"event": event.get("hook_event_name"), "sample": [sample],
							"session": event.get("session_id"), "ms": 0,
							"msg": "a rule module raised and was skipped; its findings for this call are lost"}])
	except Exception:
		pass


def note(root, rule, key, why, event=None):
	"""One row when a rule ignored a config value: the rule id, the config key and why, never the value.
	Capped like a breadcrumb. Never raises."""
	try:
		sample = excerpt("%s %s %s" % (rule, key, why))
		if breadcrumb_repeats(root, sample, "hook-config") >= BREADCRUMB_REPEAT_MAX:
			return
		event = event if isinstance(event, dict) else {}
		append_rows(root, [{"ts": now_iso(), "mode": "error", "rule": "hook-config",
							"event": event.get("hook_event_name"), "sample": [sample],
							"session": event.get("session_id"), "ms": 0,
							"msg": "a .claude/tickets/config.json value was ignored and the fallback used"}])
	except Exception:
		pass


def prompt_context(texts):
	"""One UserPromptSubmit output adding every text as context, or None if there are none. Never a block."""
	texts = [t for t in texts if t]
	if not texts:
		return None
	return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(texts)}}


def deny(reasons):
	"""One PreToolUse deny joining every reason, or None if there are none."""
	reasons = [r for r in reasons if r]
	if not reasons:
		return None
	return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
								   "permissionDecisionReason": ascii_text(" | ".join(reasons))}}


def print_json(obj):
	sys.stdout.write(json.dumps(obj, ensure_ascii=True))
	sys.stdout.flush()
