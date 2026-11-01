# Adopting the ticket system in a new project (release 1.4.1)

*For an agent (or its PM) putting the ticket system into a repository that has none. Follow the steps in order; each ends in a check. If your project already has a copy, use `UPGRADING.md` instead.*

*Assessed 2026-10-21 (B47, under the documentation standard): split three ways. Steps 1-11 are one continuous procedure that cites itself throughout, so they stay together in one file and keep their numbers. Migrating from another tracker and the optional hooks stand alone, and only some projects need them. The names below stay here.*

Throughout:
- `SRC` = the folder holding this release: a clone of the GitHub repo, `https://github.com/shadowevil/claude-ticket-system`, or, on the maintainer's machine, the maintainer's source folder, whose `tools/release.py export` makes the export you install from (step 2);
- `REPO` = your repository's root;
- `SCRATCH` = your session's scratch folder: `<REPO>/.claude/scratch/<role>/<task>/`, inside your project and git-ignored (step 9). Never a system temp folder or the harness's scratchpad, which lives in one;
- **the maintainer** = whoever maintains the ticket system. Problems and wanted changes go to the GitHub repo's issues, `https://github.com/shadowevil/claude-ticket-system/issues`; on the maintainer's machine, to the `Ticket Master` session as a message. An issue is public, so draft it (what you saw against what you expected, repro steps, the version, with no private paths and no ticket text your user hasn't approved), show it to your user, and post it only with their OK. Anything else a step says to tell the maintainer goes to the `Ticket Master` session on the maintainer's machine, and to your user anywhere else.

**Requirements:** git, and Python 3.7 or newer (stdlib only); check with `python --version`. On Windows, 3.8 or newer is recommended: before 3.8, `os.path.realpath` doesn't see through junctions and symlinks, so the viewer's own-server check and the hooks self-test's scratch guard are weaker. On a machine where Python is `python3`, replace `python` in the three commands of the hooks' `settings.snippet.json`.

**Reading SRC is fine; never edit it.** If something here is wrong or unclear, tell the maintainer (step 11).

From 1.1.0 no code is edited. Your project's values live in `.claude/tickets/config.json`, the two team enums of `ticket.schema.json`, `tags.json`, the rules doc and the skill's Settings rows. Everything else is installed exactly as released, so an upgrade is a plain copy.

## Contents

- `adopting/steps.md` - **steps 1-11, the adoption itself,** each ending in a check: 1 decide your values, 2 get the release (a clone, or an export), 3 copy the files, 4 write `config.json` (every key and its default, including the optional `page_title`), 5 the schema's team enums and the icons, 6 tags (the numbered tag store, `author.py`, tag groups), 7 the rules doc, 8 the skill (reviewed before install), 9 project wiring (`CLAUDE.md`, `.gitignore`, `.gitattributes`), 10 verify (the viewer starts bound to localhost; `--all-interfaces` opts in to the LAN), 11 report to the maintainer. Read it whole and in order for every new adoption: steps 1-10, then the two optional parts below if they apply, then step 11. `UPGRADING.md` cites its steps 6 and 9.
- `adopting/migrating.md` - **Migrating from another tracker:** `tickets.py import`, the record format with an example, seven checked steps (map the fields, adapt the enums and tags, rehearse in scratch, dry run, import, verify, retire the old tracker), and recovering from a killed import with `import --abort-interrupted`. Read it after step 10, only if the project has an earlier tracker (a queue file, a TODO list, another tool's export). `UPGRADING.md` sect. 7 cites its step 3 for a rehearsal.
- `adopting/hooks.md` - **Optional: ticket hooks:** what T1 and T2 log, and seven steps (stage and review with the staged self-test, copy the folder, merge the wiring, ignore the runtime files, config, the installed self-test with `--scratch`, leave them log-only). Read it after step 10, only if you want the hooks. `UPGRADING.md` sect. 6 sends a first install here.
