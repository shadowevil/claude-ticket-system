"""Shared library for the ticket-system hooks (.claude/hooks/tickets/). Stdlib only, split by concern:

	paths.py         the project root, and the gitignored runtime directory build/hooks/tickets/
	jsonfile.py      reading a JSON file the hooks do not own, never raising (bad or deeply nested -> None)
	project.py       the ticket system's settings: .claude/tickets/config.json, the tool's folder, the
					 default service marker
	output.py        the hit log (build/hooks/tickets/hits.jsonl), breadcrumbs, secret-masked samples, and
					 the hook's JSON output
	policy.py        ENFORCE - which rule ids act (inject or deny); every other id is log-only
	prompt_clock.py  the per-project prompt clock (build/hooks/tickets/prompt_clock.json)
	viewer.py        the project's ticket viewer: its port and service marker, and the health probe
	shell.py         static write/delete targets of a Bash/PowerShell command, linear and bounded
	ticket_store.py  read-only view of the ticket store (active tickets by requester)
	runner.py        the UserPromptSubmit flow and the PreToolUse flow
	fixtures.py      self-test fixtures (Checker, scratch root, stub projects, loopback servers)
	selftest.py      the `--self-test` collector

The folder is imported as `hooklib` with .claude/hooks/tickets/ first on sys.path (each entry point puts it
there), so a project's own .claude/hooks/hooklib/ is never picked up. Nothing here holds a rule; rules live
in rules/<action>/."""
