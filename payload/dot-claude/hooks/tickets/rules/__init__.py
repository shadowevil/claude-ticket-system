"""Rule modules, grouped by the action that triggers them:

	prompt/     a prompt arriving (UserPromptSubmit): what must hold when work starts or resumes (T1)
	write/      a write (file tools, and a shell command's redirects, copies, moves, in-place edits and
				deletes): where it may land (T2)

Other actions (delete/, read/, execute/, dispatch/) get their own directory when their first rule arrives. An
entry point classifies its event into action(s) and runs those modules. A new rule is a new module in its
action's directory plus one line in its entry point's rule_modules(); the self-test collector
(hooklib/selftest.py) reads the same rule_modules(), so there is no second list. Kept import-free: importing
one action must not load them all."""
