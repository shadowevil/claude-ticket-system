"""Run the prompt rules over recorded session transcripts and count what they would do - the measurement
before any rule is enforced.

	python .claude/hooks/tickets/replay.py                        # this project's transcripts
	python .claude/hooks/tickets/replay.py --show T1              # every T1 quiet-spell prompt, with excerpts
	python .claude/hooks/tickets/replay.py --show T1 --sample 20  # a random sample instead
	python .claude/hooks/tickets/replay.py --root <dir> --root <dir> --sweep   # other corpora, threshold sweep
	python .claude/hooks/tickets/replay.py --probe                # time the live health probe (read-only GETs)
	python .claude/hooks/tickets/replay.py --show T2              # every write into the ticket system's source
	python .claude/hooks/tickets/replay.py --show T2-miss         # commands that mention it but yield no target
	python .claude/hooks/tickets/replay.py --root <dir> --project-root <repo>  # another project's transcripts

Transcripts live in ~/.claude/projects/<the project path, every non-alphanumeric character as '-'>/. The
excerpts --show prints go through the same secret masking as the hit log's samples.

T2 (the ticket system's source is not changed locally) replays every Write/Edit/MultiEdit/NotebookEdit/Bash/
PowerShell call, sub-agent transcripts included (PreToolUse fires there too), once per tool_use id, through
the live rule's protected_targets() with the record's own `cwd`. The ticket store's state at the time of each
call is not in the transcript, so a hit is counted as a write into the system's source, tied or not; the tied
check is proven by the self-test. `T2-miss` lists the shell commands that mention tools/tickets/,
skills/tickets/ or hooks/tickets/ but yield no protected target - the parser's blind spot, for hand-checking.

Offline, so it differs from the live hook in one way: the viewer's health at the time of each prompt is
not in the transcript, so every quiet-spell prompt is counted as a would-probe, and the T1 "hit" count is
the upper bound of reminders (the live hook reminds only when the probe fails). As a proxy for whether a
reminder would have been needed, each quiet-spell prompt is marked `checked` when the session's own tool
calls before the next prompt touched the viewer (serve.py, /api/health or the port).

Prompts are the main-session user records (sub-agent transcripts have no UserPromptSubmit), classified by
hooklib/prompt_clock.classify() on the text alone, exactly as the live hook sees them; where a record
carries `origin.kind`, the replay reports how often the text classifier agrees with it. The clock runs
per root (one project), in timestamp order across all its sessions, like the live per-project clock.
Reads transcripts only; writes nothing. Output is ASCII."""
import argparse
import collections
import json
import os
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hooklib import output  # noqa: E402
from hooklib import paths  # noqa: E402
from hooklib import prompt_clock  # noqa: E402
from hooklib import viewer  # noqa: E402
from rules.prompt import t1_viewer_after_quiet_spell as t1  # noqa: E402
from rules.write import t2_ticket_system_fork as t2  # noqa: E402

TOOL_NAMES = t2.FILE_TOOLS + t2.SHELL_TOOLS
SOURCE_MENTIONS = ("tools/tickets", "tools\\tickets", "skills/tickets", "skills\\tickets", "hooks/tickets",
				   "hooks\\tickets")

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def default_root():
	"""This project's transcript folder: the project path with every non-alphanumeric character as '-'."""
	root = paths.project_root()
	name = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in root)
	return os.path.join(PROJECTS, name)


def ascii(s):
	return str(s).encode("ascii", "backslashreplace").decode("ascii")


def shown(text, limit):
	"""A transcript excerpt as printed: secrets masked (as in the hit log), whitespace collapsed, ASCII."""
	return output.sample_text(text, limit)


def epoch(ts):
	try:
		return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
	except (AttributeError, ValueError):
		return None


def record_text(content):
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
	return ""


def is_tool_result(content):
	return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def scan(root, since):
	"""(prompts, tool_uses): prompts [(t, session, text, origin_kind, file)], tool_uses {session: [(t, blob)]}."""
	prompts, tools = [], collections.defaultdict(list)
	for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
		path = os.path.join(root, name)
		if not name.endswith(".jsonl") or not os.path.isfile(path):
			continue  # main transcripts only; <session>/subagents/*.jsonl are sub-agents
		with open(path, encoding="utf-8", errors="replace") as fh:
			for line in fh:
				if '"user"' not in line and '"tool_use"' not in line:
					continue
				try:
					rec = json.loads(line)
				except ValueError:
					continue
				if rec.get("isSidechain"):
					continue
				t = epoch(rec.get("timestamp"))
				if t is None or (since and rec.get("timestamp", "")[:10] < since):
					continue
				session = rec.get("sessionId") or name
				content = (rec.get("message") or {}).get("content")
				if rec.get("type") == "assistant" and isinstance(content, list):
					for block in content:
						if isinstance(block, dict) and block.get("type") == "tool_use":
							tools[session].append((t, json.dumps(block.get("input") or {})))
					continue
				if rec.get("type") != "user" or is_tool_result(content):
					continue
				origin = rec.get("origin") if isinstance(rec.get("origin"), dict) else {}
				kind = origin.get("kind")
				text = record_text(content)
				if kind is None:
					# older records carry no origin: skip injected meta records and local command echoes
					if rec.get("isMeta") or text.lstrip().startswith(("<local-command", "Caveat:")):
						continue
				elif kind not in ("human", "peer", "task-notification"):
					continue
				prompts.append((t, session, text, kind, name))
	prompts.sort(key=lambda p: p[0])
	for lst in tools.values():
		lst.sort()
	return prompts, tools


def replay_clock(prompts, threshold):
	"""[(prompt, gap_s, quiet)] for every conversation prompt, the clock moved as the live hook moves it."""
	out = []
	previous = None
	for p in prompts:
		kind = prompt_clock.classify(p[2])
		if not prompt_clock.is_conversation(kind):
			continue
		gap = prompt_clock.gap_seconds(previous, p[0])
		out.append((p, gap, t1.quiet_spell(gap, threshold)))
		previous = {"ts": p[0], "session": p[1]}
	return out


def viewer_touched(tools, session, start, end, port):
	needles = ("serve.py", "/api/health", str(port))
	return any(start <= t < end and any(n in blob for n in needles) for t, blob in tools.get(session, ()))


def run_probe(n):
	cfg = viewer.load_config(paths.project_root())
	if cfg is None:
		print("probe: this project has no viewer config")
		return
	print("probe: %s (config from %s), timeout %.0f ms" % (viewer.health_url(cfg), cfg["source"],
														   viewer.PROBE_TIMEOUT_S * 1000))
	for label, port in (("configured port", cfg["port"]),):
		res = [viewer.probe(port, cfg["service"], cfg["health_path"]) for _ in range(n)]
		ms = sorted(r[1] for r in res)
		print("  %-16s states %s  min %d ms  median %d ms  max %d ms  (n=%d)"
			  % (label, dict(collections.Counter(r[0] for r in res)), ms[0], ms[len(ms) // 2], ms[-1], n))


def tool_calls(root, since):
	"""Yield (ts, session, tool name, input, cwd, agent_id) for every Write/Edit/MultiEdit/NotebookEdit/Bash/
	PowerShell call under `root`, sub-agent transcripts included, once per tool_use id."""
	seen = set()
	for dirpath, _dirs, files in os.walk(root):
		for name in sorted(files):
			if not name.endswith(".jsonl"):
				continue
			with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as fh:
				for line in fh:
					if '"tool_use"' not in line:
						continue
					try:
						rec = json.loads(line)
					except ValueError:
						continue
					ts = rec.get("timestamp") or ""
					if since and ts[:10] < since:
						continue
					for block in (rec.get("message") or {}).get("content") or []:
						if not isinstance(block, dict) or block.get("type") != "tool_use":
							continue
						if block.get("name") not in TOOL_NAMES or block.get("id") in seen:
							continue
						seen.add(block.get("id"))
						yield (ts, rec.get("sessionId") or name, block.get("name"), block.get("input") or {},
							   rec.get("cwd"), rec.get("agentId"))


def replay_t2(root, project_root, since, show, sample, limit, seed, tool_dir=None):
	if tool_dir:
		dirs = (tool_dir.replace("\\", "/").strip("/").lower(), t2.SKILL_DIR, t2.HOOKS_DIR)
	else:
		dirs, notes = t2.tool_dirs(project_root)
		for key, why in notes:
			print("  T2 config: %s %s (ignored)" % (key, why))
	calls = shell_calls = 0
	hits, misses, timings = [], [], []
	for ts, session, tool, ti, cwd, agent in tool_calls(root, since):
		calls += 1
		event = {"tool_name": tool, "cwd": cwd or project_root, "tool_input": ti}
		t0 = time.perf_counter()
		found = t2.protected_targets(event, project_root, dirs)
		timings.append(time.perf_counter() - t0)
		cmd = ti.get("command") or ""
		if tool in t2.SHELL_TOOLS:
			shell_calls += 1
		if found:
			hits.append((ts, session, tool, agent, found, cmd or ti.get("file_path") or ti.get("notebook_path") or ""))
		elif cmd and any(m in cmd.lower() for m in SOURCE_MENTIONS):
			misses.append((ts, session, tool, agent, cmd))
	st = sorted(timings) or [0.0]
	print("  T2 tool source: %s" % ", ".join(dirs))
	print("  T2: %d write/shell calls (%d shell), %d write into the tool's source, %d shell commands mention it "
		  "with no target; per-call %.3f ms median, %.3f ms max"
		  % (calls, shell_calls, len(hits), len(misses), st[len(st) // 2] * 1000, st[-1] * 1000))
	by_path = collections.Counter(t[2] for h in hits for t in h[4])
	for path, n in by_path.most_common(12):
		print("    %4d  %s" % (n, ascii(path)))
	for label, rows in (("T2", hits), ("T2-miss", misses)):
		if show != label:
			continue
		rows = list(rows)
		if sample:
			random.Random(seed).shuffle(rows)
			rows = sorted(rows[:sample], key=lambda r: r[0])
		else:
			rows = rows[:limit]
		print("\n  %s: showing %d" % (label, len(rows)))
		for row in rows:
			ts, session, tool, agent = row[:4]
			what = ", ".join("%s %s" % (t[0], t[2]) for t in row[4]) if label == "T2" else ""
			text = row[5] if label == "T2" else row[4]
			print("    %s %-10s %-8s %-4s %s | %s" % (ts[:16], tool, ascii(session)[:8], "sub" if agent else "main",
												   ascii(what)[:70], shown(text, 110)))


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--root", action="append", help="transcript directory (repeatable); default: this project's")
	ap.add_argument("--since", help="YYYY-MM-DD")
	ap.add_argument("--threshold-min", type=float, default=t1.QUIET_SPELL_S / 60.0)
	ap.add_argument("--sweep", action="store_true", help="also count quiet spells at other thresholds")
	ap.add_argument("--show", help="print hits for this rule id (T1)")
	ap.add_argument("--sample", type=int, help="print a random sample of this many hits")
	ap.add_argument("--limit", type=int, default=50)
	ap.add_argument("--seed", type=int, default=7)
	ap.add_argument("--probe", type=int, nargs="?", const=5, help="time N live health probes (read-only GET)")
	ap.add_argument("--project-root", help="the repo the transcripts belong to (T2); default: this project")
	ap.add_argument("--tool-dir", help="the ticket tool's folder in that repo (T2); default: read from the project")
	args = ap.parse_args()

	if args.probe:
		run_probe(args.probe)
		return
	threshold = args.threshold_min * 60.0
	cfg = viewer.load_config(paths.project_root()) or {"port": 0}
	project_root = os.path.normpath(args.project_root) if args.project_root else paths.project_root()
	for root in args.root or [default_root()]:
		replay_t2(root, project_root, args.since, args.show, args.sample, args.limit, args.seed, args.tool_dir)
		started = time.perf_counter()
		prompts, tools = scan(root, args.since)
		sessions = {p[1] for p in prompts}
		by_origin = collections.Counter(p[3] or "(none)" for p in prompts)
		agree = sum(1 for p in prompts if p[3] and prompt_clock.origin_kind(prompt_clock.classify(p[2])) == p[3])
		with_origin = sum(1 for p in prompts if p[3])
		classified = collections.Counter(prompt_clock.classify(p[2]) for p in prompts)
		clock = replay_clock(prompts, threshold)
		quiet = [(p, g) for p, g, q in clock if q]
		first = sum(1 for _p, g in quiet if g is None)
		next_prompt = {}
		for i, (p, _g, _q) in enumerate(clock):
			later = [c[0][0] for c in clock[i + 1:] if c[0][1] == p[1]]
			next_prompt[id(p)] = later[0] if later else float("inf")
		checked = sum(1 for p, _g in quiet if viewer_touched(tools, p[1], p[0], next_prompt[id(p)], cfg["port"]))
		print("root: %s" % ascii(os.path.basename(root)))
		print("  prompt records: %d in %d session(s), origin kinds %s"
			  % (len(prompts), len(sessions), dict(by_origin)))
		print("  text classifier agrees with origin.kind on %d of %d records; classified %s"
			  % (agree, with_origin, dict(classified)))
		print("  conversation prompts (human + peer, the clock): %d" % len(clock))
		print("  T1 quiet spells >= %.0f min: %d (%d with no earlier prompt on record), %.1f%% of prompts; "
			  "viewer touched before the next prompt: %d  [%.0f ms]"
			  % (args.threshold_min, len(quiet), first, 100.0 * len(quiet) / max(1, len(clock)), checked,
				 (time.perf_counter() - started) * 1000))
		if args.sweep:
			for m in (10, 15, 20, 30, 45, 60, 120, 240):
				n = sum(1 for _p, _g, q in replay_clock(prompts, m * 60.0) if q)
				print("    threshold %3d min: %4d quiet spells" % (m, n))
		if args.show == "T1":
			rows = list(quiet)
			if args.sample:
				random.Random(args.seed).shuffle(rows)
				rows = sorted(rows[:args.sample], key=lambda r: r[0][0])
			else:
				rows = rows[:args.limit]
			print("\n  T1: %d quiet-spell prompt(s), showing %d" % (len(quiet), len(rows)))
			for p, g in rows:
				touched = viewer_touched(tools, p[1], p[0], next_prompt[id(p)], cfg["port"])
				print("    %s  gap %-9s %-6s %-9s %s  %s" % (
					datetime.fromtimestamp(p[0]).strftime("%Y-%m-%d %H:%M"),
					"none" if g is None else "%.0f min" % (g / 60), prompt_clock.classify(p[2]),
					"checked" if touched else "-", ascii(p[1])[:8], shown(p[2], 90)))


if __name__ == "__main__":
	main()
