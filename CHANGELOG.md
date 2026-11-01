# Ticket system changelog

Versions use x.y.z numbering (user rule, 2026-09-30): **minor** means the configuration or a JSON structure changed, **patch** is anything smaller such as UI updates and fixes, and **major** is kept for large progress, which is not defined yet. Each entry lists the items it ships, by their numbers (`B<n>`) in the maintainer's internal backlog, and its upgrade steps. The steps in full are in `docs/UPGRADING.md`.

## [1.5.1] - 2026-11-01

**Docs only.** The `update_source` example in `docs/adopting/steps.md` and `docs/upgrading/1.4.x-to-1.5.0.md` named the maintainer's local repository; it now reads `C:\\path\\to\\source-repo\\ticket-system`. A **patch**: no code, configuration or JSON structure change, and nothing to do for a copy on 1.5.0.

Agents: none

## [1.5.0] - 2026-11-01

**The viewer's one-click update, and the last manual upgrade.** A **minor**: `config.json` gains `update_source`, the ticket schema gains `x-project-owned`, and the viewer's API gains three routes. Nothing migrates: both keys are optional for existing stores. The steps are in `docs/UPGRADING.md` sect. 10; from 1.5.0 on, releases install from the viewer (sect. 11).

- **An update badge and one-click update (B65, from the user):** with `update_source` in `config.json` (the absolute path of the maintainer's `ticket-system/` folder on this machine), the viewer shows "Update x.y.z" in its top bar when a newer release is tagged there. A click shows the changelog (rendered through marked and DOMPurify) and asks to confirm, then:
  - the release, and the one the copy runs (the merge base), are exported from their tags with `release.py export` into `build/tickets/update/<v>/`; every file is checked against the export's manifest `raw` hash, and every manifest path must sit under `src/tools/tickets/` or `dot-claude/` with no `..`;
  - the schema is merged with `merge_schema` (the project's `x-project-owned` values kept); a project change outside them stops the update before any file changes;
  - the replaced files are backed up, and a detached helper from the new release (`updater_helper.py`) stops the viewer, installs each file as `.new` plus `os.replace` (a held file retried for 10 s), deletes `__pycache__`, runs `validate` and restarts the viewer on the same port and bind; a failure restores the backup and restarts the old viewer, and a helper that dies part-way is undone by the next `serve.py` start;
  - the skill (Settings rows carried over, version row set), the hooks (where installed) and the rules doc (merged with `merge-doc --base`) are only staged, in `build/tickets/staged/<v>/`; nothing is committed and no git command runs in the adopter's repository.
- **The update endpoint (B65):** `GET /api/update` (installed, latest, state, release notes), `GET /api/update/status`, and `POST /api/update/apply`, the viewer's only POST. It needs all of: a client on this PC, `Host` `127.0.0.1:<port>` or `localhost:<port>`, a matching `Origin`, and `X-Tickets-Token` equal to a token made at start (memory only, served in a `<meta>` to local clients, compared with `hmac.compare_digest`); anything else is 403, and no CORS header is ever sent. The body must name the version on offer (409 otherwise), and `build/tickets/update.lock` refuses a second apply (409). Without `update_source` the POST is always 403. Discovery is a listing of `releases/*.json` plus `git tag -l`: an untagged manifest is never offered.
- **The agents README (B65, from the user):** `.claude/tickets/README.md`, rewritten by each update: per release, newest first, its `Agents:` lines, then the `ACTION` lines for the copy. After an update, `tickets.py` prints `tickets: store updated to <v> - see .claude/tickets/README.md` once, to stderr (`build/tickets/readme-seen`); `tickets.py readme` writes the first README. The skill gains "After an update": read it, and act on `ACTION` lines only as the role allows.
- **`update_source` (B65):** optional; absent or empty, updates are off (the opt-out). A non-string stops `serve.py` with an error naming the key.
- **`schema_merge.py` from the command line (B65):** `python <CLI_DIR>/schema_merge.py <release> <project> --base <base> --out <file>`, the manual 1.5.0 schema step.
- **New tool-folder files:** `updater.py`, `updater_helper.py` (with `schema_merge.py` and `VERSION` below). Changed: `tickets.py`, `serve.py`, `app.js`, `index.html`, `style.css`.
- **`x-project-owned` in `ticket.schema.json` (B65):** a top-level list of JSON pointers to the values a project owns: the id pattern (`/properties/id/pattern`, `/$defs/ticket_ids/items/pattern`) and the `status`, `severity`, `owner_area` and `author` enums. `tickets.py` ignores the keyword, so existing tickets validate unchanged.
- **`schema_merge.py` (B65):** a new tool-folder module, `merge_schema(release, project, base) -> (merged, problems)`. It takes the release's schema and copies the project's value in at each owned pointer; if the project differs from the base release's schema anywhere else, it returns problems and no merge.
- **A `VERSION` file in the tool folder (B65):** one line, the version the installed copy is at. `release.py manifest` writes it from `VERSION` and lists it, so `identify` and `export` carry it like any product file.
- **Release tooling (B65):** a new manifest also records `changelog` (the entry's text) and `agents` (the lines of the entry's `Agents:` block, `[]` for `Agents: none`); manifests already written are never rewritten. `release.py check` fails without the `Agents:` block, with an `x-project-owned` pointer that does not resolve in the payload schema, or when the payload's `VERSION` file disagrees with `VERSION`.
- **Structure:** `ticket.schema.json` gains `x-project-owned`; `config.json` gains `update_source`; the viewer API gains `GET /api/update`, `GET /api/update/status` and `POST /api/update/apply`; manifests gain `changelog` and `agents`.
- **Ships:** B65.

**Upgrade** from 1.4.x (`docs/UPGRADING.md` sect. 10), the last one by hand:
1. Get the release, back up, stop the viewer; copy the tool folder except `icons/`.
2. Ignore `build/tickets/`; merge the schema with `schema_merge.py --base <your release's schema>`; add `update_source` on the maintainer's machine.
3. Merge the rules doc with `merge-doc`, take the skill (Settings rows back, version row set, reviewed), run `tickets.py readme`, restart the viewer, commit.

Agents:
- After an update, `tickets.py` prints `tickets: store updated to <version> - see .claude/tickets/README.md` once, on stderr: read that README's newest section before the next write.
- `ACTION` lines in `.claude/tickets/README.md` are for this copy: act on one only if your role allows it, otherwise tell the user (or the PM).
- `tickets.py readme` writes the README when it is missing.
- `ticket.schema.json` may hold an `x-project-owned` list; it is for the updater, and agents ignore it.

## [1.4.2] - 2026-11-01

**The rules-doc merge rebuilt as a three-way merge.** 1.4.1 was tagged but never published; 1.4.2 is that release with `merge-doc` redone, so a copy on 1.4.0 or 1.3.x upgrades straight to it. A **patch**: no configuration or JSON structure change. The steps are in `docs/UPGRADING.md` sect. 9, read for 1.4.2.

- **`release.py merge-doc` is a hunk-level three-way merge (B64, from the maintainer's pre-release test on three adopter copies):** the values and the free-text places are filled into the release's and the base's text first, then each change hunk against `--base` is taken from the side that changed it, once if both changed it alike. Text both sides changed differently, or changed next to each other, is written as a conflict block (`<<<<<<< project`, `||||||| base <version>`, `=======`, `>>>>>>> release <version>`), each listed with its line numbers, and the command exits 2. It never mixes lines of the two sides in a hunk and never drops a project line, except the base's own text where the release changed it. The project's line is kept over the release's only where the release changed nothing on it but the placeholder itself; any other change around a placeholder, or a placeholder line added next to a project edit, is a conflict. `--base` is required (exit 1 without it), and a doc still holding conflict marker lines (`<<<<<<<`, `|||||||`, `>>>>>>>`) is refused. The 1.4.1 version garbled reflowed paragraphs and dropped project rules next to changed lines.
- **The upgrade guide (B64):** `--base` is the rules doc of the release the copy runs now (a 1.3.x copy uses its own 1.3.x export, and skips sect. 8's rules-doc step); conflict blocks and their resolution, the `<REPO>` value (`--set REPO=`), and what to expect replace the "only the release's changes" promise. The check is a re-run with the new release's doc as `--base`: exit 0 and an identical file.
- **Files changed since 1.4.1:** the source's `tools/release.py` and the upgrade docs. The tool folder, the skill, the rules-doc template and the hooks are as in 1.4.1.
- **Ships:** B64 (with B61, B62 and B63 from 1.4.1).

**Upgrade** from 1.4.0 or 1.3.x: as for 1.4.1 below (`docs/UPGRADING.md` sect. 9), with `--base` the rules doc of the release you run now, and every conflict block resolved before the doc is copied over.

## [1.4.1] - 2026-11-01

**A merge tool for the rules doc, `done` enforced, and a quieter `identify`.** A **patch**: no configuration or JSON structure change (the schema, `config.json`, `tags.json` and the API's JSON are as in 1.4.0). The steps are in `docs/UPGRADING.md` sect. 9.

- **`release.py merge-doc` (B61, from an adopter):** `merge-doc <release-doc> <project-doc> --base <old-release-doc> --out <file>` writes the release's rules doc with the project's parts kept: the value placeholders (from `--set`, `config.json`, then the project doc), the text written in each free-text place, `<!-- project:begin <name> -->` ... `<!-- project:end <name> -->` blocks and, with `--base` (the rules doc of the release the project runs), a three-way merge that keeps the project's edits wherever the release left the text alone. Exit 0 means no project text was dropped; a project line the release text replaced that is not the base's wording is listed as LOOK and the command exits 2. `--out` may not be an input, and the file is written atomically; a BOM and the line endings are kept. An upgrade's rules-doc step is that command plus a review of the diff (`docs/UPGRADING.md` sect. 3 step 7).
- **The rules-doc template (B61):** the porting note sits between `<!-- template:begin -->` / `<!-- template:end -->` (merge-doc drops it, and reports a project's changed copy); sect. 5 ends with an empty `project:begin rules` pair for the project's own rules; the free-text placeholders are capitals (`<NEIGHBOURS: ...>`, `<ROLE_LIMITS: ...>`, `<DESIGN_DOC: ...>`, `<PEER>`), with `<NEIGHBOURS: ...>` and `<DESIGN_DOC: ...>` on lines of their own. A doc ported from an older template, with no markers, merges by alignment.
- **`done` needs a commit link (B62, from an adopter):** `tickets.py new` and `set --status done`, and `author.py draft`/`new` (flags or `--from-json`), refuse `done` while `links.commits` is empty and the same command adds none: `ERROR status done needs a commit link (links.commits is empty): add --link-commit <hash> to the same command`. `wont_do` is unaffected; `import` still takes an old done ticket without one, and `set` on such a ticket without `--status done` still works. `validate` warns, never fails: `WARNING N done ticket(s) have no commit link (<ids>): ...`.
- **`identify` (B63, from an adopter):** prints every release's summary line, but the per-file lines only under the closest release, plus a count of the ones hidden; `--verbose` shows every release's. The same `SKILL.md ... local change` line no longer repeats once per older release.
- **Files changed since 1.4.0:** in the tool folder, `tickets.py` and `author.py`; the skill (its Close wording, outside its rows) and the rules-doc template; the source's `tools/release.py`.
- **Ships:** B61, B62, B63.

**Upgrade** from 1.4.0 (`docs/UPGRADING.md` sect. 9):
1. Get the release (pull your clone, or export it).
2. Copy `tickets.py` and `author.py`, merge the rules doc with `release.py merge-doc` and review its diff, take the skill (Settings rows back, version row set, reviewed), run `validate` (a `WARNING ... no commit link` is fine).

## [1.4.0] - 2026-10-31

**Typed ticket links, comments, two statuses, a new detail view and a localhost viewer.** A **minor**: the ticket schema and `config.json` gain optional fields (user rule, 2026-09-30: "Minor only updates when a configuration or json structure change happens"). Nothing migrates: every new field is optional, so existing tickets and configs validate unchanged. The steps are in `docs/UPGRADING.md` sect. 8 and the per-release notes, 1.4.0.

- **Typed links (B58):** `links.blocks`, `links.blocked_by` and `links.relates_to` are optional ticket-id lists; the old `links.tickets` is still read, as relates-to.
  - `tickets.py new` and `set`, and `author.py draft` and `new`, take `--block`, `--blocked-by` and `--relates`; `set` also takes `--remove-block`, `--remove-blocked-by` and `--remove-relates`. A block is written on both tickets, all or none.
  - `list` shows `[blocked by ...]` and a comment count; `show` prints the typed links.
- **Comments (B58):** a ticket's optional `comments` list of `{author, at, body}`, appended by `tickets.py comment <id> --author --body-file` and `author.py comment`. CLI-only; the viewer stays read-only.
- **Mentions (B58):** a ticket id written in a body or comment is linked by the viewer, and the detail view gains "Mentions" and "Mentioned by" groups; `show` prints them. Derived, never stored.
- **The detail view (B58):** subject, tags, body, linked tickets (each clickable), then the comments newest first, 10 at a time with a "load more" button.
- **`validate` (B58):** fails a typed link that dangles or points at its own ticket, a block listed on one ticket only, a ticket that blocks and is blocked by the same one, and a comment dated before its ticket or in the future; warns about a mentioned id with no ticket.
- **`new` with a block is all or nothing (B58):** `tickets.py new` and `author.py new` check the new ticket and every other ticket it changes before writing, then write them together; a failure leaves no ticket and changes no other one. `author.py --from-json` refuses `comments` (add them with `comment` once the ticket exists).
- **The viewer links mentions as `validate` reads them (B58):** no letter, digit, `_` or `-` before the id, and at most the store's digit limit.
- **Status `verified` (B59):** between `in_review` and `done`: reviewed and green, only landing it left. Active.
- **Status `user_review` (B60):** the ticket waits on the user; settable from any active status, active, and shown as a filled amber pill with a highlighted count. The schema's `status` enum gains both (a minor); `list --active`, the viewer's order, chips, counts and Active filter, the skill and the rules doc carry them. `done` still needs its commit link.
- **`page_title` (B57):** optional `config.json` key, the page title and heading used as written; without it, or empty, `<store_name> Tickets`.
- **Tag names (B57):** the rule is unchanged and now documented: no hyphen, so the tag for `re-docs` is `re_docs`.
- **The viewer binds 127.0.0.1 by default (B57).** `serve.py --all-interfaces` opts in to the LAN (a phone, another PC), and `--local-only` is accepted and changes nothing. A viewer that the LAN reached must be restarted with the new flag. The maintainer's master site reaches viewers over 127.0.0.1 on the same PC and needs no flag.
- **Files changed since 1.3.1:** in the tool folder, `tickets.py`, `author.py`, `serve.py`, `app.js`, `index.html` and `style.css`; the schema; the skill and the rules-doc template. In the hooks, `hooklib/ticket_store.py` (T2 also ties on `verified`, not on `user_review`), with its T2 self-test cases in `rules/write/t2_ticket_system_fork.py` and the T2 text in `RULES.md`: with the hooks installed, copy them in by `docs/UPGRADING.md` sect. 6.
- **Ships:** B57, B58, B59, B60.

**Upgrade** from 1.3.0 or 1.3.1 (`docs/UPGRADING.md` sect. 8):
1. Get 1.4.0 (pull your clone, or export it).
2. Stop the viewer, copy the six tool files, merge the schema's `links` and `comments` nodes and add `user_review` and `verified` to its `status` enum, take the rules doc's changed sections and the skill, run `validate`, and start the viewer again (with `--all-interfaces` if the LAN must reach it).

## [1.3.1-hotfix] - 2026-10-21

**A hotfix to the 1.3.1 public README only: its prompt is easy to copy.** This is not a new release: `VERSION` stays 1.3.1, and no file of the release payload changed (so no configuration or JSON structure change either).

- **The public README's prompt (B56):** `README.md` is a title, one line saying where to paste the prompt, and the whole prompt, wording unchanged, in one fenced `markdown` code block (a four-backtick fence, so nothing inside can close it). GitHub shows a copy button on the block, and the copied text is the raw Markdown.
- **Ships:** B56.

**Upgrade:** nothing to do. The change is the public repo's README only; your copy, your skill and your `VERSION` row stay as they are.

## [1.3.1] - 2026-10-21

**Portable, and public.** The ticket system now works from a clone of its public GitHub repo, `https://github.com/shadowevil/claude-ticket-system`, on any machine and for any user. A **patch**: no configuration or JSON structure change (user rule, 2026-09-30: "Patch should be for smaller changes"). The steps are in `docs/UPGRADING.md`, per-release notes, 1.3.1.

- **Portable docs (B55):** no distributed file names a machine path, a user name or a local project.
  - `SRC` in `ADOPTING.md` and `UPGRADING.md` is the folder holding the release: a clone of the GitHub repo, or, on the maintainer's machine, the maintainer's source folder. `ADOPTING.md` step 2 tells a clone to skip the export, and every export and `identify` command is written `python <SRC>/tools/release.py ...`.
  - Reports go to "the maintainer": the GitHub repo's issues, drafted and shown to the user and posted only with their OK, or, on the maintainer's machine, the `Ticket Master` session. The adoption and upgrade guides, the skill and the rules-doc template say so; step 11 of the adoption is "Report to the maintainer", and a clone reports to its user.
  - The skill's "Ticket system source" Settings row ships with the GitHub URL and a `<SRC: ...>` placeholder that each adopter fills in.
  - The per-adopter values in `UPGRADING.md` sect. 4 and 5 and in the 1.0.0 per-release note are replaced by where to find your own; the steps and their numbers are unchanged. The hooks' `RULES.md` names the measured projects neutrally (project A to D), with the same numbers. Reporter attributions in this changelog read "from an adopter".
- **The public repo (B55):** it holds the release, without the maintainer's internal files, and a `README.md` that is a prompt: pasted into Claude Code in a project, it has Claude get the release, adopt it (or upgrade an existing copy) by the guides, verify and report.
- **Adoption and upgrade docs (B51):**
  - `ADOPTING.md` step 1's port check is a Python one-liner that works on any system and prints `free` or `in use`; the PowerShell check's exit code 1 for a free port is explained. The example port is 18600, no adopter's.
  - Step 2 says the export works only once the release tag exists. Step 6 says a tag rename doesn't touch `tag_groups`, and to update a group that names the old tag. Step 10 says why the smoke test files with `tickets.py new` while agents file through `author.py`.
  - This changelog's 1.2.2, 1.2.0 and 1.1.0 upgrade steps point at B43: copy the changed files, or everything except `icons/`.
  - `docs/workflow.md` (the maintainer's workflow) says how a scratch adoption handles step 8's skill review.
- **Temp-folder scratch rows (B54, from an adopter):** `UPGRADING.md` sect. 3 step 8 and sect. 7 step 11, the 1.3.0 and 1.3.1 per-release notes and the 1.3.0 upgrade steps here say to replace a "Scratch for body files" Settings row that points at the temp folder (the harness's scratchpad), and the rules-doc bullet and CLI examples that name it, with `.claude/scratch/<role>/<task>/`, rather than keep it.
- **A killed tag store write (B52):** `import --abort-interrupted` also removes the `tags.store-<pid>.tmp` a killed tag store write leaves, once its process is gone, and keeps and names one whose process still runs. The killed write's `tags.json.lock` is still deleted by hand. With nothing to clean it prints `ERROR no interrupted import, no killed new or set and no killed tag store write: ...`.
- **Bad tag entries (B52):** `validate` reports a tag whose `tags.json` entry is invalid as such, not as unknown: `<file>: tag id N: its entry in tags.json is invalid (the tags.json problem for tag N says why)`, `<file>: tag '<name>': its entry in tags.json is invalid (...)`, and `config.json tag_groups[i] ('<g>'): tag(s) "<a>", "<b>" have an invalid entry in tags.json (...)`.
- **Portable code (B55):** no machine paths in the code; the example `viewer_port` is 18600; `release.py identify` and `export` work from a clone of the public repo and from the source repo alike (the public repo's release tags start at `tickets-v1.3.1`, so a clone exports 1.3.1 and later); export writes files exactly as committed whatever the user's line-ending setting. T2 names the GitHub issues as an upstream. The CLI's citation of the 1.3.0 upgrade's hand rename reads "the ticket system's docs/UPGRADING.md sect. 7 step 7".
- **Requirements, stated:** Python 3.7 or newer (stdlib only); on Windows, 3.8 or newer is recommended. A `.gitattributes` ships with the release: LF for text, CRLF for `*.bat`, `*.png` binary.
- **New maintainer tool** `tools/publish.py` (internal, not published): builds the public repo's tree from a release tag and fails on any leftover of the maintainer's machine.
- **Files changed since 1.3.0:** in the tool folder, `tickets.py` and `serve.py`; in the hooks, `rules/write/t2_ticket_system_fork.py` and `RULES.md`; the skill (outside its rows) and the rules-doc template; the example `config.json` (its port).
- **Ships:** B51, B52, B53, B54, B55.

**Upgrade** from 1.3.0 (`docs/UPGRADING.md` sect. 3 and the 1.3.1 note):
1. Get 1.3.1: pull your clone, or export it (`python <SRC>/tools/release.py export 1.3.1 <SCRATCH>/ts-1.3.1`).
2. Stop the viewer, copy `tickets.py` and `serve.py` into the tool folder (or everything except `icons/`; never `icons/`), run `validate`, and start the viewer again.
3. Install the 1.3.1 skill whole, after a review: put your Settings rows back, set the version row to `1.3.1`, and fill in the "Ticket system source" row's `<SRC: ...>`. If your "Scratch for body files" row, your rules doc's `<SCRATCH>` bullet or a CLI example names the temp folder, replace it with `.claude/scratch/<role>/<task>/`; don't keep it (B54).
4. Take the rules-doc template's changes into your rules doc, after a review if your project reviews it: the maintainer wording in sect. 4 and sect. 6, and the bad-tag-entry and killed-tag-store-write lines in sect. 3.
5. If you run the hooks: stage the new `hooks/tickets/` (`t2_ticket_system_fork.py` and `RULES.md` changed), run its self-test there with `--scratch <project>/.claude/scratch/<role>/<task>/`, have it reviewed, replace yours, and run the self-test again (sect. 6).
6. The example `config.json`'s port change doesn't apply to an existing config: leave yours.
7. Tell the maintainer the version you run.

From 1.2.x, follow `docs/UPGRADING.md` sect. 7 with 1.3.1 in place of 1.3.0.

## [1.3.0] - 2026-10-21

**Numbered tags, enforced tag groups, and an authoring tool for agents.** **Minor**, because JSON structures change (user rule, 2026-09-30: "Minor only updates when a configuration or json structure change happens"). The steps are in `docs/UPGRADING.md` sect. 7, and the move is required: every writer refuses an old-format `tags.json`.

Structure: tags.json becomes format 2 (format, next_id, tags keyed by id); ticket.schema.json tags items become an id or a name; config.json gains the optional tag_groups key; the viewer API's /api/tickets tags map is keyed by id and gains tag_format and tag_groups.

- **The tag store (B49, from the user):** `tags.json` is `{"format": 2, "next_id": <n>, "tags": {"<id>": {"name", "color", "description"}}}`.
  - Ids are positive whole numbers below `next_id`, given in order, and never reused or renumbered.
  - Names stay unique, and from 1.3.0 need at least one letter or `_`: an all-digit name reads as an id.
  - Renaming a tag changes only the store.
  - Every writer refuses a store with any problem.
- **Tickets hold tag ids:** `"tags": [1, 4]`.
  - People and agents still type names: `--tags`, `--add-tag`, `--remove-tag`, `list --tag`, `import` records and `author.py` take names or ids, and writers write ids.
  - `list`, `show`, `validate`'s messages and the viewer resolve ids to names.
  - `tickets.py` checks the tag items itself, whatever the project's schema says, so a schema from before 1.3.0 keeps working.
- **Tag groups:** the optional `config.json` key `tag_groups`, such as `[{"name": "type", "tags": ["bug", "cleanup", "docs"], "min": 1, "max": 1}]`. Groups are written with tag names; `min` defaults to 0 and `max` to `null`, any number.
  - `new`, `set`, `import` and `author.py new` refuse a ticket that breaks a group, naming it: `tag group type: pick exactly 1 of bug, cleanup, docs (has none)`. `validate` fails such a ticket.
  - A group naming a tag the store lacks is a config error.
  - No key means no groups, as before. The example `config.json` has one group, `area`.
- **`author.py`,** new in the tool folder: the authoring tool for agents. It takes flags and JSON, never a prompt, gives `--json` output throughout, and writes only through `tickets.py`.
  - `tags` lists the store: id, name, groups, the number of tickets carrying each tag, and the description. `--unused` and `--group <g>` filter it.
  - `tags add <name> --color --description` adds a tag with the next id, and `tags rename <old> <new>` keeps the id.
  - `rules` prints the groups.
  - `draft` takes `tickets.py new`'s flags, or `--from-json <file>` (`-` for stdin), and prints the ticket `new` would write, or its problems: field problems first, then, once the fields pass, unknown tags and each missing group. `new` takes the same input and writes the ticket.
- **Migration:**
  - `author.py tags --probe` numbers an old-format `tags.json` in name order, keeping every name, colour and description. It then adds each name found on tickets that the store lacks, with the next id, `#808080` and "found by probe".
  - `author.py --convert <file or id>` and `--convert-all` rewrite tickets' tag names as ids, each file atomically, with `updated` unchanged.
  - Each takes `--dry-run`, refuses with nothing written when a value can't be placed, and changes nothing on a second run. A `--convert-all` that fails on a write part-way says how many tickets it converted; the rest are unchanged, and running it again finishes.
  - Before the probe, readers take the old store and tickets holding names. They don't resolve an integer or an all-digit tag value: `validate` fails each one with the probe's own line (`tag id N on a ticket while tags.json is not numbered yet; replace it with the tag's name (Ticket Master's docs/UPGRADING.md sect. 7 step 7)`, or `the tag name 'N' is all digits, which reads as a tag id; rename it by hand first (Ticket Master's docs/UPGRADING.md sect. 7 step 7)`), `list` and `show` print the raw value, and the viewer shows a grey chip. Such a value is fixed by hand before the probe (`docs/UPGRADING.md` sect. 7, step 7).
  - Every writer refuses an old-format store with `run author.py tags --probe`. Between the probe and the conversion, readers take names and ids, and `validate` warns `N tickets still carry tag names: run author.py --convert-all` instead of failing.
  - `author.py tags rename` refuses, writing nothing, while any ticket still carries the old name as text, since that ticket would lose the tag: run `author.py --convert-all` first, then rename. It also refuses while an unconverted ticket carries the new name as text that `tags.json` lacks, since that ticket would gain the tag, and while any ticket file doesn't read, since it can't be checked (`ERROR rename refused, nothing written: N ticket file(s) do not read, so they cannot be checked for '<old>' or '<new>'; fix them first (tickets.py validate names them)`).
- **The tag-store lock:** `author.py tags add`, `tags rename`, `tags --probe` and a real `--convert` or `--convert-all` hold `.claude/tickets/tags.json.lock` while they read and write `tags.json`, so concurrent writers take turns.
  - One that waits 30 s refuses with an `ERROR` naming the lock file, its holder and its age, and `tags.json` unchanged.
  - Locks are never broken automatically. A lock left by a killed process is deleted by hand once no `tickets.py` or `author.py` is running.
  - `ADOPTING.md` step 9 and `UPGRADING.md` sect. 7 add `.claude/tickets/tags.json.lock` to `.gitignore`.
- **The viewer:**
  - `/api/tickets` returns the store's tags keyed by id, plus `tag_format` and `tag_groups`.
  - The page shows the same names and colours, and its tag filter matches a tag whether a ticket holds its id or, unconverted, its name.
  - A value the store lacks is a grey, dashed chip, and so is every id while the store is in the old format.
  - The problems box lists each `tags.json` entry that doesn't read, such as `tags.json: tag 9 ('ui'): needs a #rrggbb color`. A store that doesn't read at all shows `tags.json: <reason>`, and an old-format store is reported too.
- **No traceback for an unreadable input (B50):** a missing or unreadable `--body-file`, `--append-body-file`, `--from-json` (stdin included) or `import` file, or a missing or corrupt `ticket.schema.json`, now gives one `ERROR` line that names the file and exits 1. A ticket file that doesn't read, or isn't a JSON object, gives `show` and `set` one `ERROR <id>: ...` line.
- **`set` and `show` on an invalid ticket:**
  - `set` refuses up front only a ticket it can't work on: `ERROR <id> cannot be changed with set: <problem>; fix the file, then run validate`. That covers another id in the file, `tags` not a list, `links` not an object, a `links` entry not a list, and a body that isn't text with `--append-body-file`.
  - Otherwise `set` applies the change and refuses an invalid result with `ERROR refusing to write an invalid ticket:`, so it can repair a ticket, such as a summary that is too long or a missing `tags` list or body.
  - `show` prints a JSON-object ticket that fails the schema, then `WARNING <id> is invalid (N problem(s); the first: ...); run validate`.
- **Stricter JSON reads:** a ticket, `tags.json`, `config.json`, an `import` file or a `--from-json` input holding `NaN`, `Infinity` or `-Infinity` is refused as not valid JSON. A file nested too deeply to read is reported as unreadable. A store read (a ticket, `tags.json`) is tried again while Windows reports the file busy, for example while a `set` moves it into place. The retries share a 3 s budget per command; in the viewer, each request, concurrent ones included, has its own; once it is spent, a busy file is reported as unreadable at once.
- **Fix:** `validate` no longer prints `duplicate id None` for ticket files that aren't JSON objects; each still fails with `not a JSON object`.
- **No abbreviated options:** `tickets.py`, `author.py` and `serve.py` no longer accept an abbreviated option name, such as `--body` for `--body-file` or `--sto` for `--stop`. An abbreviation is now an `unrecognized arguments` usage error.
- **Release tooling:** `release.py`'s version gate reads the format-2 `tags.json`. Adding a tag is data; `format`, `next_id` and a key every tag carries are structure.
- **Docs:** `ADOPTING.md` step 6 covers the tag store, `author.py` and tag groups. `UPGRADING.md` gains sect. 7, "1.2.x -> 1.3.0". The skill files tickets through `author.py` and refers to tags by name. The rules-doc template gains "Tags, tag groups and `author.py`" in sect. 3.
  - `UPGRADING.md` and `ADOPTING.md` are lean indexes now, each with an assessment line (B47). Each upgrade section is a file under `docs/upgrading/` (sect. 1-7, section and step numbers kept, plus the per-release notes); the adoption steps 1-11, migrating from another tracker and the optional hooks are files under `docs/adopting/`.
  - Every existing citation still resolves through the index, including the CLI's "docs/UPGRADING.md sect. 7 step 7" and `release.py identify`'s "UPGRADING.md sect. 1". The text was moved, with only its in-text pointers repointed to the new files. `release.py export` ships the new folders with the rest of `ticket-system/`.
- **A safer `import --abort-interrupted` (B42, B45):** it checks the journal's structure (contiguous ids matching `first`, `last`, `count` and the pid in its name, the store's prefix, sane length) and removes no ticket for a journal that fails it, and it keeps a ticket older than the journal. It refuses while the import's process runs (`ERROR an import is running now (pid N; ...); nothing was removed`), and touches only the tool's own file names. The journal check catches a cut-off or carelessly edited journal; it is not a defence against a deliberately consistent forgery. It also removes the temporary file a killed `new` or `set` left, once its process is gone. `ADOPTING.md` "Migrating from another tracker" says to hold off filing until the re-import is done.
- **`set` writes only through a move (B45):** it no longer falls back to writing in place. A move Windows keeps refusing ends in `ERROR could not write <id>.json (moving the new version over it was refused: ...); the ticket is unchanged; another process may hold the file open: close it, then run set again`, and the temporary file is removed.
- **The viewer and the hooks (B45, B46):**
  - The viewer's change check skips `.tmp` files, so a leftover no longer refreshes the page.
  - A live hook run from a release export no longer writes runtime files into its `payload/`.
  - The hooks self-test's `--scratch` refuses the project root and `.claude/` itself.
  - `write_ticket`'s docstring matches the code.
  - The optional hooks changed (`hooklib/fixtures.py`, `paths.py`, `prompt_clock.py`, `output.py`, `selftest.py`, `ticket_store.py` and `rules/write/t2_ticket_system_fork.py`, plus `RULES.md`); upgrade them as in `docs/UPGRADING.md` sect. 6. The self-test is at 382 assertions. The hooks' ticket-file-name rule (4 to 9 digits) matches the CLI's.
- **Ticket numbers:** a hand-made ticket file with an over-long number (more than 9 digits) is no longer read as a ticket, and `validate` names it. `new`, `import` and `author.py new` refuse cleanly (`ERROR the store is full: ...; nothing was written`) when the store's ids would exceed the digit limit, instead of writing a file nothing reads.
- **`import --abort-interrupted` output:** it is ASCII-safe for any import file name, and the refusal says what each pid is (its program, on Windows) and names that pid's leftover files by pattern (`journal.import-<pid>.tmp` and `<PREFIX>[0-9]*.import-<pid>.tmp`; `<PREFIX>[0-9]*.new-<pid>.tmp` and `<PREFIX>[0-9]*.set-<pid>.tmp` for a running `new` or `set`; for bash or PowerShell, since cmd's `del` does not understand `[0-9]`), so a pid it can't check (access refused) or one that another program reuses has a way out in the `ERROR`: delete those files by hand once you are sure no import runs. A batch that would run past the id limit says how many records fit, and a full store caused by a killed import's journal points at `--abort-interrupted`.
- **One rule for the tool folder in the upgrade notes (B43, from an adopter):** copy the files the release changed, or everything except `icons/`; never `icons/`, whose baked icons are the project's own. `make_icons.py` restores `icon_text`, and from 1.2.0 `icon_color`, from `config.json`, so a folder copied whole by mistake is fixed by a re-bake. `UPGRADING.md` sect. 3, sect. 4 step 5, sect. 5 step 4, sect. 7 step 5 and every per-release note say so, and the 1.2.2 note no longer says to copy the folder whole. The announcement template in `docs/workflow.md` carries the same wording.
- **The new ticket's id is the one `new` prints (B44, from an adopter):** the skill's Write section and the rules-doc template say to read the id from `created <id> - <summary>` (`tickets.py new` and `author.py new` alike), never to work it out beforehand, since `new` can land on a later id.
- **Scratch is inside the project (B48):** the skill, `ADOPTING.md`, `UPGRADING.md` and the rules-doc template name `.claude/scratch/<role>/<task>/` as the scratch folder, not the harness's scratchpad in the temp folder. Every hooks self-test passage (`ADOPTING.md`, `UPGRADING.md`, `RULES.md`) passes `--scratch <project>/.claude/scratch/<role>/<task>/`, an existing folder. `ADOPTING.md` step 9 adds `.claude/scratch/` to `.gitignore`.
- **Ships:** B42, B43, B44, B45, B46, B47, B48, B49, B50.

**Upgrade** from 1.2.x (`docs/UPGRADING.md` sect. 7):
1. Back up, including the whole `.claude/tickets/` folder, and stop the viewer.
2. Copy `tickets.py`, `author.py`, `serve.py`, `app.js` and `style.css` into the tool folder (or everything except `icons/`; never `icons/`), and take the schema's `tags` node.
3. Rename any all-digit tag name, and replace any integer tag value, by hand. Then run `author.py tags --probe --dry-run`, then `author.py tags --probe`.
4. `author.py --convert-all --dry-run`, then `author.py --convert-all`.
5. `tickets.py validate`.
6. Optionally, add `tag_groups`, and fix each ticket `validate` lists.
7. Take the rules-doc changes, and install the 1.3.0 skill with your Settings rows, after a review. Replace a "Scratch for body files" row that points at the temp folder (the harness's scratchpad under `AppData\Local\Temp`), and the rules-doc bullet and CLI examples that name it, with `.claude/scratch/<role>/<task>/`; don't keep it (B54, added in 1.3.1).
8. Start the viewer again. Add `.claude/tickets/tags.json.lock` to `.gitignore`, and commit the store.
9. If you run the hooks: stage the new `hooks/tickets/`, run its self-test there with `--scratch <project>/.claude/scratch/<role>/<task>/`, have it reviewed, replace yours, and run the self-test again (sect. 6).
10. Tell the maintainer the version you run.

## [1.2.2] - 2026-09-30

**Import from another tracker, a safer writer, and a hooks self-test that takes a scratch folder you name.** A **patch**: no configuration or JSON structure change (user rule, 2026-09-30: "Patch should be for smaller changes"). The schema and the example config are byte-identical to 1.2.1, and the skill differs only in its version row. The steps are in `docs/UPGRADING.md`, per-release notes, 1.2.2.

- **Import (B40, from an adopter):** `tickets.py import <file.json> [--dry-run]` creates one ticket per record of a JSON array, in input order, with the ids `new` would give.
  - Each record keeps its own `created` and `updated`, and its links may point at other tickets in the same file.
  - Every record is validated first. A failure reads `FAIL record <index> (<id>): <key>: <why>`, and nothing is written unless all pass. `--dry-run` only validates.
  - It never replaces a ticket file. A failure part-way, or Ctrl+C, removes what the run wrote.
  - It survives being killed. The run journals its batch before it writes anything. The next `import` refuses to start while the leftovers are there, and `import --abort-interrupted` removes exactly that batch's unchanged tickets and temporary files. A ticket changed since is kept and named.
  - It validates the existing store first, and refuses when the store has problems.
  - `ADOPTING.md` gains "Migrating from another tracker": the record format, an example and seven checked steps.
- **A safer writer (B41):**
  - `new` creates its file exclusively and never overwrites. If another writer took the id meanwhile, it takes the next one, up to 20 times, and prints the id it wrote.
  - `set` writes the ticket whole to a temporary name and moves it over the file, so a failure part-way can't leave a cut-off ticket. If another process holds the file open, it writes in place as before.
  - `new` and `set` refuse a line break in `--summary` and `--target`, and `validate` reports one in `summary` or `target_patch`: `has a line break; it must be one line`. That covers every character that ends a line: LF, CR, VT, FF, FS, GS, RS, NEL, U+2028 and U+2029. No adopter's store has one (checked 2026-09-30).
  - `new` and `set` report every write failure as one `ERROR could not write ...` line, with no temporary file left.
  - While an import is running, `new` takes the id after that batch's last.
  - A `new`, `set` or `import` leaves a short-lived `.tmp` file in the tickets folder while it runs. `validate`, `list` and the viewer ignore it. `ADOPTING.md` step 9 adds `.claude/tickets/*.tmp` to `.gitignore`.
- **Hooks self-test (B38, B39, B36, from adopters):**
  - `--scratch <dir>` (or `--scratch=<dir>`) puts its throwaway folders in a folder you name and skips the system temp folder entirely. The folder may lie inside the project, so a project that keeps every write in its repo can run the installed self-test (B38).
  - That folder must exist. It is refused, with exit 2 and nothing written, inside the hooks package, inside a `.claude/tickets` board or an export's `payload/`.
  - Any argument other than `--self-test`, `--scratch <dir>` or `--scratch=<dir>` is refused with exit 2, so a mistyped `--scratch` never falls back to the temp folder. 1.2.1 ignored extra arguments. Live hook calls are unchanged.
  - A refused `TMP` no longer gets a transient probe file. The temp candidates are checked before anything is written, and the refusal names the variable that pointed there (B39).
  - A temp or `--scratch` folder that can't hold a folder, such as one whose ACL denies it, is skipped or refused after one try.
  - `fixtures.py`'s docstring says what is protected (B36).
  - The self-test grows to 365 assertions.
- **Docs:** `RULES.md`, `ADOPTING.md` "Optional: ticket hooks" and `UPGRADING.md` sect. 6 document `--scratch`, and "run it from an export" as the alternative. The rules-doc template lists `import` and says a summary is one line.
- **The live hooks are unchanged:** the rules, log-only, fail-open and `settings.snippet.json`.
- **Ships:** B36, B38, B39, B40, B41.
- **The maintainer's master site** (not part of the ticket system): B37. A port that fails the HTTP probe gets no connect and no request until the new `not_viewer_recheck` back-off ends (a `config.json` key of the master site, default 900 s), then one more probe (a bare connect, then a connection with `GET /`). This replaces the fixed 300 s re-probe, which also connected on every scan.

**Upgrade** from 1.2.1 (`docs/UPGRADING.md`, per-release notes, 1.2.2):
1. Stop the viewer, copy the whole tool folder, and run `validate`. *Corrected by B43 (1.3.0): copy `tickets.py`, the one file that changed, or everything except `icons/`; never `icons/`. If you copied `icons/`, re-bake with `make_icons.py` (`docs/UPGRADING.md` sect. 3).*
2. Set the skill's version row to `1.2.2`.
3. If you run the hooks: stage the new `hooks/tickets/`, run its self-test there, and have it reviewed. Then replace yours and run the self-test again, with `--scratch <dir>` if your project keeps scratch inside the repo (sect. 6).

## [1.2.1] - 2026-09-30

**The hooks' self-test runs on a staged copy.** A **patch**: only the optional hooks and the docs change, with no configuration or JSON structure change (user rule, 2026-09-30: "Patch should be for smaller changes"). The tool folder, the schema and the example config are byte-identical to 1.2.0, and the skill differs only in its version row.

- **Hooks self-test (B35, from an adopter):**
  - It writes nothing inside the copy it runs from, wherever that copy is staged, or inside an installed project. Its scratch folders go to the system temp folder.
  - They are removed even when a case fails or raises. A folder it has to leave is named on stderr.
  - It runs with bytecode off, so no `__pycache__` appears either.
  - If `TMP` points into the package, or into its project when installed, it prints one `self-test: refused: ...` line and exits 2 instead of writing there. That includes `\\?\` and `\\localhost\c$` aliases. Exit 1 still means a case failed.
  - The self-test grows to 308 assertions.
- **Docs:** `ADOPTING.md` "Optional: ticket hooks" and `UPGRADING.md` sect. 6 run the self-test on the staged copy for the review and again after install, both as `python -I -S -B ...`.
- **The live hooks are unchanged:** the rules, log-only, fail-open and `settings.snippet.json`.
- **Ships:** B35.

**Upgrade** from 1.2.0 (`docs/UPGRADING.md`, per-release notes, 1.2.1):
- **Without the hooks:** set the skill's version row to `1.2.1`. Nothing else changes.
- **With the hooks:** stage the new `hooks/tickets/`, run its self-test there, and have it reviewed. Then replace yours and run the self-test again (sect. 6).

## [1.2.0] - 2026-09-30

**Adopters' first reports on 1.1.0.** **Minor**, because `config.json` gains a key (user rule, 2026-09-30: "Minor only updates when a configuration or json structure change happens"). The steps are in `docs/UPGRADING.md` sect. 5.

Structure: config.json gains the optional icon_color key (the example config doesn't set it).

- **Icon colour (B31):** the optional `config.json` key `icon_color`, written `#rrggbb` with a default of `#007acc`, sets the background that `make_icons.py` bakes. `make_icons.py --color "#rrggbb"` overrides it; quote the value, since an unquoted `#` starts a comment. A bad value stops `tickets.py`, `serve.py` and `make_icons.py` with one `ERROR` line naming the key, and `serve.py --stop` still works. Without the key, the icons are byte-identical to 1.1.0's. `make_icons.py --text XY` now reads `config.json` when it finds one, and each `wrote` line shows the colour.
- **`identify` reads `tool_dir` (B32):** without `--cli-dir`, `release.py identify` looks for the CLI at `config.json`'s `tool_dir` first, then at `src/tools/tickets` and `tools/tickets`. It refuses a `tool_dir` that isn't a relative path inside the repo: absolute, a drive, UNC, `..`, a device name, one that leaves the repo through a junction or symlink, one that overlaps the board, or one without `tickets.py`. A refused value, or an unreadable `config.json`, prints one note and falls back. The final `ERROR` lists every path tried.
- **Trailing newlines (B34):** every anchored check in `tickets.py`, `serve.py` and the hooks' ticket store now rejects a value that ends in a line break. That covers `id_prefix`, tag names and colours, `icon_color`, `server_version`, and the schema patterns for ids, links, commits, files, tags and dates. A rejected value prints on one line, with `\n` written out. All five adopters' stores still validate.
- **The skill (B29, B30):**
  - Its description names the bare requests: "new ticket", "file a ticket", "log a finding", "list tickets", "show a ticket", "mark it done", "set a status" and "what's on the board".
  - It cites rules-doc sections by name, not number. The Settings "Rules doc" row maps each name to the copy's own section, so a copy keeps its numbering.
- **Docs:**
  - `ADOPTING.md` step 9 recommends `text eol=lf` for the tool folder, the skill and the hooks, with the icons marked binary (B33).
  - `UPGRADING.md` gains sect. 5, "1.1.0 -> 1.2.0", which lists each adopter's 1.0.0 icon colour. The hooks section becomes sect. 6.
  - `tool_dir` is no longer described as read only by the hooks.
- **Ships:** B29, B30, B31, B32, B33, B34.

**Upgrade** from 1.1.0 (`docs/UPGRADING.md` sect. 5):
1. Stop the viewer.
2. Copy the whole tool folder. *Corrected by B43 (1.3.0): copy `make_icons.py`, `serve.py` and `tickets.py`, the three files that changed, or everything except `icons/`; never `icons/` (`docs/UPGRADING.md` sect. 3).*
3. Optionally, set `icon_color` and re-bake. To keep a 1.0.0 colour, see `docs/UPGRADING.md` sect. 5 step 5.
4. Take the skill whole, with your Settings rows, after a review.
5. Map your rules-doc sections in its "Rules doc" row.
6. Take the `icon_color` and `tool_dir` rows and the icon wording into your rules doc.
7. Optionally, add the `.gitattributes` lines.
8. If you run the hooks, take the new `hooks/tickets/` after a review.

## [1.1.0] - 2026-09-30

**Config-driven, drop-in.** A copy now works in any project from `.claude/tickets/config.json` alone. No code is edited on adoption, so an upgrade is a plain file copy. **Minor**, because the configuration and JSON structures change (user rule, 2026-09-30: "Minor only updates when a configuration or json structure change happens"). The steps are in `docs/UPGRADING.md` sect. 4.

Structure: config.json gains viewer_port and six optional keys; ticket.schema.json status enum gains in_review; id and links.tickets patterns generalised; the owner_area and author example enums change.

- **Configuration and JSON structure:**
  - `config.json` gains `viewer_port`, which `serve.py` needs unless `--port` is given, and six optional keys: `short_name`, `viewer_service`, `theme_key`, `server_version`, `icon_text` and `tool_dir`. Each has a default derived from `store_name` or `id_prefix`.
  - `id_prefix` must match `^[A-Z][A-Z0-9]*-$`, and `store_name` is required. A missing or bad key stops the CLI and the viewer with one `ERROR .claude/tickets/config.json: ...` line naming it. Unknown keys are ignored.
  - `ticket.schema.json`: the `status` enum gains `in_review`. The id and `links.tickets` patterns accept any prefix (`^[A-Z][A-Z0-9]*-[0-9]{4,}$`), and `validate` checks that each id and link carries the store's own prefix. The title is `Ticket`.
  - A release manifest records its `normalize` scheme (2 from 1.1.0; 1.0.0's has none and means 1), and files of a new kind, `optional`.
  - The example `owner_area` and `author` enums in `ticket.schema.json` (now `core, ui, docs, project` and `user, pm, core, ui, peer`) and the example `tags.json` are project-neutral (B24). They are starting points that each project adapts, so an adopter keeps its own.
  - `/api/health` and `/api/tickets` keep their shape.
- **No code edits on adoption (B1-B4):**
  - `tickets.py` finds the repository by walking up to `.claude/tickets/config.json`, so one file works at `src/tools/tickets` and `tools/tickets` (B2).
  - `index.html` and `manifest.webmanifest` are templates that `serve.py` fills from `config.json`: names, id prefix, theme key. `app.js` reads them from the page and links only the store's own ids (B1).
  - The port, the health marker and the `Server` header come from `config.json` (B1).
  - marked and DOMPurify moved into the tool folder, `<CLI_DIR>/lib/`. `serve.py` falls back to `<repo>/external/` while a file is missing there (B3).
  - `make_icons.py` draws A-Z and 0-9 from `icon_text`, or `--text`, and sizes three letters to fit (B4).
- **New status `in_review` (B17):** after `in_progress`, and counted as active. The CLI (`--active`), the viewer (order, "In review" pill, counts), the skill, the rules doc and hook T2 carry it. A status the page doesn't know shows as a neutral pill.
- **Skill and rules doc (B5, B6, B11, B16, B17):**
  - The skill is project-neutral outside 14 Settings rows (B5). New rows: Store absolute, Design questions, Author and Tag for an issue a peer sends, Ticket system source.
  - It takes one adopter's peer rules (B6) and another's request rules with the provenance line (B16).
  - Reports to the maintainer's session are a plain message, confirmed in a line (B11).
  - `tickets.md` is a template with `<...>` placeholders, and gains sect. 6, "the ticket system itself".
- **Optional ticket hooks (B12):** new, log-only, installed per project in `.claude/hooks/tickets/`, with the wiring in `settings.snippet.json`.
  - T1 logs when work resumes after a quiet spell and the viewer is down. T2 logs a write into the ticket system's source that no Ticket Master request covers. They read `viewer_port`, `viewer_service`, `store_name`, `tool_dir`, `id_prefix` and an optional `source_of_truth_session` from `config.json`.
  - Fixed from the first review: the shell parser is linear and bounded, a `<` operand is a read, every JSON read survives `RecursionError`, a `tool_dir` that overlaps the board is ignored with a breadcrumb, and log samples are secret-masked.
  - T2 also protects `.claude/hooks/tickets/**`, except `hooklib/policy.py`, and ties on `in_review` as well as `in_progress` (B17).
- **Release tooling (B14, B15, B19, B20, B22):**
  - `identify` prints an adapted or optional file that isn't installed as `not installed`, never `missing`, and shows `[expected at: ...]` for a file it didn't find (B14).
  - `whitespace` (scheme 2, in 1.1.0 manifests) no longer covers mixed tab and space indentation, or a non-breaking space or form feed at a line end.
  - A broken manifest gives a clean ERROR.
  - The skill's Settings section is found exactly: `## Settingsfoo` is another section, and a heading inside a code fence neither starts nor ends it. A table row indented by up to 3 spaces counts as a row.
  - `export` refuses Windows-aliased names.
  - `check` warns about uncommitted payload changes.
  - "local change(s)" wording.
  - `check` verifies the version level (B19). A JSON-structure change needs a minor bump, and a minor bump needs such a change or a `Structure:` line in its changelog entry. A major bump only warns.
  - `check --release` refuses while `BACKLOG.md` lists open items; a plain `check` warns (B20).
  - The three icons are `adapted` in a scheme 2 manifest, since each project bakes its own (B22). `identify` shows them as `(yours: adapted per project, not compared)`, so a correct 1.1.0 copy has no local change. 1.0.0's manifest still records them as product, and they show `unverified` there.
  - `identify` names the closest release by the fewest local changes and missing files (an `unverified` file byte-identical to another release's file counts as a local change), then the largest share of matching product files, then the most unverified, then the newest (B22).
- **Fixes (B7, B8, B9, B23, B25, B26):**
  - Racing `serve.py` starts no longer delete the winner's `serve.pid` (B7).
  - The banner lists only the default-route adapter's address as the LAN URL (B8).
  - `show` prints non-ASCII links as `?` (B9).
  - `list` widens the id column only for ids longer than 8 characters, so a longer prefix lines up. `serve.py --stop` recognises its script however the path is spelled (long or 8.3 short, any case, through a junction or symlink, or relative to the folder it was started from), and still confirms a viewer whose `viewer_service` changed while it ran. The `Server` header lost its trailing space (B23).
  - `serve.py --port` outside 1-65535 is a clean `ERROR`, not a traceback. A foreground run never overwrites a `serve.pid` that names a live viewer of the same script, so a test on a second port can't orphan the main one. A broken `config.json` shows its `ERROR` when the viewer starts, and `--stop` works regardless (B25).
  - The viewer passes DOMPurify `USE_PROFILES`, the real option's spelling, so SVG and MathML are stripped from ticket bodies. Scripts were stripped before (B26).
- **Faster start (B28):** a detached `serve.py` start on a free port prints `started` in about 1 s instead of about 4 s. One 0.3 s connect check replaces two 1.5 s probes, and a start now waits up to 15 s for the viewer to come up.
- **Removed:** `payload/external/` (now `<CLI_DIR>/lib/`), and `dot-claude/docs/portable_workflow.md`, which was not part of the ticket system (B14). Adopters who copied it keep it as their own.
- **Ships:** B1, B2, B3, B4, B5, B6, B7, B8, B9, B11, B12, B14, B15, B16, B17, B19, B20, B22, B23, B24, B25, B26, B28.
- **The maintainer's master site** (not part of the ticket system): B10, B13, B18, B21, B27.
  - The banner lists only the default-route address (B10).
  - Tabs of systems offline longer than `offline_grace` are dropped, and their proxy and feed are released (B13).
  - The page is mobile friendly (B18).
  - No traceback when a relayed event stream ends after its browser left (B21).
  - Live streams are ended after 60 s without data, and a relayed stream whose write to the browser has been stuck for 60 s ends, so a vanished viewer or browser no longer ties up a thread (B13, B27).

**Upgrade** from 1.0.0 (`docs/UPGRADING.md` sect. 4, which says where your 1.0.0 code holds each value):
1. Stop the old viewer with its own `serve.py --stop`, before copying anything. A 1.1.0 `serve.py` refuses a port held by an old viewer whose health marker it doesn't recognise.
2. Add `viewer_port`, plus the keys that pin your 1.0.0 names (marker, `short_name`, `theme_key`, `Server` header).
3. Copy the whole tool folder, `lib/` included. *Corrected by B43 (1.3.0): every file changed, so copy everything except `icons/`; never `icons/` (`docs/UPGRADING.md` sect. 4 step 5).*
4. Delete `external/marked/` and `external/dompurify/` (or a `<CLI_DIR>/vendor/` copy).
5. Re-bake the icons.
6. Add `in_review` to the schema's `status` enum.
7. Take the rules-doc changes.
8. Install the 1.1.0 skill with your Settings rows, after a review.

The hooks are optional (`docs/ADOPTING.md`, "Optional: ticket hooks").

## [1.0.0] - 2026-09-30

**Baseline.** The ticket system exactly as the project that first built it ran it on 2026-09-30, the day the maintainer took ownership of the source. Nothing in it changed. This release gives every existing copy a version to record.

- **Source:** the working tree of that project's repository at a commit of 2026-09-30, plus that tree's uncommitted edits to `.claude/skills/tickets/SKILL.md` and `.claude/docs/tickets.md` as they stood at 10:40 local time on 2026-09-30. Every file is byte-identical to that tree. `releases/1.0.0.json` holds, per file, a `raw` SHA-256 of the exact bytes, which `release.py check` compares and so proves that byte identity, plus the normalized hashes (line endings, indentation tabs, trailing spaces, and for the skill its Settings table rows) that `release.py identify` uses to match installed copies.
- **Contents:**
  - the CLI `tickets.py` (new, set, list, show, validate);
  - the read-only viewer: `serve.py`, the page, the icons and `make_icons.py`;
  - marked 18.0.14 and DOMPurify 3.4.16, vendored;
  - the ticket schema and tags;
  - the `tickets` skill;
  - the rules doc `tickets.md` and `portable_workflow.md`.
- **Known limitation:** 1.0.0 is hard-wired to the project that first built it. Adopting it means editing code for the id prefix, brand, port, service marker and install depth; `docs/ADOPTING.md` lists every place. A later release moves all of that into `config.json`.

**Upgrade:** nothing to install. A project that copied the system on 2026-09-30, before 1.1.0, records `1.0.0`. `python <SRC>/tools/release.py identify <repo>` shows how its copy compares, file by file (`docs/UPGRADING.md` sect. 1).
