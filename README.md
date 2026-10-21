Paste this into Claude Code, opened in your project. (Or tell it: "Adopt the ticket system by following the README of https://github.com/shadowevil/claude-ticket-system".)

---

Install the Claude ticket system in this project, or upgrade the copy it already has. The ticket system is a JSON ticket board kept in the repo (`.claude/tickets/`): a stdlib-Python CLI that is the only writer, an authoring tool for agents, a read-only web viewer on localhost, and a `tickets` skill that tells Claude sessions how to use it. Work through these steps in order.

1. **Check the requirements: git, and Python 3.7 or newer (stdlib only).** Run `python --version` (or `python3 --version`; if only `python3` works, use it wherever the docs say `python`) and `git --version`. If both are there and Python is 3.7 or newer, go on and upgrade nothing; on Windows you may mention that 3.8 or newer is recommended (see `docs/ADOPTING.md` in the repo, once cloned), but act on it only if I ask. If either is missing, or Python is older than 3.7, stop and tell me; install or upgrade nothing unless I agree.

2. **Already installed?** Before you clone anything, look in this project, outside `.claude/scratch/`, for a `.claude/tickets/` folder or a `tickets.py` (usually in `src/tools/tickets/` or `tools/tickets/`). If either is there, this is an upgrade (step 4); otherwise an adoption (step 5).

3. **Get the release.** If I named a clone of https://github.com/shadowevil/claude-ticket-system, use it. Otherwise make sure this project's `.gitignore` has the line `.claude/scratch/`, then run, from the project root:
   `git clone https://github.com/shadowevil/claude-ticket-system .claude/scratch/pm/ticket-system/claude-ticket-system`
   (if that folder exists already, run `git -C <it> pull` instead). Call the clone `SRC` and use `.claude/scratch/pm/ticket-system/` as `SCRATCH`. `SRC/VERSION` names the release. Read SRC; never edit it.

4. **Upgrade** (an installed copy):
   - run `python SRC/tools/release.py identify .` from the project root;
   - read `SRC/docs/UPGRADING.md`, then follow its sections 1 and 2 and the path its section 3 gives for the version you run ("From a public clone"), step by step, with every check;
   - then go to step 6.

5. **Adopt.** Read `SRC/docs/ADOPTING.md`, then the files it names, whole and in order, starting with `SRC/docs/adopting/steps.md`. SRC is a clone, so skip the export in its step 2: `PAYLOAD` is `SRC/payload/`.
   - Step 1, the values: choose them yourself. `PREFIX` from the project's name (two to four capitals and a hyphen, such as `XY-`), `NAME` the project's name, `CLI_DIR` `src/tools/tickets` (or `tools/tickets` if the repo has no `src/`), `AREAS` and `AUTHORS` from how this project is organised, and a free `PORT` in 18000-19000, checked with the command in step 1. Show me all the values in one message and wait for my answer before its step 3 copies anything.
   - Follow every step literally and run every check. Where a check fails, stop and tell me what you saw.
   - Step 8 installs the skill only after a separate read-only agent has reviewed it. Do that.
   - The optional parts, migrating from another tracker (`SRC/docs/adopting/migrating.md`) and the ticket hooks (`SRC/docs/adopting/hooks.md`): ask me first. If Python is `python3` here and I want the hooks, replace `python` in the three commands of the hooks' `settings.snippet.json`.
   - Step 11: you adopted from a clone, so you report to me (step 6 below), not to a `Ticket Master` session.

6. **Report.** Tell me: the version now installed, the values used, each step and whether its check passed, the path of the smoke-test ticket (adopting), and the command that starts the viewer. Ask me before any commit or push.

If the ticket system itself misbehaves, or a step in its docs is wrong, don't patch the copy. Draft an issue for https://github.com/shadowevil/claude-ticket-system/issues: what you saw against what you expected, the steps to reproduce, and the version from `SRC/VERSION`, with no private paths and no ticket text I haven't approved. Show it to me, and post it only with my OK.
