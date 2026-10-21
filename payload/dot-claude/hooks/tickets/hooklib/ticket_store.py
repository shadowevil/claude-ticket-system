"""Read-only view of the project's ticket store (.claude/tickets/<PREFIX>NNNN.json), for rules that depend on
which tickets are open. The id prefix comes from .claude/tickets/config.json (`id_prefix`); without one, any
`<LETTERS>-NNNN.json` file counts; the number has 4 to 9 digits (more only for a longer first_ticket_number), as the CLI reads it (max_digits). Never writes; a file that does not parse (malformed, truncated past
TICKET_READ_MAX, or nested deep enough to raise RecursionError) is skipped, and the others still count.

	active_from(root, session) -> [ticket id, ...]   active tickets (in_progress or in_review) whose body
													carries the provenance line "Requested by <session> ..."
													(the tickets skill's provenance format)"""
import os
import re

from hooklib import jsonfile
from hooklib import project

STORE_REL = os.path.join(".claude", "tickets")
# A ticket file's number has 4 to MAX_DIGITS digits, or to one more than config.json's first_ticket_number has when
# that is longer: the CLI's own rule (tickets.py id_max_digits), so a file the CLI does not read as a ticket is none
# here either.
MAX_DIGITS = 9
# \Z, not $: "$" also matches before a final newline, so a name ending in a line feed would count as a ticket file.
ANY_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{4,%d}\.json\Z" % MAX_DIGITS)
TICKET_READ_MAX = 512 * 1024
# The statuses in which a requested change is being worked on: in_progress, then in_review (fixes from the
# review happen there too).
ACTIVE_STATUSES = ("in_progress", "in_review")


def max_digits(cfg):
	"""The longest ticket number the CLI reads, from the config.json already read for the prefix."""
	first = cfg.get("first_ticket_number")
	if isinstance(first, int) and not isinstance(first, bool) and first >= 0:
		return max(MAX_DIGITS, len(str(first)) + 1)
	return MAX_DIGITS


def id_pattern(root):
	cfg = project.read_config(root)
	prefix = cfg.get("id_prefix")
	if isinstance(prefix, str) and prefix:
		return re.compile("^" + re.escape(prefix) + r"[0-9]{4,%d}\.json\Z" % max_digits(cfg))
	return ANY_ID_RE


def is_ticket_file(root, rel_name):
	return bool(id_pattern(root).match(rel_name))


def tickets(root):
	"""Every ticket dict in the store, in file-name order."""
	store = os.path.join(root, STORE_REL)
	try:
		names = sorted(os.listdir(store))
	except OSError:
		return []
	pattern = id_pattern(root)
	out = []
	for name in names:
		if not pattern.match(name):
			continue
		ticket = jsonfile.load(os.path.join(store, name), TICKET_READ_MAX)
		if isinstance(ticket, dict):
			out.append(ticket)
	return out


def provenance_re(session):
	return re.compile(r"Requested by\s+(?:the\s+)?" + re.escape(session) + r"(?![A-Za-z0-9])", re.I)


def active_from(root, session, statuses=ACTIVE_STATUSES):
	"""Ids of tickets in `statuses` whose body carries the provenance line naming `session`."""
	pattern = provenance_re(session)
	return [str(t.get("id")) for t in tickets(root)
			if t.get("status") in statuses and pattern.search(str(t.get("body") or ""))]
