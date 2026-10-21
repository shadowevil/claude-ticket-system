"""Where things live: the project root, and the gitignored runtime directory build/hooks/tickets/ that holds the
hit log and the prompt clock. Reads the environment only; creates nothing (a writer creates the runtime
directory when it first writes), except inside the payload/ of a release export the package runs from
(runtime_allowed()).

Everything of the ticket-system hooks is namespaced: the code in .claude/hooks/tickets/ (so it never collides
with a project's own .claude/hooks/), the runtime files in build/hooks/tickets/.

The root is never hard-coded: CLAUDE_PROJECT_DIR from the hook environment, else the hook input's `cwd` when
it is a project root itself, else the project this file sits in (.claude/hooks/tickets/hooklib/ -> four up)."""
import os
import re

HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .claude/hooks/tickets
FILE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
HOOKS_REL = os.path.join(".claude", "hooks", "tickets")
RUNTIME_REL = os.path.join("build", "hooks", "tickets")
HITS_NAME = "hits.jsonl"
STATE_NAME = "prompt_clock.json"
# HOOKS_DIR's name and its parents' in a payload tree: a release export (<export>/payload/dot-claude/hooks/tickets),
# whose payload/ a live hook call must not write into (runtime_allowed())
PAYLOAD_SHAPE = ("payload", "dot-claude", "hooks", "tickets")
MSYS_DRIVE = re.compile(r"^/([A-Za-z])(/.*)?\Z")


def msys_to_windows(p):
	"""An MSYS/Git-Bash path (`/c/Users/...`) as `C:\\Users\\...`; any other path is returned as given."""
	m = MSYS_DRIVE.match(p or "")
	if not m or os.name != "nt":
		return p
	return m.group(1).upper() + ":\\" + (m.group(2) or "").lstrip("/").replace("/", "\\")


def project_root(event=None):
	"""The project root: CLAUDE_PROJECT_DIR, else the hook input's `cwd` when it is a project root itself
	(holds .claude/hooks/tickets/; a session that cd'd into a subfolder must not grow a stray build/hooks/
	there), else this file's project."""
	root = (os.environ.get("CLAUDE_PROJECT_DIR") or "").strip()
	if root:
		return os.path.normpath(msys_to_windows(root))
	cwd = str(event.get("cwd") or "").strip() if isinstance(event, dict) else ""
	if cwd:
		cwd = os.path.normpath(msys_to_windows(cwd))
		if os.path.isdir(os.path.join(cwd, HOOKS_REL)):
			return cwd
	return FILE_ROOT


WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")


def resolve(raw, cwd):
	"""`raw` as an absolute, normalized path (MSYS-mapped, joined to `cwd` when relative, `..` collapsed
	lexically; the filesystem is never touched), or None when it cannot be resolved statically: empty, a
	variable, a substitution, `~`, or a POSIX-only path such as /dev/null. A wildcard stays in the result
	(tools/tickets/*.py still lands inside tools/tickets/)."""
	t = str(raw or "").strip().strip('"').strip("'")
	if not t or t.startswith(("~", "$", "%", "@")) or "$(" in t or "`" in t:
		return None
	t = msys_to_windows(t)
	if os.name == "nt" and t.startswith("/") and not t.startswith("//"):
		return None
	if not WIN_ABS.match(t) and not t.startswith(("\\\\", "//")) and not os.path.isabs(t):
		base = msys_to_windows(str(cwd or "").strip())
		if not base:
			return None
		t = os.path.join(base, t)
	return os.path.normpath(t)


def rel_to_root(path, root):
	"""`path` relative to `root` as a lower-case '/'-joined string ('' for the root itself), or None when it
	lies outside the root. Case-insensitive, as the Windows filesystem is."""
	if not path or not root:
		return None
	r = os.path.normcase(os.path.normpath(root)).rstrip("\\/")
	p = os.path.normcase(os.path.normpath(path))
	if p == r:
		return ""
	if p.startswith(r + os.sep):
		return p[len(r) + 1:].replace("\\", "/").lower()
	return None


def payload_root(hooks_dir=None):
	"""The payload/ folder this package runs from when it sits in a payload tree (<x>/payload/dot-claude/hooks/tickets:
	a release export, or the ticket system's own source) rather than an installed copy; None otherwise. Read from the
	real path, so a start through an 8.3 name or a junction is judged as the folder it reaches."""
	hooks = os.path.realpath(hooks_dir or HOOKS_DIR)
	parts = []
	d = hooks
	for _ in range(len(PAYLOAD_SHAPE)):
		parts.insert(0, os.path.basename(d).lower())
		d = os.path.dirname(d)
	return os.path.join(d, parts[0]) if tuple(parts) == PAYLOAD_SHAPE else None


def runtime_allowed(root, hooks_dir=None):
	"""False when `root`'s runtime directory lies inside the payload/ folder this package runs from (payload_root()):
	a live hook call run from an export falls back to that folder as its project, and must leave the export as it was
	extracted. The hit log and the prompt clock are then not written. Never raises; an error reads as True."""
	try:
		payload = payload_root(hooks_dir)
		return payload is None or rel_to_root(os.path.realpath(runtime_dir(root)), payload) is None
	except Exception:
		return True


def runtime_dir(root):
	return os.path.join(root, RUNTIME_REL)


def hits_path(root):
	return os.path.join(runtime_dir(root), HITS_NAME)


def state_path(root):
	return os.path.join(runtime_dir(root), STATE_NAME)
