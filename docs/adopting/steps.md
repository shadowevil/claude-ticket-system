# Adopting, steps 1-11

*Assessed 2026-10-21 (B47, under the documentation standard): kept whole. One continuous procedure, read whole and in order; its steps cite each other throughout.*

*Part of the adoption guide, `../ADOPTING.md`: read its opening first, for `SRC`, `REPO` and `SCRATCH`. The optional parts are `migrating.md` and `hooks.md`, done after step 10 and before step 11. `UPGRADING.md` is `../UPGRADING.md`, an index too.*

## 1. Decide your values

| Value | Rule | Example |
|---|---|---|
| `PREFIX` | A capital letter, then capitals or digits, then a hyphen (`^[A-Z][A-Z0-9]*-$`). Unique among the boards you or your peers run; on the maintainer's machine, also not in the Adopters table of the maintainer's `ticket-system/README.md` | `XY-` |
| `FIRST` | The first ticket number, usually 1 | `1` |
| `NAME` | The store name. The page title and brand show `<NAME> Tickets` | `Example` |
| `PORT` | **Unique on this machine.** 18000-19000 is the suggested range. If your machine has its own rule for viewer ports (for example a dashboard that only scans a range), that rule wins. Not listening now (check below), and not configured by another board on this machine; on the maintainer's machine, also not in the Adopters table of the maintainer's `ticket-system/README.md`. `serve.py` checks only that it is a port number (1-65535, else an `ERROR`) | `18600` |
| `CLI_DIR` | Where the tool goes: `src/tools/tickets` (recommended), or `tools/tickets` if your repo has no `src/` | `src/tools/tickets` |
| `AREAS` | Your team's `owner_area` values: 2-6 areas that write fixes | `core, ui, docs, project` |
| `AUTHORS` | Who may file: `user`, `pm`, your roles, and `peer` for issues other projects send | `user, pm, core, ui, peer` |

The viewer's health marker (`viewer_service`) comes from `NAME` unless you set it: lowercase, each run of characters other than `a-z` and `0-9` becomes `-`, trimmed, plus `-tickets`. `Example` gives `example-tickets`. Call the result `MARKER`. It should differ from every other adopter's marker; a different `NAME` gives a different one.

Check the port is free, on any system. Expect `free`:

```bash
python -c "import socket; s = socket.socket(); s.settimeout(1); print('in use' if s.connect_ex(('127.0.0.1', <PORT>)) == 0 else 'free')"
```

It exits 0 either way; read the word. On Windows, `Get-NetTCPConnection -State Listen -LocalPort <PORT> -ErrorAction SilentlyContinue` lists a listener instead. For a free port it prints nothing **and exits 1**, which is the success case here, not a failure.

## 2. Get the release

**From a clone of the GitHub repo:** skip the export. The clone is the release: `PAYLOAD` is `<SRC>/payload/`. (The public repo tags each release from 1.3.1 on, so the export below also works in a clone for 1.3.1 and later; you don't need it.)

**Check:** `<SRC>/VERSION` reads `1.4.0`, and `git -C <SRC> status --short` prints nothing, so you install the release as published.

**On the maintainer's machine,** SRC is the maintainer's source folder. Export the release from it into your scratch:

```bash
python <SRC>/tools/release.py export 1.4.0 <SCRATCH>/ticket-system-1.4.0
```

The export reads the release tag, `tickets-v1.4.0`, so it works only once that tag exists; before then it stops with `ERROR cannot read tickets-v1.4.0: ...`. (The maintainer's pre-release test exports a branch with `--ref <branch>`; an adopter never does.) Everything below copies from `<SCRATCH>/ticket-system-1.4.0/payload/` (call it `PAYLOAD`), never from SRC's working tree, which may be mid-change.

**Check:** the command prints `exported tickets-v1.4.0 to ...`, and `PAYLOAD/../VERSION` reads `1.4.0`.

## 3. Copy the files

| From `PAYLOAD/` | To `REPO/` |
|---|---|
| `src/tools/tickets/`, the whole folder: the scripts (`tickets.py`, `author.py`, `serve.py`, `make_icons.py`), the page files, `icons/` and `lib/` | `<CLI_DIR>/` |
| `dot-claude/tickets/ticket.schema.json`, `tags.json` | `.claude/tickets/` |
| `dot-claude/docs/tickets.md` | `.claude/docs/tickets.md` (you adapt it in step 7) |
| `dot-claude/skills/tickets/SKILL.md` | **not yet**; it goes to `SCRATCH` and is installed after review (step 8) |
| `dot-claude/hooks/tickets/` | **not now**; the hooks are optional (the "Optional: ticket hooks" section, `hooks.md`) |

`dot-claude/tickets/config.json` is an example; you write your own in step 4. No ticket files are in the payload.

`<CLI_DIR>/lib/` holds marked and DOMPurify, which the page loads. The tool folder is self-contained: nothing goes to `REPO/external/`.

**Check:** these three files exist:

```bash
ls REPO/<CLI_DIR>/tickets.py REPO/<CLI_DIR>/lib/marked/marked.umd.min.js REPO/<CLI_DIR>/lib/dompurify/purify.min.js
```

## 4. Write `.claude/tickets/config.json`

```json
{
  "id_prefix": "<PREFIX>",
  "first_ticket_number": <FIRST>,
  "store_name": "<NAME>",
  "viewer_port": <PORT>
}
```

UTF-8 with LF, 2-space indent. `id_prefix` and `store_name` are required; `serve.py` also needs `viewer_port` (or `--port`).

Add an optional key only when its default doesn't suit you:

| Key | What it sets | Default |
|---|---|---|
| `first_ticket_number` | The first id's number | `1` |
| `short_name` | The home-screen name (manifest `short_name`, `apple-mobile-web-app-title`) | `store_name` |
| `page_title` | From 1.4.0: the page title and heading, any string, used as written. Without it, or with an empty string, the title is `store_name` + ` Tickets`, so a `store_name` of `DotR` gives `DotR Tickets`; set this to drop or change the suffix | `store_name` + ` Tickets` |
| `viewer_service` | The `/api/health` marker | from `store_name` (step 1) |
| `theme_key` | The browser storage key for the page's theme | `viewer_service` + `-theme` |
| `server_version` | The HTTP `Server` header: visible ASCII, no spaces | `viewer_service` |
| `icon_text` | The icon letters: 1-3 of A-Z and 0-9 | `id_prefix` without the hyphen, first 3 characters |
| `icon_color` | The icons' background: `#rrggbb`, either case (step 5) | `#007acc`, Visual Studio blue |
| `tool_dir` | The tool folder, relative to `REPO`. The optional hooks guard it, and `release.py identify` compares it. Set it when `CLI_DIR` is neither `src/tools/tickets` nor `tools/tickets` | the hooks: the folder of `viewer_script` if set, else the first of `tools/tickets` and `src/tools/tickets` that holds `tickets.py`. `identify`: the first of `src/tools/tickets` and `tools/tickets` that holds it |
| `tag_groups` | From 1.3.0: the tags a ticket must carry (step 6) | no groups |

Unknown keys are ignored, so a project may keep its own there.

**Check:** `python <CLI_DIR>/tickets.py --help` prints the line `<NAME> ticket store (.claude/tickets).` A mistake in the file prints `ERROR .claude/tickets/config.json: ...` naming the key instead.

## 5. The schema's team enums, and the icons

`.claude/tickets/ticket.schema.json` is generic, apart from two enums that name a team:
- `properties.owner_area.enum` -> your `AREAS`;
- `properties.author.enum` -> your `AUTHORS`.

The released file carries the examples from step 1 (`core, ui, docs, project` and `user, pm, core, ui, peer`), so keep them if they fit.

Leave everything else as released. The id pattern accepts any prefix, and the CLI checks that each id carries yours.

Then bake the icons. The payload's icons say `XY`:

```bash
python <CLI_DIR>/make_icons.py
```

It draws `icon_text` from `config.json`, and any letters A-Z or digits 0-9 work. The background is `icon_color`, by default `#007acc`. To give your icon its own colour, so it stands apart from other projects' icons on a home screen, set `icon_color` in `config.json` (step 4) and bake again. To try a colour without saving it, pass `--color`:

```bash
python <CLI_DIR>/make_icons.py --color "#68217a"
```

Quote the colour: unquoted, the `#` starts a comment in bash and in PowerShell. A value that isn't `#rrggbb` stops with one line, `ERROR --color must be a colour written #rrggbb (e.g. #007acc), not '...'`, or `ERROR .claude/tickets/config.json: icon_color must be ...` for the key. A bad `icon_color` stops the CLI and the viewer with that line too.

**Check:**
- `make_icons.py` prints three `wrote icons/... (..., text <your icon text>, colour <your colour>)` lines and a `bake cost` line.
- `python <CLI_DIR>/tickets.py new --help` lists your `AREAS` under `--owner` and your `AUTHORS` under `--author`, and `--status` offers `in_review`.

## 6. Tags

The released `.claude/tickets/tags.json` is an example tag store; adapt it to your project. From 1.3.0 the store numbers its tags, and a ticket holds tag ids:

```json
{
  "format": 2,
  "next_id": 10,
  "tags": {
    "1": { "name": "bug", "color": "#e5484d", "description": "Behaves wrongly; not a design question." }
  }
}
```

- An id is a positive whole number, below `next_id`. Ids are given in order, never reused and never renumbered.
- A name is unique: lowercase letters, digits and `_`, with at least one letter or `_`. An all-digit name would read as an id. A hyphen is not allowed: where an `owner_area` value has `-` (`re-docs`), the tag is written with `_` (`re_docs`).
- A colour is `#rrggbb`, readable on both the dark and light themes.

Change the store with `author.py`. It checks the store first and writes it whole, holding `.claude/tickets/tags.json.lock` while it works, so two writers take turns. A writer that waits 30 s refuses with an `ERROR` naming the lock file. If no `tickets.py` or `author.py` is running, one was killed while it held the lock: delete the file. Nothing deletes a lock automatically.

```bash
python <CLI_DIR>/author.py tags
python <CLI_DIR>/author.py tags rename core engine
python <CLI_DIR>/author.py tags add net --color "#2b8fa3" --description "Example: networking."
```

- **Keep the generic tags:** `bug`, `cleanup`, `docs`, `performance`, `test`, `tooling`.
- **Area tags:** make them match your `AREAS`. The example has `core` and `ui`, so rename them and add one per area. `docs` is an area tag too. A rename keeps the id, so no ticket changes.
- **A rename doesn't touch `tag_groups`.** If a group in your `config.json` names the old tag (the example config's `area` group names `core` and `ui`), change the name there too, at once. `author.py tags rename` warns `config.json tag_groups: group <g> still names '<old>'; ...`, and until you fix the group every writer refuses: a group naming a tag the store lacks is a config error.
- **Peers:** if peers may send you issues, rename `peer` to what they send: a `peer_<project>` tag per sender, or one for all, such as `downstream`. The skill's Settings name it (step 8).
- **Drop an example tag:** delete its entry from `tags.json` by hand while no ticket uses it. Leave `next_id` as it is.

**Tag groups (optional).** A tag group says how many of a set of tags every ticket must carry. Without `tag_groups` in `config.json` there are none. A group is written with tag names:

```json
"tag_groups": [
  { "name": "type", "tags": ["bug", "cleanup", "docs"], "min": 1, "max": 1 }
]
```

- `min` defaults to 0. `max` defaults to `null`, which means any number. A tag may sit in more than one group.
- A group name follows the tag-name rule. A tag the store doesn't hold is a config error, and every writer refuses until you fix it.
- `new`, `set`, `import` and `author.py new` refuse a ticket that breaks a group, and `validate` fails it.
- The released example config has one group, `area`: at most one of `core` and `ui`.

**Check:**
- `python <CLI_DIR>/author.py tags` lists your tags, each with `0` tickets.
- `python <CLI_DIR>/author.py rules` prints each group as a rule, such as `type: pick exactly 1 of bug, cleanup, docs`, or `no tag groups (config.json has no tag_groups)`.
- `python <CLI_DIR>/tickets.py validate` prints `OK: 0 tickets valid against the schema, tags and links`.

## 7. Rules doc

`.claude/docs/tickets.md` is a template. Fill it in:
- the placeholders its opening paragraph lists: `<NAME>`, `<PREFIX>`, `<FIRST>`, `<PORT>`, `<CLI_DIR>`, `<REPO>`, `<SCRATCH>`;
- sect. 2: `<AREAS>` and `<AUTHORS>`, one line each on what an area covers;
- sect. 4: after the port, say what else on this PC it keeps clear of;
- sect. 5: `<Add any role limits your agent briefs set.>`, and `<where design reasoning goes>`;
- sect. 5a: the peers table, one row per peer, or "none";
- then delete the opening paragraph.

Keep the rules themselves. **The section numbers are yours:** keep the template's, or renumber to fit your doc. The skill never cites a section by number. It names the sections it relies on, and your Settings "Rules doc" row (step 8) maps each name to your number. The template's numbers:
- the severity scale: sect. 2, the `severity` row;
- the rules section: sect. 5. One ticket per finding, measure first, status tracks the work (`in_review` included), close with evidence, who writes;
- the peer exchange section: sect. 5a, exchanging issues with another project's board. Sending an issue, and filing one a peer sends, with the provenance line;
- the ticket-system section: sect. 6, the ticket system itself. The maintainer owns the source, no local fork, releases, the optional hooks.

Sect. 7, what is not built, is yours to keep too; the skill doesn't name it.

Leave the provenance line's `<session name>`, `<from-session id>` and `<YYYY-MM-DD>`, and the `peer_<project>` naming rule, as they are: they are formats, not placeholders.

**Check:** expect no output:

```bash
grep -n -E "<(NAME|PREFIX|FIRST|PORT|CLI_DIR|REPO|SCRATCH|AREAS|AUTHORS)>|<where design|<Add any|Say here|Template from" REPO/.claude/docs/tickets.md
```

Then read the sect. 5a table: it lists your peers, or says "none".

## 8. The skill (reviewed before install)

1. Put `PAYLOAD/dot-claude/skills/tickets/SKILL.md` in `SCRATCH` and edit **only its Settings table rows**. It has 14:

   | Row | Your value |
   |---|---|
   | Ticket system version | `1.4.0`, as shipped |
   | CLI | `python <CLI_DIR>/tickets.py` |
   | Store | `.claude/tickets/` and the note on what each file holds, as shipped |
   | Store, absolute (for replies to a peer) | `<REPO>\.claude\tickets\`, the absolute path |
   | Rules doc | `.claude/docs/tickets.md`, and your number for each section it names (step 7). The shipped row gives the template's |
   | Agent briefs | your path, such as `.claude/agents/*.md`, or "none: a dispatched agent's brief is the PM's dispatch prompt" |
   | Viewer | `python <CLI_DIR>/serve.py --stop`, then `python -u <CLI_DIR>/serve.py --foreground` as a session background task, with your port |
   | Scratch for body files | your path: `.claude/scratch/<role>/<task>/` inside the project, git-ignored (never a system temp folder or the harness's scratchpad) |
   | Backup before editing an existing file (PM only) | your command, or "none" |
   | Design questions | where a design question's reasoning goes: a plan folder or a decisions ledger |
   | Peer boards | "none", or per peer: project, session name, the absolute path of its tickets folder, and any rule such as "ask the user first". The maintainer is not a peer board |
   | Author for an issue a peer sends | `pm`, or `peer` if your `AUTHORS` has it |
   | Tag for an issue a peer sends | the tag from step 6, or "none" |
   | Ticket system source | the maintainer, as shipped; replace the `<SRC: ...>` placeholder with where you take releases from: the GitHub repo's URL (a clone kept in your scratch is temporary), a clone you keep, by its absolute path, or, on the maintainer's machine, the absolute path of the maintainer's source folder |

2. Anything else you think the skill needs goes to the maintainer. Your copy must match the release outside the Settings rows, and that includes the prose under the table.
3. **Have a separate read-only agent review it**: the global rule that every hook and skill write is reviewed. Install it at `REPO/.claude/skills/tickets/SKILL.md` only after a pass.

**Check:** the review passed, the installed file differs from `PAYLOAD/dot-claude/skills/tickets/SKILL.md` only in table rows under `## Settings (per project)`, and each number in the Rules doc row leads to the section it names in your rules doc.

## 9. Project wiring

- **`CLAUDE.md`**: add a short tickets section covering:
  - where tickets live;
  - that the CLI is the only writer, and that agents file through `author.py`, which writes through it;
  - that status tracks the work;
  - starting the viewer as a background task;
  - a pointer to the skill and the rules doc.
- **`.gitignore`**: add `build/`, or at least `build/tickets/` (the viewer's pid file and log) and, with the hooks, `build/hooks/`. Add `__pycache__/` too, and `.claude/tickets/*.tmp`: the CLI writes a ticket to a `.tmp` name first, and a killed `new`, `set` or `import` can leave one behind; `tickets.py import --abort-interrupted` removes it once that process is gone. Add `.claude/tickets/tags.json.lock` as well: `author.py` holds that lock while it changes the tag store (step 6). And `.claude/scratch/`, your `SCRATCH` (body files, exports, the hooks self-test's folders).
- **Line endings (`.gitattributes`).** The CLI writes tickets with LF, and the release's files are LF. Keep them so in your checkout: with `core.autocrlf=true`, the Git for Windows default, a branch switch or a merge checks the tool folder, the skill and the hooks out again with CRLF, and then `identify` still matches them but the bytes differ from the release. Add these lines to `REPO/.gitattributes`, with your `CLI_DIR` filled in:

  ```text
  <CLI_DIR>/** text eol=lf
  <CLI_DIR>/icons/*.png binary
  .claude/skills/tickets/** text eol=lf
  .claude/hooks/tickets/** text eol=lf
  .claude/tickets/*.json text eol=lf
  ```

  Keep the icons line after the `<CLI_DIR>/**` line: the later line wins, so the PNGs stay binary. The hooks line does no harm without the hooks.

**Check:**
- `git status` in `REPO` lists no `build/` or `__pycache__/` entries after step 10, and `git check-ignore .claude/tickets/tags.json.lock` prints the path.
- `git check-attr text eol -- <CLI_DIR>/tickets.py .claude/skills/tickets/SKILL.md .claude/tickets/config.json` prints `text: set` and `eol: lf` for each, and `git check-attr text -- <CLI_DIR>/icons/icon-192.png` prints `text: unset`.

## 10. Verify

Run from `REPO`:

```bash
python <CLI_DIR>/tickets.py validate
echo "Smoke test of the adopted ticket system." | python <CLI_DIR>/tickets.py new --summary "Ticket system adopted: smoke test" --severity low --owner <an area> --author pm --tags tooling --body-file -
python <CLI_DIR>/tickets.py set <FIRST> --status in_review
python <CLI_DIR>/tickets.py validate
python <CLI_DIR>/tickets.py list --active
python <CLI_DIR>/author.py tags
python <CLI_DIR>/serve.py
curl -s http://127.0.0.1:<PORT>/api/health
curl -s http://127.0.0.1:<PORT>/api/tickets
curl -s http://127.0.0.1:<PORT>/ | grep "<title>"
python <CLI_DIR>/serve.py --stop
```

- **First `validate`:** `OK: 0 tickets ...`.
- **`new`:** reads the piped line as the body and prints `created <PREFIX>NNNN - ...`, with `FIRST` padded to four digits. This check files with `tickets.py new` on purpose: it tests the CLI, the only writer, which `author.py` writes through. Agents still file through `author.py new` (step 9), which takes the same flags and prints the same `created` line. If you set `tag_groups`, add to `--tags` a tag for each group whose `min` is above 0; `new` names any group it misses.
- **`set`:** a bare number names the ticket; it prints `updated <PREFIX>NNNN (in_review low <area>)`.
- **Second `validate`:** `OK: 1 tickets ...`.
- **`list --active`:** shows the ticket as `in_review`, then `1 of 1 tickets`.
- **`author.py tags`:** shows `tooling` with `1` in the tickets column.
- **`serve.py`:** prints `started (pid N, bound to 127.0.0.1)`. From 1.4.0 the viewer binds localhost by default, so no Windows firewall prompt appears. Add `--all-interfaces` only where the LAN must reach it (a phone, another PC); a master site on the same PC needs no flag; that start may prompt, and you never change firewall settings from a script or agent. (`--local-only` is still accepted and changes nothing.)
- **`/api/health`:** returns `"service": "<MARKER>"`.
- **`/api/tickets`:** returns your one ticket, whose `tags` holds `tooling`'s id. `tags` is the store keyed by id, `tag_format` is `2`, and `problems` is empty.
- **The page title:** `<title><NAME> Tickets</title>`, or your `page_title` as written if you set one.
- **`--stop`:** prints `stopped the ticket viewer (pid N)`.
- **The page:** start it again and open `http://127.0.0.1:<PORT>/`. It shows `<NAME> Tickets`, your icon and your ticket with an "In review" pill. A `#<PREFIX>NNNN` URL selects the ticket.

Set the smoke-test ticket `done` when you are satisfied: `python <CLI_DIR>/tickets.py set <id> --status done`, with a line appended saying what verified it.

Then start the viewer for the user as a session background task: `python <CLI_DIR>/serve.py --stop`, then `python -u <CLI_DIR>/serve.py --foreground`.

**Check the master site,** if your machine runs one that lists ticket viewers: within a few seconds it lists yours, named after the page title.

*Before step 11, the two optional parts, if they apply: `migrating.md` (an earlier tracker) and `hooks.md` (the ticket hooks).*

## 11. Report to the maintainer

**On the maintainer's machine,** send the `Ticket Master` session one message with:
- your project name, `PREFIX`, `PORT` and `CLI_DIR`. Ticket Master runs `release.py identify` on your repo, which finds the tool through `tool_dir` or the two default folders, so it needs no `--cli-dir` from you;
- the version you installed (`1.4.0`), and whether you installed the hooks;
- the absolute path of your smoke-test ticket's JSON.

Ticket Master adds you to the adopter table and announces future releases to you.

**Check:** Ticket Master confirms in a line.

**Anywhere else** (you adopted from a clone), report the same three points to your user. Nobody keeps a list of adopters there: new releases appear on the GitHub repo.

Problems with the ticket system, or wrong steps in this guide, go to the maintainer: an issue on the GitHub repo, `https://github.com/shadowevil/claude-ticket-system/issues`, or, on the maintainer's machine, a message to `Ticket Master`. Give what you saw against what you expected, repro steps, and the version. **An issue is public:** draft it, with no private paths and no ticket text your user hasn't approved, show it to your user, and post it only with their OK. Ticket Master keeps no ticket board; it records each report on its backlog and confirms in a line.
