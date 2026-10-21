"""T1 - the ticket viewer is running when work resumes after a quiet spell (RULES.md "T1"). Log-only: never
in ENFORCE; enforcing is the user's call.

User rule, 2026-09-30: "Make sure that your ticket system is running anytime you detect a long period of no
conversation and work is just starting". The viewer runs as a visible background task of the session
(.claude/docs/tickets.md, "The viewer").

On a conversation prompt (human or peer, not a task notification or a sub-agent report) that arrives
QUIET_SPELL_S or more after the previous one in this project (or with none on record), probe the project's
viewer /api/health (the pid file's port first, then the configured one). Viewer down, or its port held by
something else -> "remind"; viewer up -> "ok" (logged, nothing to do). A hook cannot start the viewer as the
session's visible background task, so the enforced form is a reminder injected as additionalContext, never
a block.

	evaluate_prompt(event, ctx)  -> [hit] on a quiet-spell prompt in a project with a viewer, else []
"""
import json
import os
import sys
import time

from hooklib import output
from hooklib import prompt_clock
from hooklib import viewer
from hooklib.policy import ENFORCE, MODE

RULE = "T1"

# "A long period of no conversation": 30 minutes since the previous conversation prompt in this project.
# Calibrated on recorded transcripts (RULES.md "T1", measured evidence): past the p90 of the gap between
# prompts in every corpus with real volume (19 to 28 min), so an ordinary pause between turns rarely reaches
# it, while a break, a meal or a restart does.
QUIET_SPELL_S = 30 * 60
SAMPLE_MAX = 80

REMIND = "remind"
OK = "ok"

MSG = {
	RULE: "The ticket viewer is not running and work is resuming after a quiet spell. User rule 2026-09-30: "
		  "\"Make sure that your ticket system is running anytime you detect a long period of no conversation "
		  "and work is just starting\". Before starting the work, start it as a visible background task "
		  "(.claude/docs/tickets.md, The viewer): `python {script} --stop`, then "
		  "`python -u {script} --foreground` with run_in_background.",
}


def quiet_spell(gap_s, threshold=QUIET_SPELL_S):
	"""True when this prompt ends a quiet spell: no previous prompt on record, or `threshold` seconds or
	more since it. A negative gap (clock moved back) is not a quiet spell."""
	if gap_s is None:
		return True
	return gap_s >= threshold


def judge(gap_s, kind, health, threshold=QUIET_SPELL_S):
	"""REMIND, OK or None (the rule does not apply). `health` is None when the project has no viewer."""
	if not prompt_clock.is_conversation(kind) or not quiet_spell(gap_s, threshold) or health is None:
		return None
	return REMIND if health in (viewer.DOWN, viewer.FOREIGN) else OK


def evaluate_prompt(event, ctx):
	if not prompt_clock.is_conversation(ctx.get("kind")) or not quiet_spell(ctx.get("gap_s")):
		return []
	cfg = viewer.load_config(ctx["root"])
	if cfg is None:
		return []
	health, probe_ms, port = viewer.check(cfg)
	verdict = judge(ctx.get("gap_s"), ctx.get("kind"), health)
	if verdict is None:
		return []
	return [{"verdict": verdict, "health": health, "probe_ms": probe_ms, "port": port,
			 "gap_s": ctx.get("gap_s"), "cfg": cfg}]


def gap_text(gap_s):
	return "no earlier prompt on record" if gap_s is None else "%d min since the last prompt" % int(gap_s // 60)


def reminder_text(hit):
	cfg = hit["cfg"]
	state = "does not answer" if hit["health"] == viewer.DOWN else "is held by something that is not the viewer"
	head = "T1: %s (threshold %d min) and %s %s (service %s)." % (
		gap_text(hit["gap_s"]), QUIET_SPELL_S // 60, viewer.health_url(cfg, hit.get("port")), state, cfg["service"])
	return output.ascii_text(head + " " + MSG[RULE].format(script=cfg["script"]))


def mode_for(enforce=None):
	"""The mode this call actually runs in: "enforce" when T1 is in the enforce set used, else MODE."""
	return "enforce" if RULE in (ENFORCE if enforce is None else enforce) else MODE


def log_rows(event, ctx, hits, ms, enforce=None):
	rows = []
	mode = mode_for(enforce)
	for hit in hits:
		cfg = hit["cfg"]
		remind = hit["verdict"] == REMIND
		rows.append({
			"ts": output.now_iso(), "mode": mode, "rule": RULE,
			"event": "UserPromptSubmit", "verdict": hit["verdict"],
			"would": ("injected the viewer reminder" if mode == "enforce" else "inject the viewer reminder")
			if remind else "nothing (viewer up)",
			"gap_min": None if hit["gap_s"] is None else round(hit["gap_s"] / 60.0, 1),
			"threshold_min": QUIET_SPELL_S // 60, "health": hit["health"], "probe_ms": hit["probe_ms"],
			"port": hit.get("port", cfg["port"]), "ports": cfg.get("ports"), "service": cfg["service"],
			"config": cfg["source"], "kind": ctx.get("kind"), "new_session": ctx.get("new_session"),
			"session": event.get("session_id"), "sample": [output.sample_text(event.get("prompt") or "", SAMPLE_MAX)],
			"ms": ms, "msg": MSG[RULE].format(script=cfg["script"]) if remind else "",
		})
	return rows


def decide(event, ctx, hits, enforce=None):
	"""The reminder text for a REMIND hit once "T1" is in the enforce set (default ENFORCE), else None.
	Never a block."""
	if mode_for(enforce) != "enforce":
		return None
	texts = [reminder_text(h) for h in hits if h.get("verdict") == REMIND]
	return "\n".join(texts) or None


# (gap seconds or None, prompt kind, viewer health or None for "no viewer", expected verdict)
H, P, A, TN = prompt_clock.HUMAN, prompt_clock.PEER, prompt_clock.AGENT_REPORT, prompt_clock.TASK_NOTIFICATION
T1_CASES = [
	(None, H, viewer.DOWN, REMIND),             # nothing on record (first prompt after install): work starting
	(QUIET_SPELL_S, H, viewer.DOWN, REMIND),    # exactly the threshold
	(2 * 3600, H, viewer.DOWN, REMIND),         # back after two hours
	(3 * 86400, H, viewer.DOWN, REMIND),        # back after a weekend
	(3600, H, viewer.FOREIGN, REMIND),          # port held by something else: serve.py will refuse, say so
	(3600, P, viewer.DOWN, REMIND),             # a peer session's ticket request after a quiet spell
	(None, P, viewer.FOREIGN, REMIND),
	(QUIET_SPELL_S - 1, H, viewer.DOWN, None),  # one second short: an ordinary pause
	(60, H, viewer.DOWN, None),                 # mid-conversation, even with the viewer down (not this rule)
	(0, H, viewer.DOWN, None),
	(-600, H, viewer.DOWN, None),               # clock moved back: not a quiet spell
	(3600, H, viewer.UP, OK),                   # viewer answering: nothing to do
	(None, H, viewer.UP, OK),
	(3600, TN, viewer.DOWN, None),              # a background task reporting back is not conversation
	(None, TN, viewer.DOWN, None),
	(3600, A, viewer.DOWN, None),               # a sub-agent's report: work already running, not starting
	(3600, H, None, None),                      # project without a viewer: silent
]

CLASSIFY_CASES = [
	("fix the build", H), ("/tickets list", H), ("  <task-notification>\n<task-id>x", TN),
	("Another Claude session sent a message:\n<cross-session-message from=x>", P),
	("<cross-session-message from=x>hi</cross-session-message>", P),
	("Another Claude session sent a message:\n<agent-message from=\"a1\">Round 3</agent-message>", A),
	("<agent-message from=\"a1\">done</agent-message>", A),
	("Another Claude session sent a message", P),
	("please read <task-notification> docs", H), ("", H), (None, H),
]


def run_self_test():
	"""(assertion count, [failure, ...]) for T1. The count is the number of checks actually made."""
	from hooklib import fixtures
	from hooklib import paths
	from hooklib import project
	ck = fixtures.Checker("T1")
	ok = ck.check

	for gap, kind, health, want in T1_CASES:
		got = judge(gap, kind, health)
		ok(got == want, "judge(%r, %r, %r) = %r, want %r" % (gap, kind, health, got, want))
	ok(any(c[3] == REMIND for c in T1_CASES) and any(c[3] != REMIND for c in T1_CASES),
	   "lacks a must-fire or must-not-fire case")

	# prompt classification, from the prompt text alone (all the live input carries)
	for text, want in CLASSIFY_CASES:
		ok(prompt_clock.classify(text) == want, "classify(%r) != %r" % (text, want))

	# the project root: CLAUDE_PROJECT_DIR, else cwd only when it is a project root (holds .claude/hooks/tickets)
	real_env = os.environ.get("CLAUDE_PROJECT_DIR")
	try:
		os.environ.pop("CLAUDE_PROJECT_DIR", None)
		with fixtures.scratch_root() as root:
			sub = os.path.join(root, "projects", "sub")
			os.makedirs(sub)
			ok(paths.project_root({"cwd": sub}) == paths.FILE_ROOT, "a plain subfolder cwd became the root")
			os.makedirs(os.path.join(root, ".claude", "hooks"))
			ok(paths.project_root({"cwd": root}) == paths.FILE_ROOT,
			   "a cwd with only a project's own .claude/hooks became the root")
			os.makedirs(os.path.join(root, ".claude", "hooks", "tickets"))
			ok(paths.project_root({"cwd": root}) == os.path.normpath(root), "a project-root cwd was not used")
			os.environ["CLAUDE_PROJECT_DIR"] = sub
			ok(paths.project_root({"cwd": root}) == os.path.normpath(sub), "CLAUDE_PROJECT_DIR did not win")
	finally:
		if real_env is None:
			os.environ.pop("CLAUDE_PROJECT_DIR", None)
		else:
			os.environ["CLAUDE_PROJECT_DIR"] = real_env

	# the viewer config: config.json first (1.1.0), a 1.0.0 serve.py's constants as the fallback, the service
	# marker derived from store_name last; the pid file's port is probed first
	old_text = ('default_port = 18990\nlan_bind = "0.0.0.0"\n'
				'# comment\nservice_marker = "demo-tickets"\nhealth_path = "/api/health"\n')
	ok(viewer.parse_serve_text(old_text) == {"port": 18990, "service": "demo-tickets", "health_path": "/api/health"},
	   "did not parse a 1.0.0 serve.py's constants: %r" % (viewer.parse_serve_text(old_text),))
	ok(viewer.parse_serve_text("def f():\n    default_port = 1\n") == {}, "parsed an indented (non-module) constant")
	ok(viewer.parse_serve_text(fixtures.SERVE_STUB_110) == {"health_path": "/api/health"},
	   "read a port from a 1.1.0 serve.py")
	for name, want in (("Demo", "demo-tickets"), ("My Board 2", "my-board-2-tickets"), ("  --X__y!! ", "x-y-tickets"),
					   ('Beta <Board> & "Co"', "beta-board-co-tickets"), ("Caf\u00e9 \u00c9t\u00e9", "caf-t-tickets"),
					   ("!!!", "tickets"), ("", None), ("   ", None), (None, None), (7, None)):
		ok(project.service_from_store_name(name) == want, "service_from_store_name(%r)" % (name,))
	with fixtures.scratch_root() as root:
		ok(viewer.load_config(root) is None, "found a viewer in an empty project")
		fixtures.write_stub_project(root, 18991, "demo-tickets")
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("port"), cfg.get("ports"), cfg.get("service"), cfg.get("source"), cfg.get("script"))
		   == (18991, [18991], "demo-tickets", "script", "tools/tickets/serve.py"),
		   "1.0.0 copy, config without viewer keys: %r" % (cfg,))
		fixtures.write_stub_project(root, 18991, "demo-tickets", config={"viewer_port": 18992, "id_prefix": "X-",
																		 "store_name": "Other Name"})
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("port"), cfg.get("service"), cfg.get("source")) == (18992, "demo-tickets", "config+script"),
		   "1.0.0 copy: config.json port, the script's marker over store_name: %r" % (cfg,))
		fixtures.write_stub_project(root, 18991, "x", config={"viewer_port": "18993", "viewer_service": " "})
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("port"), cfg.get("service")) == (18991, "x"), "accepted a malformed config.json value: %r" % (cfg,))
		fixtures.write_pid_file(root, 18994)
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("ports"), cfg.get("source")) == ([18994, 18991], "script+pidfile"),  # config.json values invalid
		   "the pid file's port was not probed first: %r" % (cfg,))
		fixtures.write_pid_file(root, 18991)
		ok((viewer.load_config(root) or {}).get("ports") == [18991], "a pid port equal to the configured one was probed twice")
		fixtures.write_pid_file(root, "18994")
		ok((viewer.load_config(root) or {}).get("ports") == [18991], "a malformed pid-file port was used")
		fixtures.write_text(os.path.join(root, "build", "tickets", "serve.pid"), "[" * 2000 + "]" * 2000)
		ok((viewer.load_config(root) or {}).get("ports") == [18991], "a deeply nested pid file broke the config")
		fixtures.write_text(os.path.join(root, ".claude", "tickets", "config.json"), "[" * 100000 + "]" * 100000)
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("port"), cfg.get("service")) == (18991, "x"), "a deeply nested config.json broke the config: %r" % (cfg,))
	with fixtures.scratch_root() as root:
		# 1.1.0 copy: everything from config.json, the tool found in src/tools/tickets, no constants in serve.py
		fixtures.write_stub_project_110(root, {"id_prefix": "TK-", "store_name": "Demo Board", "viewer_port": 18995})
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("port"), cfg.get("service"), cfg.get("source"), cfg.get("script"))
		   == (18995, "demo-board-tickets", "config+script+store_name", "src/tools/tickets/serve.py"),
		   "1.1.0 copy, marker from store_name: %r" % (cfg,))
		fixtures.write_config(root, {"id_prefix": "TK-", "store_name": "Demo Board", "viewer_port": 18995,
									 "viewer_service": "custom-svc", "viewer_health_path": "/health"})
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("service"), cfg.get("health_path"), cfg.get("source")) == ("custom-svc", "/health", "config"),
		   "1.1.0 copy, viewer_service and viewer_health_path: %r" % (cfg,))
		fixtures.write_config(root, {"id_prefix": "TK-", "store_name": "Demo Board"})
		ok(viewer.load_config(root) is None, "a 1.1.0 copy without viewer_port has no viewer to check")
		fixtures.write_config(root, {"store_name": "Demo", "viewer_port": 18996, "viewer_script": "elsewhere/serve.py",
									 "tool_dir": ".claude/tickets"})
		cfg = viewer.load_config(root) or {}
		ok((cfg.get("script"), cfg.get("service")) == ("elsewhere/serve.py", "demo-tickets"),
		   "viewer_script override: %r" % (cfg,))
		fixtures.write_config(root, {"store_name": "Demo", "viewer_port": 18996, "tool_dir": ".claude/tickets"})
		ok((viewer.load_config(root) or {}).get("script") == "src/tools/tickets/serve.py",
		   "a tool_dir overlapping the board was used for the viewer script")

	# the probe: up, foreign, not 200, closed port, a listener that never answers - each under 1 s
	probes = []
	with fixtures.http_server({"service": "svc-a", "pid": 1}) as port:
		probes.append(("up", viewer.probe(port, "svc-a"), viewer.UP))
		probes.append(("other marker", viewer.probe(port, "svc-b"), viewer.FOREIGN))
	with fixtures.http_server({"service": "svc-a"}, status=404) as port:
		probes.append(("status 404", viewer.probe(port, "svc-a"), viewer.FOREIGN))
	with fixtures.http_server(b"<html>not json</html>") as port:
		probes.append(("not json", viewer.probe(port, "svc-a"), viewer.FOREIGN))
	with fixtures.http_server(b"[" * 3000 + b"]" * 1000) as port:
		probes.append(("deeply nested json", viewer.probe(port, "svc-a"), viewer.FOREIGN))
	probes.append(("closed port", viewer.probe(fixtures.closed_port(), "svc-a"), viewer.DOWN))
	with fixtures.silent_listener() as port:
		probes.append(("silent listener", viewer.probe(port, "svc-a"), viewer.DOWN))
	for label, (state, ms), want in probes:
		ok(state == want, "probe %s: %s, want %s" % (label, state, want))
		ok(ms < 1000, "probe %s took %d ms (must stay well under 1 s)" % (label, ms))

	# check(): a viewer started with --port N is up although the configured port is closed; a stale pid file
	# falls back to the configured port
	with fixtures.http_server({"service": "svc-a"}) as port:
		base = {"service": "svc-a", "health_path": "/api/health", "port": fixtures.closed_port()}
		state, _ms, used = viewer.check(dict(base, ports=[port, base["port"]]))
		ok((state, used) == (viewer.UP, port), "viewer on the pid-file port read as %s on %s" % (state, used))
		state, _ms, used = viewer.check(dict(base, port=port, ports=[fixtures.closed_port(), port]))
		ok((state, used) == (viewer.UP, port), "a stale pid file hid the viewer on its configured port: %s" % state)
	state, ms, _used = viewer.check({"service": "s", "health_path": "/", "port": 1,
									 "ports": [fixtures.closed_port(), fixtures.closed_port()]})
	ok(state == viewer.DOWN and ms < 1000, "two closed ports: %s in %d ms" % (state, ms))

	# the clock: first prompt has no previous, the second sees the first, a corrupt file reads as none
	with fixtures.scratch_root() as root:
		ok(prompt_clock.advance(root, 1000.0, "s1") is None, "clock: a fresh project had a previous prompt")
		prev = prompt_clock.advance(root, 1060.0, "s1")
		ok(bool(prev) and prompt_clock.gap_seconds(prev, 1060.0) == 60.0,
		   "clock: second prompt did not see the first: %r" % (prev,))
		ok(os.path.isfile(os.path.join(root, "build", "hooks", "tickets", "prompt_clock.json")),
		   "clock: state is not under <root>/build/hooks/tickets/")
		with open(paths.state_path(root), "w", encoding="ascii") as fh:
			fh.write('{"ts": true}')
		ok(prompt_clock.read(root) is None, "clock: a corrupt state file was trusted")
		with open(paths.state_path(root), "w", encoding="ascii") as fh:
			fh.write("[" * 2000 + "]" * 2000)
		ok(prompt_clock.read(root) is None, "clock: a deeply nested state file was not read as none")

	# evaluate_prompt over a stub project: down -> remind, up -> ok, not quiet -> nothing, no viewer -> nothing
	with fixtures.scratch_root() as root:
		base = {"root": root, "kind": H, "previous": None, "new_session": False}
		ok(evaluate_prompt({}, dict(base, gap_s=3600)) == [], "fired in a project with no viewer")
		fixtures.write_stub_project(root, fixtures.closed_port(), "svc-a")
		hits = evaluate_prompt({}, dict(base, gap_s=3600))
		ok([h["verdict"] for h in hits] == [REMIND], "did not remind with the viewer down: %r" % (hits,))
		ok(evaluate_prompt({}, dict(base, gap_s=120)) == [], "probed on an ordinary pause")
		with fixtures.http_server({"service": "svc-a"}) as port:
			fixtures.write_pid_file(root, port)  # started with --port N: the configured port stays closed
			hits = evaluate_prompt({}, dict(base, gap_s=None))
			ok([(h["verdict"], h["port"]) for h in hits] == [(OK, port)],
			   "did not find the viewer on its pid-file port: %r" % (hits,))
	with fixtures.scratch_root() as root:
		base = {"root": root, "kind": H, "previous": None, "new_session": False}
		with fixtures.http_server({"service": "demo-board-tickets"}) as port:
			fixtures.write_stub_project_110(root, {"id_prefix": "TK-", "store_name": "Demo Board", "viewer_port": port})
			hits = evaluate_prompt({}, dict(base, gap_s=None))
			ok([(h["verdict"], h["port"]) for h in hits] == [(OK, port)],
			   "a 1.1.0 viewer answering with its derived marker was not up: %r" % (hits,))

	# log-only: the real ENFORCE never injects; a forced enforce yields ASCII text naming the fix
	fake = {"verdict": REMIND, "health": viewer.DOWN, "probe_ms": 1, "gap_s": 5400.0, "port": 18997,
			"cfg": {"port": 18997, "ports": [18997], "service": "demo-tickets", "health_path": "/api/health",
					"script": "tools/tickets/serve.py", "source": "script"}}
	ok(RULE not in ENFORCE, "T1 is in ENFORCE; enforcing is the user's call")
	ok(decide({}, {}, [fake]) is None and decide({}, {}, [fake], enforce=frozenset()) is None,
	   "would inject while log-only")
	text = decide({}, {}, [fake], enforce=frozenset({RULE})) or ""
	ok("serve.py --foreground" in text and "18997/api/health" in text and "90 min" in text,
	   "enforced text is missing the fix: %r" % text[:120])
	ok(all(ord(ch) < 128 for ch in text + MSG[RULE]), "text is not ASCII")
	ok(decide({}, {}, [dict(fake, verdict=OK)], enforce=frozenset({RULE})) is None, "injected with the viewer up")
	ok(log_rows({}, {}, [fake], 1)[0]["mode"] == MODE, "a log-only row did not say log-only")
	ok(log_rows({}, {}, [fake], 1, enforce=frozenset({RULE}))[0]["mode"] == "enforce",
	   "an enforced row did not say enforce")
	row = log_rows({"prompt": "use password=Tr0ub4dor&3 then resume"}, {}, [fake], 1)[0]
	ok("Tr0ub4dor" not in json.dumps(row) and row["sample"][0].startswith("use password=***"),
	   "a secret in the prompt reached the log sample: %r" % (row["sample"],))

	# prompt_guard end to end, in process, on a stub project: logs, prints nothing, never blocks
	import prompt_guard
	real_stdin, real_stdout = sys.stdin, sys.stdout

	def call(root, payload, enforce=None, now=None):
		os.environ["CLAUDE_PROJECT_DIR"] = root
		sys.stdin = fixtures.stdin_bytes(payload)
		sys.stdout = captured = __import__("io").StringIO()
		code = None
		started = time.perf_counter()
		try:
			prompt_guard.main(enforce, now)
		except SystemExit as exc:
			code = exc.code
		finally:
			sys.stdout = real_stdout
		return code, captured.getvalue(), (time.perf_counter() - started) * 1000

	def log_lines(root):
		try:
			with open(paths.hits_path(root), encoding="ascii") as fh:
				return [json.loads(line) for line in fh.read().splitlines()]
		except OSError:
			return []

	try:
		with fixtures.scratch_root() as root:
			fixtures.write_stub_project(root, fixtures.closed_port(), "svc-a")
			now = time.time()
			prompt_clock.write(root, {"ts": now - 3600, "session": "s0", "kind": H})
			ev = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "resume the codec work"}
			code, out, ms = call(root, json.dumps(ev), now=now)
			rows = log_lines(root)
			ok(code in (0, None) and not out and len(rows) == 1 and rows[0].get("verdict") == REMIND
			   and rows[0].get("mode") == "log-only" and rows[0].get("new_session") is True,
			   "end to end (quiet spell): exit %r, out %r, rows %r" % (code, out[:60], rows))
			ok(ms < 1000, "end to end took %d ms" % ms)
			code, out, _ = call(root, json.dumps(ev), now=now + 5)
			ok(not out and len(log_lines(root)) == 1, "end to end fired on a prompt 5 s later")
			tn = dict(ev, prompt="<task-notification>\n<task-id>b1</task-id>")
			call(root, json.dumps(tn), now=now + 7200)
			ok((prompt_clock.read(root) or {}).get("ts") == now + 5 and len(log_lines(root)) == 1,
			   "end to end: a task notification moved the clock or fired")
			code, out, _ = call(root, "not json", now=now + 9000)
			ok(code in (0, None) and not out, "end to end: garbage input was not silent")
			code, out, _ = call(root, "[" * 100000 + "]" * 100000, now=now + 9500)
			ok(code in (0, None) and not out, "end to end: deeply nested input was not silent")
			# UTF-8 bytes on stdin (a prompt with non-ASCII text) are read as UTF-8, never the console codepage
			utf8 = json.dumps(dict(ev, prompt="r\u00e9sum\u00e9 the \u2192 codec"), ensure_ascii=False).encode("utf-8")
			code, out, _ = call(root, utf8, now=now + 20000)
			rows = log_lines(root)
			ok(code in (0, None) and not out and len(rows) == 2 and rows[-1]["sample"][0].startswith("r?sum? the ? codec"),
			   "end to end: a UTF-8 prompt was misread: %r" % (rows[-1:],))
			code, out, _ = call(root, json.dumps(ev), enforce=frozenset({RULE}), now=now + 40000)
			try:
				spec = json.loads(out).get("hookSpecificOutput", {})
			except ValueError:
				spec = {}
			ok(spec.get("hookEventName") == "UserPromptSubmit" and "serve.py" in spec.get("additionalContext", "")
			   and "decision" not in out and "block" not in out, "end to end enforced output: %r" % out[:120])
			modes = [r.get("mode") for r in log_lines(root)]
			ok(modes == ["log-only", "log-only", "enforce"], "logged modes %r, want log-only x2 then enforce" % (modes,))
	finally:
		sys.stdin, sys.stdout = real_stdin, real_stdout
		if real_env is None:
			os.environ.pop("CLAUDE_PROJECT_DIR", None)
		else:
			os.environ["CLAUDE_PROJECT_DIR"] = real_env
	return ck.result()
