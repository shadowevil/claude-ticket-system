"""PreToolUse Bash|PowerShell. A typed command line can write (redirects, copies, moves, in-place edits,
deletes), so the call runs rules/write/: T2, the ticket system's source is not changed locally (log-only;
enforcing is the user's call). Targets come from hooklib/shell.py, a static parser, linear in the command's
length and bounded; writes made inside an interpreter (python -c, a script) are not seen.

Rows go to build/hooks/tickets/hits.jsonl. Only an id in hooklib/policy.py ENFORCE (none as shipped) prints
anything: one PreToolUse deny merging every rule's reason. Any error prints nothing and exits 0.

	python -I -S -B .claude/hooks/tickets/shell_guard.py --self-test [--scratch <dir>]   (runs every rule
	module's self-test; it writes nothing inside this folder, so a staged copy can be tested before install,
	and nothing in its project unless --scratch puts its throwaway folders in <dir> there, outside this folder
	and .claude/tickets, instead of in the system temp folder)
"""
import os
import sys

# python -I leaves the script's own directory off sys.path; hooklib/ and rules/ import from it, first, so a
# project's own .claude/hooks/hooklib/ can never be picked up instead
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACTIONS_FOR_TOOL = {"Bash": ("write",), "PowerShell": ("write",)}


def rule_modules():
	"""RULE_MODULES: each action's rule modules, in order (the runner and the self-test both read it)."""
	from rules.write import t2_ticket_system_fork
	return {"write": (t2_ticket_system_fork,)}


def main(enforce=None):
	try:
		from hooklib import runner
		runner.main_tool(ACTIONS_FOR_TOOL, rule_modules(), enforce)
	except SystemExit:
		raise
	except BaseException:
		pass  # a broken rule library must never block, print or fail a tool call
	sys.exit(0)


if __name__ == "__main__":
	if "--self-test" in sys.argv:
		sys.dont_write_bytecode = True  # no __pycache__ in a staged copy, even without -B
		from hooklib import selftest
		sys.exit(selftest.main())
	main()
