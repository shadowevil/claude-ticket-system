"""The project's ticket-system settings, as the hooks need them. Read-only; never raises.

	.claude/tickets/config.json   the store's settings (id_prefix, store_name, viewer_port, viewer_service,
								  tool_dir, ... - the ticket system's config keys; unknown keys are ignored,
								  so a hook may add its own, e.g. source_of_truth_session)

	read_config(root)            -> dict ({} when missing or malformed)
	service_from_store_name(s)   -> the default viewer_service ("My Board" -> "my-board-tickets"), or None
	tool_dir(root, cfg)          -> (rel, source, notes): the folder holding the ticket CLI and viewer
	check_dir(root, value)       -> (rel, None) or (None, why): a configured folder, validated

The tool's folder is config `tool_dir`, else the folder of `viewer_script`, else the first of TOOL_DIR_CANDIDATES
that holds tickets.py. A configured folder that lies outside the project, is the project root, or overlaps the
board (.claude/tickets) is rejected: it is ignored, the next source is used, and `notes` says why (a rule logs
it as a breadcrumb). Treating the board as the tool's source would flag every ticket edit."""
import os
import re

from hooklib import jsonfile
from hooklib import paths

CONFIG_REL = os.path.join(".claude", "tickets", "config.json")
BOARD_REL = ".claude/tickets"
TOOL_DIR_CANDIDATES = ("tools/tickets", "src/tools/tickets")
TOOL_MARKER = "tickets.py"
SERVICE_SUFFIX = "-tickets"
SERVICE_FALLBACK = "tickets"


def read_config(root):
	return jsonfile.load_dict(os.path.join(root, CONFIG_REL))


def service_from_store_name(name):
	"""The viewer's default service marker, exactly as tickets.py derives it (default_viewer_service):
	lowercase store_name, runs of anything but [a-z0-9] as '-', trimmed, plus '-tickets'; 'tickets' when
	nothing is left. None when store_name is not a non-empty string (tickets.py refuses such a config, so
	there is no viewer to check). tickets.py itself is never imported: it exits on a bad config."""
	if not isinstance(name, str) or not name.strip():
		return None
	slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
	return slug + SERVICE_SUFFIX if slug else SERVICE_FALLBACK


def overlaps(rel, other):
	"""True when the '/'-joined relative folders `rel` and `other` are the same, or one holds the other."""
	return rel == other or rel.startswith(other + "/") or other.startswith(rel + "/")


def check_dir(root, value):
	"""(rel, None) for a usable folder, with `rel` '/'-joined in the case given; (None, why) otherwise."""
	if not isinstance(value, str):
		return None, "is not a string"
	full = paths.resolve(value.replace("\\", "/").rstrip("/") or ".", root)
	low = paths.rel_to_root(full, root)
	if low is None:
		return None, "lies outside the project or does not resolve"
	if low == "":
		return None, "is the project root"
	if overlaps(low, BOARD_REL):
		return None, "overlaps the board (.claude/tickets)"
	return os.path.relpath(full, root).replace("\\", "/"), None


def tool_dir(root, cfg=None):
	"""(rel or None, source, notes). `source` is "tool_dir", "viewer_script", "found" or "none"; `notes` is
	[(config key, why)] for every configured value that was rejected."""
	cfg = read_config(root) if cfg is None else cfg
	notes = []
	value = cfg.get("tool_dir")
	if value is not None and not (isinstance(value, str) and not value.strip()):
		rel, why = check_dir(root, value)
		if rel:
			return rel, "tool_dir", notes
		notes.append(("tool_dir", why))
	script = cfg.get("viewer_script")
	if isinstance(script, str) and script.strip():
		rel, why = check_dir(root, os.path.dirname(script.replace("\\", "/").strip()))
		if rel:
			return rel, "viewer_script", notes
		notes.append(("viewer_script", why))
	for cand in TOOL_DIR_CANDIDATES:
		if os.path.isfile(os.path.join(root, cand, TOOL_MARKER)):
			return cand, "found", notes
	return None, "none", notes
