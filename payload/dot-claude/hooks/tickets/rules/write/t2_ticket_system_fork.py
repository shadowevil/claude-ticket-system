"""T2 - the ticket system's SOURCE is not changed locally; the board is the project's own (RULES.md "T2").
Log-only: never in ENFORCE; enforcing is the user's call.

User rule, 2026-09-30: "The Ticket Master project will now be the source of truth for any future changes, so
you may get tickets from him to update your ticket system", clarified the same day: "Our ticket system is
still ours. The ticket master is just the maintainer of the source code and versioning and changes. We just
use the board." A fault or a wanted change goes to the maintaining session as a request, not into a local
fork; its updates are applied under a ticket filed from its request (the tickets skill).

A write (Write/Edit/MultiEdit/NotebookEdit, or a shell command's redirect, copy, move, in-place edit or
delete) that lands in the ticket system's source - the tool's folder (config tool_dir, else the folder of
viewer_script, else tools/tickets or src/tools/tickets, whichever holds tickets.py), .claude/skills/tickets/**
or .claude/hooks/tickets/** - is "fork" unless a ticket requested by the maintaining session is active
(in_progress, in_review or verified; not user_review): then it is "tied". THE BOARD IS NEVER JUDGED: tickets (written by tickets.py
new/set), tags.json and the settings (config.json) are the project's own, and a tool_dir that overlaps the
board is ignored with a breadcrumb. ticket.schema.json is left out too: it mixes the maintained format with
the project's own enums and id pattern, which a static check cannot tell apart. The hooks' policy.py is the
project's own enforce setting, and __pycache__ is not source.

	evaluate_tool(event, ctx) -> [hit] when the call writes into the ticket system's source, else []
"""
import json
import os
import sys

from hooklib import output
from hooklib import paths
from hooklib import project
from hooklib import shell
from hooklib import ticket_store
from hooklib.policy import ENFORCE, MODE

RULE = "T2"
SOURCE_OF_TRUTH = "Ticket Master"  # the maintaining session's name; config.json "source_of_truth_session" overrides
CONFIG_SESSION_KEY = "source_of_truth_session"
ISSUES_URL = "https://github.com/shadowevil/claude-ticket-system/issues"  # upstream reports without that session
SKILL_DIR = ".claude/skills/tickets"
HOOKS_DIR = ".claude/hooks/tickets"
PROTECTED_DIRS = project.TOOL_DIR_CANDIDATES + (SKILL_DIR, HOOKS_DIR)  # when no tool folder is known
PROJECT_OWNED = (HOOKS_DIR + "/hooklib/policy.py",)  # inside a protected folder, but the project's own setting
PROTECTED_FILES = ()  # the board (.claude/tickets/*: tickets, tags.json, config.json, schema) is the project's
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
FORK = "fork"
TIED = "tied"

MSG = {
	RULE: "Local change to the ticket system's source ({paths}). The board is this project's own, but {session} "
		  "maintains the ticket system (CLI, viewer, schema format, tickets skill, these hooks) and its "
		  "versions, and it is not changed locally (the tickets skill). No {session} ticket is in progress or "
		  "in review, so this is a local fork: send the fault or wanted change to {session} as a request "
		  "instead (with no such session on this machine, draft an issue for " + ISSUES_URL + " for the user to "
		  "post, or post it only with their OK). If this IS a "
		  "{session} update, file it as a ticket carrying the provenance line "
		  "(\"Requested by {session} ...\") and set it in_progress before applying it. Board edits (tickets, "
		  "tags, config) are never affected.",
}


def tool_dirs(root):
	"""(dirs, notes): the ticket system's source folders in this project, lower-case and '/'-joined - the tool's
	folder (both candidates when none is known), the tickets skill and these hooks - and [(config key, why)]
	for every configured folder that was rejected."""
	rel, _source, notes = project.tool_dir(root)
	tools = (rel.lower(),) if rel else project.TOOL_DIR_CANDIDATES
	return tools + (SKILL_DIR, HOOKS_DIR), notes


def protected(rel, kind="write", dirs=PROTECTED_DIRS):
	"""True when a target at `rel` (lower-case, '/'-joined, relative to the root) changes the system's source.
	A delete of an ancestor (rm -r tools) takes the source with it; a write into an ancestor does not."""
	if not rel:
		return False
	if "__pycache__" in rel.split("/") or rel in PROJECT_OWNED:
		return False
	for d in dirs:
		if rel == d or rel.startswith(d + "/"):
			return True
	if rel in PROTECTED_FILES:
		return True
	if kind == "delete":
		return any(p.startswith(rel.rstrip("/") + "/") for p in tuple(dirs) + PROTECTED_FILES)
	return False


def source_session(root):
	value = project.read_config(root).get(CONFIG_SESSION_KEY)
	return value.strip() if isinstance(value, str) and value.strip() else SOURCE_OF_TRUTH


def call_targets(event):
	"""([(verb, raw target, kind)] this tool call writes, complete). complete is False when a shell command
	was too long to parse in full."""
	tool = str(event.get("tool_name") or "")
	ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
	if tool in FILE_TOOLS:
		raw = ti.get("file_path") or ti.get("notebook_path")
		return ([(tool, str(raw), "write")] if raw else []), True
	if tool in SHELL_TOOLS:
		return shell.parse(ti.get("command") or "", tool == "PowerShell")
	return [], True


def match_targets(targets, event, root, dirs):
	"""[(verb, raw, rel, kind)] for every target that lands in the system's source."""
	cwd = event.get("cwd") or root
	found = []
	for verb, raw, kind in targets:
		rel = paths.rel_to_root(paths.resolve(raw, cwd), root)
		if protected(rel, kind, dirs):
			found.append((verb, raw, rel, kind))
	return found


def protected_targets(event, root, dirs=None):
	"""[(verb, raw, rel, kind)] for every target of this call that lands in the system's source (replay.py)."""
	targets = call_targets(event)[0]
	if not targets:
		return []
	return match_targets(targets, event, root, tool_dirs(root)[0] if dirs is None else dirs)


def evaluate_tool(event, ctx):
	targets, complete = call_targets(event)
	if not targets:
		return []
	dirs, notes = tool_dirs(ctx["root"])
	for key, why in notes:
		output.note(ctx["root"], RULE, key, why, event)
	found = match_targets(targets, event, ctx["root"], dirs)
	if not found:
		return []
	session = source_session(ctx["root"])
	tied = ticket_store.active_from(ctx["root"], session)
	return [{"verdict": TIED if tied else FORK, "targets": found, "tied": tied, "session": session,
			 "complete": complete}]


def mode_for(enforce=None):
	return "enforce" if RULE in (ENFORCE if enforce is None else enforce) else MODE


def message(hit):
	rels = sorted({t[2] for t in hit["targets"]})
	return MSG[RULE].format(paths=", ".join(rels), session=hit["session"])


def log_rows(event, ctx, hits, ms, enforce=None):
	rows = []
	mode = mode_for(enforce)
	ti = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
	for hit in hits:
		fork = hit["verdict"] == FORK
		rows.append({
			"ts": output.now_iso(), "mode": mode, "rule": RULE, "event": "PreToolUse",
			"tool": event.get("tool_name"), "verdict": hit["verdict"],
			"would": ("denied the call" if mode == "enforce" else "deny the call") if fork
			else "nothing (a %s ticket is active)" % hit["session"],
			"targets": sorted({t[2] for t in hit["targets"]}), "verbs": sorted({t[0] for t in hit["targets"]}),
			"tied": hit["tied"], "partial": not hit.get("complete", True),
			"session": event.get("session_id"), "agent": event.get("agent_id"),
			"sample": [output.sample_text(ti.get("command") or ti.get("file_path") or ti.get("notebook_path") or "")],
			"ms": ms, "msg": message(hit) if fork else "",
		})
	return rows


def decide(event, ctx, hits, enforce=None):
	"""The deny reason for a FORK hit once "T2" is in the enforce set (default ENFORCE), else None."""
	if mode_for(enforce) != "enforce":
		return None
	reasons = ["T2: " + message(h) for h in hits if h.get("verdict") == FORK]
	return " ".join(reasons) or None


# (relative target, kind, must be judged part of the ticket system's source) - default folders
PROTECTED_CASES = [
	("tools/tickets/serve.py", "write", True),
	("tools/tickets/lib/marked/marked.min.js", "write", True),
	("src/tools/tickets/tickets.py", "write", True),  # no tool folder known: both candidates count
	("tools/tickets", "delete", True),
	(".claude/skills/tickets/skill.md", "write", True),
	(".claude/hooks/tickets/hooklib/shell.py", "write", True),  # these hooks are the system's source too
	("tools", "delete", True),                        # rm -r tools takes the tool's source with it
	(".claude", "delete", True),                      # ... and .claude takes the skill and the hooks
	(".claude/hooks", "delete", True),
	(".claude/hooks/tickets/hooklib/policy.py", "write", False),  # the project's own enforce setting
	(".claude/hooks/tickets/__pycache__/x.pyc", "write", False),
	(".claude/hooks/hooklib/x.py", "write", False),   # a project's own hooks
	(".claude/tickets/ticket.schema.json", "write", False),  # the project's enums and id pattern live here too
	(".claude/tickets/config.json", "write", False),  # the project's settings
	(".claude/tickets", "delete", False),             # the board is the project's own
	("tools/tickets/__pycache__/tickets.cpython-313.pyc", "write", False),
	(".claude/tickets/tk-0007.json", "write", False),   # ticket data, written by the CLI
	(".claude/tickets/tags.json", "write", False),      # project-local tags
	("tools/scripts/backup.ps1", "write", False),
	("tools", "write", False),                        # a copy INTO tools/ is not into tools/tickets/
	(".claude/skills/other/skill.md", "write", False),
	("tools/ticketsx/a.py", "write", False),          # a prefix, not the folder
	("", "delete", False),                            # the root itself
	(None, "write", False),                           # outside the root, or unresolvable
]

# (command, powershell, expected [(verb, raw target, kind)])
SHELL_CASES = [
	("cp a.py tools/tickets/serve.py", False, [("cp", "tools/tickets/serve.py", "write")]),
	("cp -r tools/tickets working/x", False, [("cp", "working/x", "write")]),            # copying FROM is a read
	("cp -t tools/tickets a.py b.py", False, [("cp", "tools/tickets", "write")]),
	("mv tools/tickets/a.py b.py", False, [("mv", "tools/tickets/a.py", "write"), ("mv", "b.py", "write")]),
	("echo x > tools/tickets/a.txt 2>&1", False, [(">", "tools/tickets/a.txt", "write")]),
	("make &> tools/tickets/log.txt", False, [(">", "tools/tickets/log.txt", "write")]),
	("ls 2>/dev/null; dir 2>$null", False, []),
	("python tools/tickets/tickets.py list > out.txt", False, [(">", "out.txt", "write")]),
	("python tools/tickets/tickets.py set TK-0002 --status done", False, []),            # the CLI writes ticket data
	("python - <<'EOF'\nif a > b: pass\nopen('x','w')\nEOF\necho ok", False, []),       # heredoc body is data
	("sed -i 's/a/b/' tools/tickets/app.js", False, [("sed -i", "tools/tickets/app.js", "write")]),
	("rm -rf tools; ls", False, [("rm", "tools", "delete")]),
	("git checkout -- tools/tickets/serve.py", False, [("git checkout", "tools/tickets/serve.py", "write")]),
	("cat a | tee -a \"tools/tickets/b c.txt\"", False, [("tee", "tools/tickets/b c.txt", "write")]),
	("echo 'unbalanced", False, []),
	# an input redirect's operand is a read, never a write target
	("tee out.txt < tools/tickets/in.txt", False, [("tee", "out.txt", "write")]),
	("sort < tools/tickets/a.txt > b.txt", False, [(">", "b.txt", "write")]),
	("touch a.txt 0< tools/tickets/x", False, [("touch", "a.txt", "write")]),
	("tee <<< 'x > y' tools/tickets/y", False, [("tee", "tools/tickets/y", "write")]),
	("cat <<'EOF' > tools/tickets/x.txt\nbody > y\nEOF", False, [(">", "tools/tickets/x.txt", "write")]),
	("mysql db < tools/tickets/dump.sql", False, []),
	("diff <(ls tools/tickets) b > out.txt", False, [(">", "out.txt", "write")]),
	("exec 3<> tools/tickets/fifo", False, [("<>", "tools/tickets/fifo", "write")]),
	("echo x 12>tools/tickets/fd.txt", False, [(">", "tools/tickets/fd.txt", "write")]),
	("Copy-Item x -Destination tools\\tickets\\y", True, [("copy-item", "tools\\tickets\\y", "write")]),
	("Copy-Item tools\\tickets\\serve.py working\\s.py", True, [("copy-item", "working\\s.py", "write")]),
	("Set-Content tools/tickets/a.txt \"hi\"", True, [("set-content", "tools/tickets/a.txt", "write")]),
	("Set-Content -Value hi -Path tools/tickets/a.txt", True, [("set-content", "tools/tickets/a.txt", "write")]),
	("Remove-Item a, b -Force", True, [("remove-item", "a", "delete"), ("remove-item", "b", "delete")]),
	("\"x\" | Out-File -FilePath tools\\tickets\\o.txt -Encoding utf8", True, [("out-file", "tools\\tickets\\o.txt", "write")]),
	("$s = @'\nline > x\n'@\nWrite-Host $s", True, []),                                    # here-string body is data
	("$s = @\"\n\"@\nSet-Content tools/tickets/e.txt $s", True, [("set-content", "tools/tickets/e.txt", "write")]),
	("Get-Content tools\\tickets\\serve.py | Select-String port", True, []),
]


def run_self_test():
	"""(assertion count, [failure, ...]) for T2. The count is the number of checks actually made."""
	import time
	from hooklib import fixtures
	ck = fixtures.Checker("T2")
	ok = ck.check

	for rel, kind, want in PROTECTED_CASES:
		ok(protected(rel, kind) == want, "protected(%r, %r) != %r" % (rel, kind, want))
	ok(any(c[2] for c in PROTECTED_CASES) and any(not c[2] for c in PROTECTED_CASES),
	   "lacks a must-fire or must-not-fire protected case")
	for cmd, ps, want in SHELL_CASES:
		got = shell.write_targets(cmd, ps)
		ok(got == want, "write_targets(%r) = %r, want %r" % (cmd[:50], got, want))

	# the parser is linear and bounded: each command below took seconds (quadratic) before; a huge command is
	# parsed up to its last whole segment inside the bounds, and a cut never invents a target
	def timed(cmd, ps=False):
		started = time.perf_counter()
		got = shell.parse(cmd, ps)
		return got, time.perf_counter() - started
	huge = "cp a.py tools/tickets/serve.py; " + "echo x > out.txt; " * 120000  # about 2 MB
	(targets, complete), secs = timed(huge)
	ok(targets[:1] == [("cp", "tools/tickets/serve.py", "write")] and not complete and secs < 2.0,
	   "a 2 MB command: %d targets, complete %r, %.2f s" % (len(targets), complete, secs))
	near = shell.PARSE_MAX - 100
	for label, cmd, ps, want in (
			("here-string openers", "@'\n" * (near // 3) + "Set-Content tools/tickets/h.txt x", True,
			 [("set-content", "tools/tickets/h.txt", "write")]),
			("redirects", "echo " + "> a " * (near // 4) + "> tools/tickets/r.txt", False, None),
			("VAR=x prefixes", "A=1 " * (near // 4) + "cp a tools/tickets/v.txt", False,
			 [("cp", "tools/tickets/v.txt", "write")]),
			("heredocs", "cat <<E\nE\n" * (near // 10) + "touch tools/tickets/d.txt", False,
			 [("touch", "tools/tickets/d.txt", "write")]),
			("quotes", "echo '" + "x' '" * (near // 4) + "' > tools/tickets/q.txt", False,
			 [(">", "tools/tickets/q.txt", "write")]),
			("separators", ";" * near + "rm tools/tickets/s.txt", False, [("rm", "tools/tickets/s.txt", "delete")])):
		(targets, complete), secs = timed(cmd, ps)
		good = complete and secs < 1.0 and (want is None or targets == want)
		if want is None:
			good = good and len(targets) == near // 4 + 1 and targets[-1] == (">", "tools/tickets/r.txt", "write")
		ok(good, "%s (%d chars): complete %r, %.2f s, last %r" % (label, len(cmd), complete, secs, targets[-1:]))
	cut = "echo ok; rm -r tools" + "/x" * shell.PARSE_MAX
	(targets, complete), secs = timed(cut)
	ok(targets == [] and not complete and secs < 1.0, "a cut segment was judged: %r" % (targets[:2],))

	root_w = "C:\\p\\proj"
	ok(paths.resolve("/c/p/proj/tools/tickets/a.py", "") == "C:\\p\\proj\\tools\\tickets\\a.py", "MSYS path")
	ok(paths.msys_to_windows("/c/p\n") == "/c/p\n" and paths.msys_to_windows("/c") == ("C:\\" if os.name == "nt" else "/c"),
	   "an MSYS path with a trailing line feed was mapped, or a bare drive was not")
	ok(paths.rel_to_root(paths.resolve("tickets\\a.py", root_w + "\\tools"), root_w) == "tools/tickets/a.py",
	   "relative path joined to cwd")
	ok(paths.rel_to_root(paths.resolve("..\\..\\x", root_w + "\\tools"), root_w) is None, "a '..' escape stayed inside")
	ok(paths.resolve("$env:TEMP\\x", root_w) is None and paths.resolve("~/x", root_w) is None, "a variable resolved")
	ok(paths.rel_to_root(paths.resolve("tools/tickets/*.py", root_w), root_w) == "tools/tickets/*.py", "wildcard")
	ok(paths.rel_to_root("C:\\P\\PROJ\\Tools\\Tickets\\A.py", root_w) == "tools/tickets/a.py", "case-insensitive rel")

	def write_config(root, cfg):
		fixtures.write_config(root, dict({"id_prefix": fixtures.PREFIX}, **cfg))

	def rows_of(root):
		try:
			with open(paths.hits_path(root), encoding="ascii") as fh:
				return [json.loads(line) for line in fh.read().splitlines()]
		except OSError:
			return []

	with fixtures.scratch_root() as root:
		def ev(tool, cwd=None, **ti):
			return {"tool_name": tool, "cwd": cwd or root, "session_id": "s", "tool_input": ti}

		def verdicts(event):
			return [h["verdict"] for h in evaluate_tool(event, {"root": root})]

		serve = os.path.join(root, "tools", "tickets", "serve.py")
		ok(verdicts(ev("Write", file_path=serve)) == [FORK], "Write into tools/tickets/ was not a fork")
		ok(verdicts(ev("Edit", file_path=os.path.join(root, ".claude", "skills", "tickets", "SKILL.md"))) == [FORK],
		   "Edit of the tickets skill was not a fork")
		ok(verdicts(ev("Edit", file_path=os.path.join(root, ".claude", "hooks", "tickets", "hooklib", "shell.py"))) == [FORK],
		   "Edit of these hooks was not a fork")
		ok(verdicts(ev("Edit", file_path=os.path.join(root, ".claude", "hooks", "tickets", "hooklib", "policy.py"))) == [],
		   "the project's enforce setting (policy.py) was judged")
		ok(verdicts(ev("Write", file_path=os.path.join(root, ".claude", "tickets", "TK-0009.json"))) == [],
		   "ticket data was judged")
		ok(verdicts(ev("Edit", file_path=os.path.join(root, ".claude", "tickets", "tags.json"))) == [], "tags.json was judged")
		ok(verdicts(ev("Edit", file_path=os.path.join(root, ".claude", "tickets", "config.json"))) == [], "config.json was judged")
		ok(verdicts(ev("Bash", command="python tools/tickets/tickets.py new --summary x --body-file working/b.md")) == []
		   and verdicts(ev("PowerShell", command="python tools/tickets/tickets.py set TK-0002 --status done")) == [],
		   "a board edit through the CLI was judged")
		ok(verdicts(ev("Write", file_path=os.path.join(root, "working", "x", "serve.py"))) == [], "a scratch copy was judged")
		ok(verdicts(ev("Read", file_path=serve)) == [], "a Read was judged")
		ok(verdicts(ev("Bash", command="cp a.py tools/tickets/serve.py")) == [FORK], "shell copy into the system")
		ok(verdicts(ev("Bash", command="python x.py < tools/tickets/serve.py > out.txt")) == [],
		   "a read through '<' was judged a write")
		ok(verdicts(ev("Bash", cwd=os.path.join(root, "tools"), command="echo x > tickets/a.txt")) == [FORK],
		   "a relative target was not joined to the call's cwd")
		ok(verdicts(ev("PowerShell", command="Copy-Item tools\\tickets\\serve.py working\\s.py")) == [],
		   "copying out of the system was judged")

		# which tickets tie a write: one the maintaining session requested, while it is in_progress, in_review or verified
		fixtures.write_ticket(root, "TK-0007", "in_progress", "Adopt the viewer fix.")
		ok(verdicts(ev("Write", file_path=serve)) == [FORK], "an unrelated in_progress ticket tied the write")
		fixtures.write_ticket(root, "TK-0008", "done", "Requested by Ticket Master (x) on 2026-10-01 via cross-session message.")
		fixtures.write_ticket(root, "TK-0009", "open", "Requested by Ticket Master (x) on 2026-10-01 via cross-session message.")
		ok(verdicts(ev("Write", file_path=serve)) == [FORK], "a done or open Ticket Master ticket tied the write")
		fixtures.write_text(os.path.join(root, ".claude", "tickets", "TK-0011.json"), "[" * 100000 + "]" * 100000)
		fixtures.write_text(os.path.join(root, ".claude", "tickets", "TK-0012.json"), '{"id": "TK-0012", "status": ')
		fixtures.write_ticket(root, "TK-0010", "in_review", "Requested by Ticket Master (uds:x) on 2026-10-01 via cross-session message.\n\nPort the CLI fix.")
		hits = evaluate_tool(ev("Write", file_path=serve), {"root": root})
		ok([(h["verdict"], h["tied"]) for h in hits] == [(TIED, ["TK-0010"])],
		   "an in_review Ticket Master ticket did not tie (past a deeply nested and a truncated ticket): %r" % (hits,))
		ok([t.get("id") for t in ticket_store.tickets(root)] == ["TK-0007", "TK-0008", "TK-0009", "TK-0010"],
		   "the store view did not skip exactly the unreadable tickets")
		# 1.4.0: user_review (paused, waiting on the user) does not tie; verified (landing the work) does
		fixtures.write_ticket(root, "TK-0013", "user_review", "Requested by Ticket Master (uds:x) on 2026-10-01 via cross-session message.")
		hits = evaluate_tool(ev("Write", file_path=serve), {"root": root})
		ok([(h["verdict"], h["tied"]) for h in hits] == [(TIED, ["TK-0010"])],
		   "a user_review Ticket Master ticket tied the write: %r" % (hits,))
		fixtures.write_ticket(root, "TK-0014", "verified", "Requested by Ticket Master (uds:x) on 2026-10-01 via cross-session message.")
		hits = evaluate_tool(ev("Write", file_path=serve), {"root": root})
		ok([(h["verdict"], h["tied"]) for h in hits] == [(TIED, ["TK-0010", "TK-0014"])],
		   "a verified Ticket Master ticket did not tie: %r" % (hits,))

		# a file name is a ticket file only as a whole: a trailing line feed ("$" would let it through) is not one
		ids = {"with a prefix": "TK-", "without a prefix": None}
		for label, prefix in ids.items():
			with fixtures.scratch_root() as root2:
				fixtures.write_config(root2, {"id_prefix": prefix} if prefix else {})
				name = "TK-0042.json"
				ok(ticket_store.is_ticket_file(root2, name), "a ticket file name was refused (%s)" % label)
				ok(not any(ticket_store.is_ticket_file(root2, bad) for bad in (
					name + "\n", name + "\r\n", "TK-0042.json ", "xTK-0042.json", "TK-42.json", "TK-0042.jsonl")),
					"a name that is not a ticket file counted as one (%s)" % label)
				real_listdir, real_load = os.listdir, ticket_store.jsonfile.load
				os.listdir = lambda _p: ["TK-0042.json\n", "TK-0043.json", "TK-0044.json\r\n"]
				# every name reads as a ticket, so only the name check decides; config.json still reads for real
				ticket_store.jsonfile.load = lambda p, m=None: (real_load(p, m) if p.endswith("config.json")
																else {"id": os.path.basename(p)})
				try:
					got = [t["id"] for t in ticket_store.tickets(root2)]
				finally:
					os.listdir, ticket_store.jsonfile.load = real_listdir, real_load
				ok(got == ["TK-0043.json"], "tickets() read a name with a trailing line break (%s): %r" % (label, got))
				# the number has 4 to 9 digits, as the CLI reads it (tickets.py id_max_digits)
				ok(ticket_store.is_ticket_file(root2, "TK-123456789.json")
				   and not ticket_store.is_ticket_file(root2, "TK-1234567890.json")
				   and not ticket_store.is_ticket_file(root2, "TK-" + "1" * 240 + ".json"),
				   "a ticket number's digit limit differs from the CLI's (%s)" % label)
		# a first_ticket_number longer than 8 digits widens the limit to one more digit than it has, as in the CLI
		with fixtures.scratch_root() as root2:
			fixtures.write_config(root2, {"id_prefix": "TK-", "first_ticket_number": 10 ** 10})
			ok(ticket_store.is_ticket_file(root2, "TK-" + "1" * 12 + ".json")
			   and not ticket_store.is_ticket_file(root2, "TK-" + "1" * 13 + ".json"),
			   "a long first_ticket_number did not widen the digit limit as the CLI does")
		fixtures.write_ticket(root, "TK-0010", "in_progress", "Requested by Ticket Master (uds:x) on 2026-10-01 via cross-session message.")
		ok(verdicts(ev("Write", file_path=serve)) == [TIED], "an in_progress Ticket Master ticket did not tie")
		write_config(root, {CONFIG_SESSION_KEY: "Ticket Hub"})
		ok(verdicts(ev("Write", file_path=serve)) == [FORK], "the configured source-of-truth session was ignored")
		fixtures.write_text(os.path.join(root, ".claude", "tickets", "config.json"), "[" * 100000 + "]" * 100000)
		ok(verdicts(ev("Write", file_path=serve)) == [TIED] and source_session(root) == SOURCE_OF_TRUTH,
		   "a deeply nested config.json broke the store view or the session default")

		# the tool's folder: discovered, from viewer_script, from tool_dir; only the one in use is judged
		write_config(root, {})
		ok(tool_dirs(root) == (project.TOOL_DIR_CANDIDATES + (SKILL_DIR, HOOKS_DIR), []),
		   "no tool installed: %r" % (tool_dirs(root),))
		fixtures.write_text(os.path.join(root, "src", "tools", "tickets", "tickets.py"), "")
		ok(tool_dirs(root)[0][0] == "src/tools/tickets", "the installed tool folder was not found: %r" % (tool_dirs(root),))
		fixtures.write_text(os.path.join(root, "tools", "tickets", "tickets.py"), "")
		ok(tool_dirs(root)[0][0] == "tools/tickets", "tools/tickets is not preferred when both hold tickets.py")
		write_config(root, {"viewer_script": "src\\tools\\tickets\\serve.py"})
		ok(tool_dirs(root)[0][0] == "src/tools/tickets", "tool folder from viewer_script: %r" % (tool_dirs(root),))
		ok(len(protected_targets(ev("Write", file_path=os.path.join(root, "src", "tools", "tickets", "tickets.py")), root)) == 1
		   and protected_targets(ev("Write", file_path=serve), root) == [],
		   "the configured tool folder was not the one judged")
		write_config(root, {"tool_dir": "vendor/Tickets/", "viewer_script": "x/serve.py"})
		ok(tool_dirs(root) == (("vendor/tickets", SKILL_DIR, HOOKS_DIR), []), "tool_dir did not win over viewer_script")
		write_config(root, {"tool_dir": os.path.join(root, "Vendor", "T")})
		ok(tool_dirs(root)[0][0] == "vendor/t", "an absolute tool_dir inside the project was not used")

		# a configured folder that overlaps the board, is the root, or lies outside is ignored, with a breadcrumb
		for value, why in ((".claude/tickets", "overlaps the board"), (".claude\\tickets\\", "overlaps the board"),
						   (".claude", "overlaps the board"), (".CLAUDE/Tickets/sub", "overlaps the board"),
						   (".", "is the project root"), ("", None), ("../elsewhere", "lies outside"),
						   (os.path.dirname(root), "lies outside"), ("$HOME/x", "lies outside"), (7, "is not a string")):
			dirs, notes = tool_dirs(dict_root(root, write_config, {"tool_dir": value}))
			got_why = notes[0][1] if notes else None
			ok(dirs[0] == "tools/tickets" and (why is None and not notes or why is not None and got_why.startswith(why)),
			   "tool_dir %r: dirs %r, notes %r" % (value, dirs[:1], notes))
		write_config(root, {"viewer_script": ".claude/tickets/serve.py"})
		dirs, notes = tool_dirs(root)
		ok(dirs[0] == "tools/tickets" and notes == [("viewer_script", "overlaps the board (.claude/tickets)")],
		   "a viewer_script in the board was used: %r %r" % (dirs[:1], notes))
		write_config(root, {"tool_dir": ".claude/tickets"})
		before = len(rows_of(root))
		board = os.path.join(root, ".claude", "tickets", "TK-0001.json")
		ok(all(verdicts(ev("Write", file_path=board)) == [] for _ in range(8)),
		   "a tool_dir overlapping the board made a board edit a fork")
		notes_logged = [r for r in rows_of(root)[before:] if r.get("rule") == "hook-config"]
		ok(len(notes_logged) == 5 and notes_logged[0]["sample"] == ["T2 tool_dir overlaps the board (.claude/tickets)"]
		   and ".claude/tickets\"" not in json.dumps(notes_logged[0]["sample"]),
		   "the ignored tool_dir left %d breadcrumb(s), want 5 (capped): %r" % (len(notes_logged), notes_logged[:1]))
		ok(verdicts(ev("Write", file_path=serve)) == [TIED], "the fallback tool folder was not judged")

		fork = {"verdict": FORK, "targets": [("Write", serve, "tools/tickets/serve.py", "write")], "tied": [],
				"session": SOURCE_OF_TRUTH, "complete": True}
		ok(RULE not in ENFORCE, "T2 is in ENFORCE; enforcing is the user's call")
		ok(decide({}, {}, [fork]) is None and decide({}, {}, [fork], enforce=frozenset()) is None, "denied while log-only")
		reason = decide({}, {}, [fork], enforce=frozenset({RULE})) or ""
		ok("tools/tickets/serve.py" in reason and "Ticket Master" in reason and all(ord(c) < 128 for c in reason + MSG[RULE]),
		   "enforced reason: %r" % reason[:120])
		ok(decide({}, {}, [dict(fork, verdict=TIED)], enforce=frozenset({RULE})) is None, "denied a tied write")
		ok(log_rows({}, {}, [fork], 1)[0]["mode"] == MODE and log_rows({}, {}, [fork], 1, frozenset({RULE}))[0]["mode"] == "enforce",
		   "row mode does not follow the enforce set")
		secret = "ghp_Zx9Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk0LmNb"
		row = log_rows({"tool_name": "Bash", "tool_input": {
			"command": "curl -H 'Authorization: token %s' https://api.example.test > tools/tickets/x.json" % secret}},
			{}, [fork], 1)[0]
		ok(secret[4:12] not in json.dumps(row) and "tools/tickets/x.json" in row["sample"][0],
		   "a secret in the command reached the log sample: %r" % (row["sample"],))

	# the entry points end to end, in process: log one row, print nothing, never block; enforced -> one deny
	import shell_guard
	import write_guard
	real_stdin, real_stdout = sys.stdin, sys.stdout
	real_env = os.environ.get("CLAUDE_PROJECT_DIR")

	def call(entry, root, payload, enforce=None):
		os.environ["CLAUDE_PROJECT_DIR"] = root
		sys.stdin = fixtures.stdin_bytes(payload)
		sys.stdout = captured = __import__("io").StringIO()
		code = None
		started = time.perf_counter()
		try:
			entry.main(enforce)
		except SystemExit as exc:
			code = exc.code
		finally:
			sys.stdout = real_stdout
		return code, captured.getvalue(), (time.perf_counter() - started) * 1000

	try:
		with fixtures.scratch_root() as root:
			w = json.dumps({"tool_name": "Write", "cwd": root, "session_id": "s",
							"tool_input": {"file_path": os.path.join(root, "tools", "tickets", "serve.py"), "content": "x"}})
			code, out, ms = call(write_guard, root, w)
			rows = rows_of(root)
			ok(code in (0, None) and not out and len(rows) == 1 and rows[0]["verdict"] == FORK
			   and rows[0]["mode"] == "log-only" and rows[0]["targets"] == ["tools/tickets/serve.py"],
			   "write_guard end to end: exit %r out %r rows %r" % (code, out[:60], rows))
			ok(ms < 1000, "write_guard took %d ms" % ms)
			b = json.dumps({"tool_name": "PowerShell", "cwd": root, "session_id": "s",
							"tool_input": {"command": "Set-Content tools\\tickets\\a.txt \"caf\u00e9\""}}, ensure_ascii=False)
			code, out, _ = call(shell_guard, root, b.encode("utf-8"))
			ok(code in (0, None) and not out and len(rows_of(root)) == 2, "shell_guard end to end (UTF-8 command)")
			code, out, _ = call(shell_guard, root, json.dumps({"tool_name": "Bash", "cwd": root,
															   "tool_input": {"command": "ls tools/tickets"}}))
			ok(not out and len(rows_of(root)) == 2, "shell_guard logged a read")
			code, out, _ = call(write_guard, root, "not json")
			ok(code in (0, None) and not out and len(rows_of(root)) == 2, "garbage input was not silent")
			code, out, _ = call(write_guard, root, "[" * 100000 + "]" * 100000)
			ok(code in (0, None) and not out and len(rows_of(root)) == 2, "deeply nested input was not silent")
			big = json.dumps({"tool_name": "Bash", "cwd": root, "session_id": "s",
							  "tool_input": {"command": huge}})
			code, out, ms = call(shell_guard, root, big)
			rows = rows_of(root)
			ok(code in (0, None) and not out and len(rows) == 3 and rows[-1]["partial"] is True
			   and rows[-1]["targets"] == ["tools/tickets/serve.py"] and len(rows[-1]["sample"][0]) <= output.EXCERPT_MAX
			   and ms < 3000, "shell_guard on a 2 MB command: exit %r, %d ms, row %r" % (code, ms, rows[-1:]))
			code, out, _ = call(write_guard, root, w, enforce=frozenset({RULE}))
			try:
				spec = json.loads(out).get("hookSpecificOutput", {})
			except ValueError:
				spec = {}
			ok(spec.get("hookEventName") == "PreToolUse" and spec.get("permissionDecision") == "deny"
			   and "T2:" in spec.get("permissionDecisionReason", ""), "enforced write_guard output: %r" % out[:120])
			ok([r["mode"] for r in rows_of(root)] == ["log-only", "log-only", "log-only", "enforce"], "logged modes")
	finally:
		sys.stdin, sys.stdout = real_stdin, real_stdout
		if real_env is None:
			os.environ.pop("CLAUDE_PROJECT_DIR", None)
		else:
			os.environ["CLAUDE_PROJECT_DIR"] = real_env
	return ck.result()


def dict_root(root, write_config, cfg):
	"""Write `cfg` as the project's config.json and return `root` (a self-test helper)."""
	write_config(root, cfg)
	return root
