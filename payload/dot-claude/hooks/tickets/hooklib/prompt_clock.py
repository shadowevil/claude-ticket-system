"""The per-project prompt clock: when the previous prompt in this project arrived, kept in
<root>/build/hooks/tickets/prompt_clock.json as {"ts", "iso", "session", "kind"}. One clock per project,
shared by every session in it (the ticket viewer is per project too, one port).

A prompt is classified from its text, the only thing the live UserPromptSubmit input carries:
	human              the user typing (slash commands included)
	peer               another Claude SESSION's message: "Another Claude session sent a message:" then
					   <cross-session-message ...> (e.g. a downstream ticket request - work arriving)
	agent-report       this session's own sub-agent reporting: the same header, then <agent-message ...>.
					   Work already running, not starting; not conversation
	task-notification  a background task reporting back; not conversation
Only conversation (human, peer) reads and moves the clock and may fire a rule; the other two are ignored.
Fails open: an unreadable or corrupt state file reads as "no previous prompt"; a failed write is ignored."""
import json
import os
import time

from hooklib import jsonfile
from hooklib import paths

HUMAN = "human"
PEER = "peer"
AGENT_REPORT = "agent-report"
TASK_NOTIFICATION = "task-notification"
MESSAGE_HEADER = "Another Claude session sent a message"
AGENT_TAG = "<agent-message"
PEER_TAG = "<cross-session-message"
TASK_TAG = "<task-notification"
STATE_READ_MAX = 4096


def classify(prompt):
	text = str(prompt or "").lstrip()
	if text.startswith(TASK_TAG):
		return TASK_NOTIFICATION
	if text.startswith(MESSAGE_HEADER):
		body = text.split("\n", 1)[1].lstrip() if "\n" in text else ""
		return AGENT_REPORT if body.startswith(AGENT_TAG) else PEER
	if text.startswith(AGENT_TAG):
		return AGENT_REPORT
	if text.startswith(PEER_TAG):
		return PEER
	return HUMAN


def origin_kind(kind):
	"""The transcript's `origin.kind` for a classified kind (an agent report is recorded as "peer")."""
	return PEER if kind == AGENT_REPORT else kind


def is_conversation(kind):
	"""Whether a prompt of this kind is conversation: it reads and moves the clock, and may fire a rule."""
	return kind in (HUMAN, PEER)


def read(root):
	"""The previous prompt's record, or None (no file, unreadable, corrupt, or no usable ts)."""
	rec = jsonfile.load(paths.state_path(root), STATE_READ_MAX)
	if not isinstance(rec, dict) or not isinstance(rec.get("ts"), (int, float)) or isinstance(rec.get("ts"), bool):
		return None
	return rec


def write(root, rec):
	"""Replace the state atomically (temp file + os.replace). Never raises. Writes nothing inside a release export's
	payload/ (paths.runtime_allowed())."""
	if not paths.runtime_allowed(root):
		return
	path = paths.state_path(root)
	tmp = "%s.%d.tmp" % (path, os.getpid())
	try:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(tmp, "w", encoding="ascii", newline="\n") as fh:
			json.dump(rec, fh, ensure_ascii=True)
		os.replace(tmp, path)
	except Exception:
		try:
			os.remove(tmp)
		except OSError:
			pass


def advance(root, now, session=None, kind=HUMAN):
	"""Record this prompt as the latest and return the previous record (or None)."""
	previous = read(root)
	write(root, {"ts": now, "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
				 "session": session, "kind": kind})
	return previous


def gap_seconds(previous, now):
	"""Seconds since the previous prompt, or None when there is none on record. May be negative (clock skew)."""
	if not previous:
		return None
	return float(now) - float(previous["ts"])
