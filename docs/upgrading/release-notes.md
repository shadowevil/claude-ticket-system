# Per-release notes

*Assessed 2026-10-21 (B47, under the documentation standard): kept whole. An upgrade reads several notes in a row, and each note is 1-3 KB, too small to stand as a file.*

*Part of the upgrade guide, `../UPGRADING.md`: read its opening first, for `SRC`, `REPO`, `SCRATCH` and `CLI_DIR`. A bare "sect. N" here is that guide's sect. N, and its index names the file. `ADOPTING.md` is `../ADOPTING.md`, an index too.*

## 1.4.1 (2026-11-01)

The rules-doc merge tool, `done` enforced, and a quieter `identify` (`CHANGELOG.md` [1.4.1]; the maintainer sets the number and date at release). There is no configuration or JSON structure change, so it's a patch. From 1.4.0, follow sect. 9; from a 1.3.x copy, follow sect. 8 with this release in place of 1.4.0 (its step 2), then sect. 9 from step 4.
- **The tool folder:** two files changed since 1.4.0: `tickets.py` and `author.py`. Copy those two, or everything in `PAYLOAD/src/tools/tickets/` except `icons/`. Never copy `icons/`, and don't re-bake.
- **`done` needs a commit link** (B62): `set --status done`, `new --status done` and `author.py draft`/`new` refuse it while `links.commits` is empty and the command adds none. Old done tickets without one stay valid; `validate` prints one `WARNING ... done ticket(s) have no commit link ...` line and exits 0.
- **The rules doc** merges with `release.py merge-doc ... --base <the 1.4.0 doc> --out <scratch file>` (B61, sect. 9 step 5); exit 0 means none of your text was dropped. The template gains `template:begin/end` markers around its porting note, an empty `project:begin rules` pair at the end of sect. 5, and capitals free-text placeholders, with `<NEIGHBOURS: ...>` and `<DESIGN_DOC: ...>` on lines of their own.
- **The skill changed outside its rows** (its Close wording, B62). Take it whole, put your Settings rows back, set the version row to `1.4.1`, and have it reviewed before install.
- **`identify`** prints per-file lines only for the closest release (B63); `--verbose` shows every release's.
- **The hooks:** unchanged.

## 1.4.0 (2026-10-31)

Typed ticket links, comments, the `user_review` and `verified` statuses, a new detail view, a localhost viewer and `page_title` (`CHANGELOG.md` [1.4.0]). The schema and `config.json` structures change, so it's a minor, but no data moves: every new field is optional. From 1.3.0 or 1.3.1, follow sect. 8; from a 1.2.x copy, follow sect. 7 with 1.4.0 in place of 1.3.0 (its step 2), then sect. 8.
- **The viewer binds 127.0.0.1 by default** (B57). Anything on the LAN that reached your viewer (a phone, another PC) needs `serve.py --all-interfaces` after the restart; the maintainer's master site, on the same PC, reaches it over 127.0.0.1 and needs nothing. `--local-only` is still accepted and changes nothing. A running viewer keeps its old binding until `--stop`.
- **The tool folder:** six files changed since 1.3.1: `tickets.py`, `author.py`, `serve.py`, `app.js`, `index.html` and `style.css`. Copy those six, or everything in `PAYLOAD/src/tools/tickets/` except `icons/`. Never copy `icons/`, and don't re-bake.
- **The schema's `links` node and a new `comments` node** (B58) must be merged into your `ticket.schema.json`, keeping your enums (sect. 8 step 4). Until then a ticket with a typed link or a comment fails the schema; unchanged tickets still validate.
- **Two new statuses, `user_review` and `verified`** (B59, B60): add both to your schema's `status` enum in the same merge (sect. 8 step 4). Both count as active; `verified` sits between `in_review` and `done`, and `user_review` marks a ticket waiting on the user, highlighted in the viewer. Until the merge the CLI does not offer them; existing tickets validate unchanged.
- **`config.json`** may carry `page_title` (B57), used verbatim; the example `config.json` is unchanged and your file needs no edit.
- **The skill and the rules doc changed.** Take the skill whole, put your Settings rows back, set the version row to `1.4.0` and have it reviewed before install. The rules doc's sect. 1-5 and 7 gain the new statuses and their rules, the typed links, comments, mentions, the `validate` checks, the `page_title` key, the hyphen sentence and the viewer binding (sect. 8 step 5).
- **`validate` may now print a `WARNING`** for a body or comment that names an id with no ticket (B58); the exit code stays 0.
- **Tag names:** unchanged (lowercase letters, digits, `_`); a hyphen is not allowed, so `re-docs` is the tag `re_docs` (B57).
- **The hooks:** `hooklib/ticket_store.py` changed: T2 now also ties a write to an active Ticket Master ticket in `verified` (not `user_review`). Its self-test cases (`rules/write/t2_ticket_system_fork.py`) and the T2 text in `RULES.md` changed with it. With the hooks installed, copy these three in by sect. 6, "Upgrading installed hooks" (staged self-test with `--scratch`, review, install, self-test again).

## 1.3.1-hotfix (2026-10-21)

A hotfix to the 1.3.1 public repo's `README.md` only: its prompt is one fenced `markdown` block, easy to copy (`CHANGELOG.md` [1.3.1-hotfix]). The version stays 1.3.1 and no file of the release payload changed, so adopters do nothing.

## 1.3.1 (2026-10-21)

Portable docs, a public GitHub repo, and fixes (`CHANGELOG.md` [1.3.1]). There is no configuration or JSON structure change, so it's a patch. From 1.3.0, follow sect. 3; from a 1.2.x copy, follow sect. 7 with 1.3.1 in place of 1.3.0 (its step 2), then this note.
- **Where releases come from.** Besides the maintainer's source folder, a release is now a clone of `https://github.com/shadowevil/claude-ticket-system`; with a clone, skip the export (`ADOPTING.md` step 2, sect. 3 step 2). The public repo starts at 1.3.1, so its release tags start there too: an older copy upgrades straight to the clone's release (sect. 3, "From a public clone"). Problems go to that repo's issues, drafted and posted only with your user's OK, or, on the maintainer's machine, to the `Ticket Master` session.
- **The tool folder:** two files changed since 1.3.0: `tickets.py` and `serve.py`. Copy those two, or everything in `PAYLOAD/src/tools/tickets/` except `icons/`. Never copy `icons/`, and don't re-bake: yours are baked per project.
- **A killed tag store write** (B52): `import --abort-interrupted` now also removes the `tags.store-<pid>.tmp` such a write leaves, once its process is gone (sect. 7, "What behaves differently"). `.claude/tickets/*.tmp` in `.gitignore` already covers it.
- **Bad tag entries** (B52): `validate` names a ticket carrying a tag whose `tags.json` entry is invalid as such (`<file>: tag id N: its entry in tags.json is invalid (...)`), not as an unknown tag.
- **The skill changed outside its rows.** Its text names the ticket system's maintainer (the GitHub repo's issues; on the maintainer's machine, the `Ticket Master` session) instead of Ticket Master alone, so a 1.3.0 skill no longer matches. Take `PAYLOAD/dot-claude/skills/tickets/SKILL.md` whole, put your Settings rows back, set the version row to `1.3.1`, and have it reviewed before install.
  - **The "Ticket system source" row** ships with a `<SRC: ...>` placeholder. Fill in where you take releases from: the GitHub repo's URL, a clone you keep, or, on the maintainer's machine, the absolute path of the maintainer's source folder (`ADOPTING.md` step 8).
  - **Replace a temp-folder scratch row; don't keep it** (B54). If your "Scratch for body files" row, your rules doc's `<SCRATCH>` bullet or a CLI example names the harness's scratchpad or a system temp folder (`AppData\Local\Temp`, `%TEMP%`, `/tmp`), set each to `.claude/scratch/<role>/<task>/` inside the project, git-ignored (sect. 3 step 8).
- **The rules doc:** the template's sect. 4 port bullet and sect. 6, the ticket system itself, name the maintainer instead of Ticket Master alone, and sect. 3 gains the bad-tag-entry lines of `validate` and a killed tag store write. Take them into yours; your section numbers stay, and if your rules doc states a binding port range, keep it.
- **The hooks:** `rules/write/t2_ticket_system_fork.py` (T2 names the GitHub issues as an upstream) and `RULES.md` (its measured-evidence section names no local projects) changed. With the hooks installed, follow sect. 6, "Upgrading installed hooks", with the staged self-test run with `--scratch <REPO>/.claude/scratch/<role>/<task>/`.
- **The example `config.json`** uses port 18600. It is an adapted file, so yours is untouched.

## 1.3.0 (2026-10-21)

Numbered tags, tag groups and `author.py` (`CHANGELOG.md` [1.3.0]). JSON structures change, so it's a minor. From any 1.2.x copy, follow sect. 7.
- **Replace a temp-folder scratch row; don't keep it** (B54). A 1.2.2 copy's "Scratch for body files" row often points at the harness's scratchpad under a system temp folder (`AppData\Local\Temp`), and so do its rules-doc bullet and CLI examples. Set them to `.claude/scratch/<role>/<task>/` inside the project, git-ignored (sect. 7 step 11), rather than carry them forward.
- **The move is required.** Until `author.py tags --probe` has run, every writer refuses. Until `author.py --convert-all` has run, `validate` warns.
- **The tool folder:** five files changed since 1.2.2: `tickets.py`, `author.py` (new), `serve.py`, `app.js` and `style.css`. Copy those five, or everything in the folder except `icons/`. The icons, `lib/`, `index.html`, `manifest.webmanifest` and `make_icons.py` are unchanged, so no re-bake is needed. Never copy `icons/`: yours are baked per project.
- **The schema's `tags` node** changes. The example `tags.json` is in format 2, and the example `config.json` has one `tag_groups` entry. All three are adapted files, so yours change only by the steps of sect. 7.
- **An all-digit tag name or an integer tag value** must be fixed by hand before the probe (sect. 7 step 7).
- **`.gitignore`:** add `.claude/tickets/tags.json.lock`, the tag-store lock. A lock left behind by a killed `author.py` is deleted by hand once no `tickets.py` or `author.py` is running.
- **No abbreviated options** in `tickets.py`, `author.py` or `serve.py`. Check your scripts.
- **A missing or unreadable input file** (`--body-file`, `--append-body-file`, `--from-json`, an `import` file), or a missing or corrupt schema, gives one `ERROR` line naming the file, not a traceback (B50). `set` refuses only a ticket it can't work on, and can repair one; `show` prints an invalid ticket with a `WARNING` (sect. 7, "What behaves differently"). A file holding `NaN` or `Infinity` is not valid JSON.
- **Leftover `.tmp` files:** `import --abort-interrupted` now removes a killed `new`'s or `set`'s temporary file too, once its process is gone. `set` no longer writes into a ticket in place (B45), and the viewer ignores `.tmp` files (B46).
- **Ticket numbers have at most 9 digits.** A longer-numbered file name is no ticket; `validate` names it (sect. 7, "What behaves differently").
- **The hooks changed** (B45, B46): `hooklib/fixtures.py`, `paths.py`, `prompt_clock.py`, `output.py`, `selftest.py` and `ticket_store.py`, `rules/write/t2_ticket_system_fork.py`, and `RULES.md`. Upgrade them as in sect. 6, and run the self-test with `--scratch <REPO>/.claude/scratch/<role>/<task>/`. `--scratch` now refuses the project root and `.claude/` itself.

## 1.2.2 (2026-09-30)

`tickets.py` and the optional hooks changed (`CHANGELOG.md` [1.2.2]). There is no configuration or JSON structure change, so it's a patch. The schema and the example `config.json` are byte-identical to 1.2.1, and the skill differs only in its Settings version row.
- **Every copy:** stop the viewer, copy `tickets.py`, the only file of the tool folder that changed (or everything in `PAYLOAD/src/tools/tickets/` except `icons/`), over `<CLI_DIR>/`, run `validate`, and start the viewer again. Set your skill's "Ticket system version" row to `1.2.2` and tell the maintainer. The icons are unchanged, so don't copy `icons/` and don't re-bake. (The original 1.2.2 note said to copy the folder whole. That replaced the project's baked icons with the release's `XY` ones, B43; if you did, re-bake with `make_icons.py`.)
- **`validate` is stricter by one check** (B41): a `summary` or `target_patch` with a line break (LF, CR, or any other character that ends a line) fails with `has a line break; it must be one line`. Fix it with `set --summary` or `set --target`. No adopter's store had one on 2026-09-30.
- **`new` never overwrites** (B41): if two writers race for an id, the later one takes the next id and prints it. Read the id from `created <id>`; don't assume it.
- **`import`** (B40) is for migrating from another tracker; `ADOPTING.md`, "Migrating from another tracker". Daily filing still uses `new`. It refuses a store that doesn't validate, and after a killed run `import --abort-interrupted` restores the store.
- **`.gitignore`:** add `.claude/tickets/*.tmp`. `new`, `set` and `import` write through a short-lived `.tmp` file, and a killed one can leave it behind. `list`, `validate`, `new`, `set` and `import` ignore it; the 1.2.2 viewer counts it, so it causes one page refresh (1.3.0's ignores it). It is safe to delete once no `tickets.py` runs; from 1.3.0 `import --abort-interrupted` removes it.
- **With the hooks:** follow sect. 6, "Upgrading installed hooks".
- **`--scratch <dir>`** (B38) lets the self-test use a folder you name, which may lie inside your project (outside `.claude/hooks/tickets/` and `.claude/tickets/`; from 1.3.0, not the project root or `.claude/` itself). Pass `--scratch <REPO>/.claude/scratch/<role>/<task>/` every time, so the self-test never uses the system temp folder (B48). A 1.2.1 self-test ignores the option and uses the temp folder; a 1.2.2 one refuses any argument it doesn't know.
- **A refused `TMP`** sees no file at all now (B39).
- **Your rules doc** (optional): the template gained an `import` line under the commands and "a line break is refused" on the `summary` row.

## 1.2.1 (2026-09-30)

Only the optional hooks and their docs changed (`CHANGELOG.md` [1.2.1]), so it's a patch. The tool folder, the schema and the example `config.json` are byte-identical to 1.2.0, and the skill differs only in its Settings version row.
- **Without the hooks:** nothing to copy: no file of the tool folder changed, so leave it, `icons/` included. Set your skill's "Ticket system version" row to `1.2.1` and tell the maintainer. `identify` shows every product file matching under `release 1.2.1`.
- **With the hooks:** follow sect. 6, "Upgrading installed hooks". Run the self-test on the staged copy first. From 1.2.1 it writes nothing inside that copy, wherever it sits (B35). Then replace `.claude/hooks/tickets/`, and run the self-test again from the installed path. A leftover `build/hooks/tickets/selftest/` from an interrupted 1.2.0 run is safe to delete.
- **The self-test** exits 2 with one `self-test: refused: ...` line when `TMP` points into the package or its project; 1 still means a case failed.

## 1.2.0 (2026-09-30)

One optional `config.json` key, `icon_color` (`CHANGELOG.md` [1.2.0]), so a minor. From a 1.1.0 copy, follow sect. 5; from 1.0.0, sect. 4 and then sect. 5.
- **The tool folder:** three files changed since 1.1.0: `make_icons.py`, `serve.py` and `tickets.py`. Copy those three, or everything except `icons/`. Re-bake only if you set `icon_color` (sect. 5 steps 4 to 6).
- **`icon_color`** (B31) sets the icons' background, `#rrggbb`, by default `#007acc`. Without it the icons are byte-identical to 1.1.0's. To keep a 1.0.0 colour, see sect. 5 step 5.
- **The skill** (B29, B30). Its description names more bare requests. It cites no rules-doc section by number: a copy keeps its own numbers, and the Settings "Rules doc" row maps each named section to one. The template `tickets.md` keeps its numbers.
- **`identify`** finds the tool through `config.json`'s `tool_dir` before the two default folders, and a `tool_dir` it can't use prints a note (B32, sect. 1).
- **A value ending in a line break is rejected** by every anchored check (B34). Every adopter's store still validates.
- **`.gitattributes`** lines for the tool folder, the skill and the hooks are recommended (B33, `ADOPTING.md` step 9).

## 1.1.0 (2026-09-30)

Config-driven, drop-in (`CHANGELOG.md` [1.1.0]). From a 1.0.0 copy, follow sect. 4.
- **`portable_workflow.md`** left the payload (B14). It was the original project's general workflow doc, not part of the ticket system. If you copied it, it is now yours to keep, change or delete. `identify` lists it only under 1.0.0, as `not installed (yours, optional)` when it is absent.
- **The skill (B5, fixed).** The per-project text now lives in the Settings rows, so a copy that changed only its rows shows `settings-only`.
- **Stop the old viewer before copying** (sect. 4 step 3), and keep your pin line's marker, `short_name`, `theme_key` and `Server` header. Behaviour changes in `serve.py`, the CLI and the page are listed at the head of sect. 4.
- **The example files.** The payload's `tags.json` and the schema's `owner_area` and `author` enums are project-neutral now (B24). They are examples you adapt, and `identify` never compares them, so an upgrade doesn't touch your own.
- **The tool folder:** every file changed and `lib/` is new (sect. 4 step 5): copy everything except `icons/`, then re-bake (sect. 4 step 7), which restores your `icon_text` from `config.json`.
- **The icons** are `adapted` (B22): each project bakes its own, so `identify` shows them as `(yours: adapted per project, not compared)`, never as a local change. Under 1.0.0 they still show `unverified` (sect. 1).

## 1.0.0 (baseline, 2026-09-30)

Nothing to install. A copy taken on 2026-09-30, before 1.1.0, is 1.0.0, whatever its line endings or indentation. Record the version (sect. 2).

What `identify` showed for the copies at release time: the original project's copy matched all 17 files. The others matched 4 to 6, with 10 to 12 files `unverified` (`tickets.py`, `serve.py`, `app.js`, `index.html`, `style.css`, `manifest.webmanifest`, `make_icons.py` and the icons, and in one copy both `refresh.md`), and each one's skill differed (below).

The unverified files' diff lines, after tab re-indentation is ignored, ran from 2 (`style.css`, its comment line) to 25 (a `tickets.py`). Diff them before your first upgrade (sect. 1). One local change was already known inside them: a `tickets.py` that wraps `show`'s links in `ascii_text()`. 1.1.0 ships it (B9).

- **The skill.** Every adopted copy's `SKILL.md` differs from 1.0.0 outside its Settings table rows: the example id in the description and `show 153`, the viewer bullet of "Adopting it in another project" (prose in the Settings section, so it is compared), the opening quote, and extra wording and rules. The 1.0.0 skill put project-specific text outside the table, so no adopter could match it exactly. 1.1.0 moves that text into Settings rows (B5) and takes adopters' peer and request rules upstream (B6, B16); sect. 4 step 10 maps the rows.
- **Library locations.** Some copies keep marked and DOMPurify in `<CLI_DIR>/lib/` or `<CLI_DIR>/vendor/`, with `serve.py`'s two `/lib/` routes edited to match. `identify` looks there too and prints where it found them. `refresh.md` files moved unedited match exactly; ones that carry the path edits show `unverified`. From 1.1.0 every copy keeps them in `<CLI_DIR>/lib/` (sect. 4 step 6).
- **Install depth.** A copy with `CLI_DIR` as `tools/tickets` has the depth edit from 1.0.0's `ADOPTING.md` step 5. 1.1.0 finds the repository root by itself (B2).
