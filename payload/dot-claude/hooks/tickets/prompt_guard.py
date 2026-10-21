"""UserPromptSubmit. A prompt arriving is the start (or resumption) of work, so it runs rules/prompt/: T1,
the ticket viewer is running when work resumes after a quiet spell (log-only; enforcing is the user's
call). Every conversation prompt moves the project's prompt clock (build/hooks/tickets/prompt_clock.json)
first.

Rows go to build/hooks/tickets/hits.jsonl. Only an id in hooklib/policy.py ENFORCE (none as shipped) prints
anything: an additionalContext reminder, never a block. Any error prints nothing and exits 0.

	python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test [--scratch <dir>]   (runs every rule
	module's self-test; it writes nothing inside this folder, so a staged copy can be tested before install,
	and nothing in its project unless --scratch puts its throwaway folders in <dir> there, outside this folder
	and .claude/tickets, instead of in the system temp folder)
"""
import os
import sys

# python -I leaves the script's own directory off sys.path; hooklib/ and rules/ import from it, first, so a
# project's own .claude/hooks/hooklib/ can never be picked up instead
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def rule_modules():
	"""RULE_MODULES: each action's rule modules, in order. The one list: the runner and the self-test both
	read it. A function, not a module constant, so a broken rule import stays inside main()'s fail-open."""
	from rules.prompt import t1_viewer_after_quiet_spell
	return {"prompt": (t1_viewer_after_quiet_spell,)}


def main(enforce=None, now=None):
	try:
		from hooklib import runner
		runner.main(rule_modules(), enforce, now)
	except SystemExit:
		raise
	except BaseException:
		pass  # a broken rule library must never block, print or fail a prompt
	sys.exit(0)


if __name__ == "__main__":
	if "--self-test" in sys.argv:
		sys.dont_write_bytecode = True  # no __pycache__ in a staged copy, even without -B
		from hooklib import selftest
		sys.exit(selftest.main())
	main()
