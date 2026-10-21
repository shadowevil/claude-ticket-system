"""The two hook flows every entry point shares.

main_prompt (UserPromptSubmit): classify the prompt, move the project's prompt clock (once per prompt, before
any rule runs), run rules/prompt/ with a shared context, log every row, and print one additionalContext
merging the texts of the rules in ENFORCE. It never blocks a prompt.

main_tool (PreToolUse): classify the call into its action(s) (the entry point's ACTIONS_FOR_TOOL), run those
actions' rule modules, log every row, and print one PreToolUse deny merging the reasons of the rules in
ENFORCE (a PreToolUse hook returns one decision, so two denying rules are joined, never overwritten).

A rule module offers evaluate_prompt(event, ctx) or evaluate_tool(event, ctx) -> [hit, ...],
log_rows(event, ctx, hits, ms, enforce=None) and decide(event, ctx, hits, enforce=None) -> text or None
(context text for a prompt rule, a deny reason for a tool rule). `enforce` None means hooklib/policy.py
ENFORCE; the same set drives the row's mode and decide(). Each module only ever sees its own hits.

The event is read from stdin as UTF-8 bytes (never the cp1252 console codepage). Fails open: any error
prints nothing and exits 0; a module that raises is skipped and leaves one breadcrumb."""
import json
import sys
import time

from hooklib import output
from hooklib import paths
from hooklib import prompt_clock


def read_event():
	event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
	return event if isinstance(event, dict) else {}


def build_context(event, now=None):
	"""The shared context for one prompt, after moving the clock; None for a prompt that is not
	conversation (a task notification or a sub-agent report), which runs no rule and leaves the clock alone."""
	root = paths.project_root(event)
	kind = prompt_clock.classify(event.get("prompt"))
	if not prompt_clock.is_conversation(kind):
		return None
	now = time.time() if now is None else now
	previous = prompt_clock.advance(root, now, event.get("session_id"), kind)
	return {"root": root, "now": now, "kind": kind, "previous": previous,
			"gap_s": prompt_clock.gap_seconds(previous, now),
			"new_session": bool(previous) and previous.get("session") != event.get("session_id")}


def isolated(mod, phase, event, ctx):
	fn = getattr(mod, phase, None)
	try:
		return (fn(event, ctx) or []) if fn else []
	except Exception as exc:
		output.breadcrumb(ctx["root"], mod, phase, exc, event)
		return []


def run(event, ctx, modules, enforce=None, phase="evaluate_prompt"):
	"""(rows, texts): every module's log rows and, for ids being enforced, its text."""
	rows, texts = [], []
	for mod in modules:
		started = time.perf_counter()
		hits = isolated(mod, phase, event, ctx)
		ms = int(round((time.perf_counter() - started) * 1000))
		if not hits:
			continue
		try:
			rows.extend(mod.log_rows(event, ctx, hits, ms, enforce))
		except Exception as exc:
			output.breadcrumb(ctx["root"], mod, "log_rows", exc, event)
		try:
			texts.append(mod.decide(event, ctx, hits, enforce))
		except Exception as exc:
			output.breadcrumb(ctx["root"], mod, "decide", exc, event)
	return rows, texts


def write_rows(root, rows):
	if rows:
		try:
			output.append_rows(root, rows)
		except Exception:
			pass


def main(rule_modules, enforce=None, now=None):
	"""UserPromptSubmit entry: read the event; log; print context only for an id being enforced."""
	try:
		event = read_event()
		ctx = build_context(event, now)
		if ctx is not None:
			rows, texts = run(event, ctx, rule_modules.get("prompt", ()), enforce)
			write_rows(ctx["root"], rows)
			verdict = output.prompt_context(texts)
			if verdict is not None:
				output.print_json(verdict)
	except Exception:
		pass
	sys.exit(0)


main_prompt = main


def modules_for(tool, actions_for_tool, rule_modules):
	"""Every rule module this tool call's action(s) select, in order, each at most once."""
	seen = []
	for action in actions_for_tool.get(tool, ()):
		for mod in rule_modules.get(action, ()):
			if mod not in seen:
				seen.append(mod)
	return seen


def main_tool(actions_for_tool, rule_modules, enforce=None):
	"""PreToolUse entry: read the event; log; deny only for an id being enforced."""
	try:
		event = read_event()
		modules = modules_for(str(event.get("tool_name") or ""), actions_for_tool, rule_modules)
		if modules:
			ctx = {"root": paths.project_root(event)}
			rows, reasons = run(event, ctx, modules, enforce, phase="evaluate_tool")
			write_rows(ctx["root"], rows)
			verdict = output.deny(reasons)
			if verdict is not None:
				output.print_json(verdict)
	except Exception:
		pass
	sys.exit(0)
