# 1-2. Identify what you run, and record your version

*Sects. 1 and 2 of the upgrade guide, `../UPGRADING.md`: read its opening first, for `SRC`, `REPO`, `SCRATCH` and `CLI_DIR`. A bare "sect. N" here is that guide's sect. N, and its index names the file. `ADOPTING.md` is `../ADOPTING.md`, an index too.*

## 1. Identify what you run

```bash
python <SRC>/tools/release.py identify <REPO>
```

This is read-only, and works from a clone as well as from the maintainer's source folder: it compares against every release recorded in `<SRC>/releases/`. For every recorded release it compares each installed file with that release's and prints a summary line, then one row per file that is not an exact match (`--verbose` lists those too). A row gives the state, the file's kind, its payload path, and where the file is in your repo: `[installed: ...]` when it was found, `[expected at: ...]` when it wasn't.

Where `identify` looks for your tool folder, in this order. The first line of its output names the one it used, `(CLI at ...)`:
1. `--cli-dir <folder>`, relative to `REPO`, when you pass it. It always wins.
2. `tool_dir` from `REPO/.claude/tickets/config.json`, when it is usable: a relative folder inside the repo, not the root and not the board (`.claude/tickets`), holding `tickets.py`. A path that is absolute, has a `..` segment, or leads outside the repo through a symlink or junction is not used.
3. The first of `src/tools/tickets` and `tools/tickets` that holds `tickets.py`.

A `tool_dir` it can't use prints one line, such as `note: config.json tool_dir '../x' ignored: has a '..' segment`, and a `config.json` it can't read prints `note: .claude/tickets/config.json ignored, tool_dir not read: <why>` (for example when the path isn't a ticket-system repo). Either way it goes on down the list. When nothing holds `tickets.py`, it stops with `ERROR no tickets.py under <repo> (tried ...); pass --cli-dir`, listing every path it tried. A copy whose tool is elsewhere sets `tool_dir`, or passes `--cli-dir`.

| State | Meaning |
|---|---|
| `exact` | Same content; line endings are ignored, so a CRLF checkout still matches. |
| `whitespace` | Same content apart from indentation and line ends. Counts as a match. What is ignored depends on the release (its manifest's `normalize` scheme). **From 1.1.0:** only indentation made purely of tabs, re-indented as 4 spaces per tab, and spaces and tabs at line ends. A line whose indentation mixes tabs and spaces, or ends in a non-breaking space or a form feed, is `differs`. **1.0.0** keeps its looser rule: mixed indentation is expanded too, and any trailing whitespace is dropped. |
| `settings-only` | (the skill) Same apart from the table rows of its `## Settings (per project)` section. The section's prose and every other section are compared. Counts as a match. |
| `unverified` | (1.0.0 only) A file that adopting 1.0.0 required editing, and it differs. A checksum can't tell those edits from a local change, so it does **not** count as a match: diff it (below). `identify` shows its number of diff lines. |
| `differs` | A **local change**: a real difference in a file the release expects unchanged. The row ends in `<- local change: diff it`. |
| `missing` | A product file or the skill that is not installed. |
| `not installed` | A file you may leave out: an `adapted` one, shown `(yours, optional)`, or an `optional` one, shown `(optional)`. It doesn't count as missing, so the rows agree with the summary. |

The kinds:
- `product`: installed unchanged.
- `skill`: installed unchanged except its Settings rows.
- `adapted`: yours, never compared: `config.json`, `tags.json`, `ticket.schema.json`, the rules doc `tickets.md` and, from 1.1.0, the three icons (`make_icons.py` bakes them per project). Their rows end `(yours: adapted per project, not compared)`.
- `optional` (from 1.1.0): the ticket hooks. When they are installed they are compared like product files, and the summary adds `; N optional files - M installed: X match, Y local change(s)`.

Where the libraries are looked for: a 1.1.0 copy has them in `<CLI_DIR>/lib/`. For a copy not moved yet, `identify` also looks in `<repo>/external/` and `<CLI_DIR>/vendor/`, and prints where it found them.

The closing line names the closest release: the one with the fewest local changes and missing files (an `unverified` file that is byte-identical to another release's file counts as a local change), then the largest share of matching product files, then the most unverified, then the newest. Read the block of the release you expect to run. Its counts are what matter.

**Reading the result for 1.0.0.** Every copy taken on 2026-09-30, before 1.1.0, is 1.0.0. Adopting 1.0.0 required editing these product files (1.0.0's `ADOPTING.md` step 5): `tickets.py`, `serve.py`, `app.js`, `index.html`, `style.css`, `manifest.webmanifest`, `make_icons.py`, the three icons, and both `refresh.md` files (`external/marked/` and `external/dompurify/`, whose paths change if you moved the libraries). Each one that differs shows `unverified`. Those edits are expected, but a local change hides among them just as well, so **diff every `unverified` file against the release**, and every `differs` file too:

```bash
python <SRC>/tools/release.py export <version> <SCRATCH>/ts-<version>
git diff --no-index --ignore-all-space --ignore-cr-at-eol <SCRATCH>/ts-<version>/payload/<payload path> <REPO>/<installed path>
```

In a clone of the GitHub repo the export works for 1.3.1 and later: the public repo carries release tags (`tickets-v<version>`) from 1.3.1 on, and no older release tree is published. A copy older than 1.3.1 is still identified, since every release's manifest is published, but its release's files can't be exported from a clone. Diff its local changes against the clone's current payload, `<SRC>/payload/<payload path>`, instead: what differs there is a local change or a change the newer release made, and the changelog names the latter. Then upgrade straight to the clone's release (sect. 3, "From a public clone").

For example, `<payload path>` = `src/tools/tickets/serve.py` and `<installed path>` = `tools/tickets/serve.py`; `identify` prints both. Anything in the diff beyond the edits 1.0.0's `ADOPTING.md` step 5 listed is a local change. The icons are binary: re-baked icons are expected, so check only that you meant to change them.

**Reading the result for 1.1.0 and later.** No product file needs editing any more, so every product file and the skill should match. The three icons are `adapted` from 1.1.0: each project bakes its own (the release's say `XY`), so they show `(yours: adapted per project, not compared)` and are never a local change. Under the 1.0.0 block they still show `unverified`. Any `differs` on a product file is a local change.

**Before you upgrade, send each local change you want kept to the maintainer, or it will be lost.** An upgrade replaces product files whole.

## 2. Record your version

Set this row in your skill's Settings table: `| Ticket system version | <x.y.z> |`. From 1.1.0 the row ships in the skill; an older copy adds it. The Settings rows are yours, so this is not a skill logic change. It still counts as a skill write, though, so a read-only review applies, as for any skill edit.

**Check:** `identify` still shows the skill as `settings-only` (or `exact`) for the release you record.
