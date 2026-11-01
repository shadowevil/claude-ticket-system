# Migrating from another tracker

*Assessed 2026-10-21 (B47, under the documentation standard): kept whole. One procedure, read whole by a project that migrates; its steps share the record format above them.*

*Part of the adoption guide, `../ADOPTING.md`: read its opening first, for `SRC`, `REPO` and `SCRATCH`. Steps 1-11 of the adoption itself are in `steps.md`. `UPGRADING.md` is `../UPGRADING.md`, an index too.*

Skip this section if the project has no earlier tracker (a queue file, a TODO list, another tool's export). If it has one, move its items in with `import` once step 10 passes. `import` creates one ticket per record of a JSON file, in the file's order, and keeps each item's own `created` and `updated` times. It validates the store and every record before it writes anything. When writing fails part-way, or you press Ctrl+C, it removes what it wrote, so the store gets all of the tickets or none. A killed process can't clean up after itself; step 5 says what it leaves and how to recover.

```bash
python <CLI_DIR>/tickets.py import <file.json> --dry-run
python <CLI_DIR>/tickets.py import <file.json>
```

**The file** is UTF-8 (a BOM is accepted) and holds one JSON array of records. A record is an object with these keys and no others:

| Key | Required | Value | When left out |
|---|---|---|---|
| `summary` | yes | One line, 1-200 characters | - |
| `severity` | yes | `critical`, `high`, `medium` or `low` | - |
| `owner` | yes | One of your `AREAS`. `owner_area` is accepted instead | - |
| `author` | yes | One of your `AUTHORS` | - |
| `status` | no | `open`, `in_progress`, `in_review`, `user_review`, `verified`, `blocked`, `done` or `wont_do` | `open` |
| `target` | no | One line, 1-40 characters. `target_patch` is accepted instead | `next` |
| `tags` | no | An array of tags from `tags.json`, by name (or by id). They are written as ids, and the tag groups apply | `[]` |
| `body` | no | A string of markdown. CRLF line ends become LF | `""` |
| `links` | no | An object with any of `tickets`, `files` and `commits`, each an array of strings, as `--link-ticket`, `--link-file` and `--link-commit` take them | no links |
| `created` | no | UTC, written exactly `YYYY-MM-DDTHH:MM:SSZ` | the time the import runs |
| `updated` | no | The same form, and not before `created` | the record's `created` |
| `id` | no | The id this record must get | - |

- **Ids are the store's.** They are assigned in the file's order, exactly as `new` would: the highest existing number plus one, then one more per record. In a store that holds only step 10's smoke-test ticket, the first record gets the number after it. A record's `id` is a check, not a request: when it differs from the id assigned, the import stops.
- **A ticket link** names a ticket already in the store or any record of the same file, later ones included, by the id it will get. A bare number works (`"12"`). A record can't link to itself.
- **Dates.** Neither `created` nor `updated` may be later than the moment the import starts, on this PC's clock. Convert local times to UTC first. A record with `updated` and no `created` fails, because `created` would then be now.
- **Refused:** a key the table doesn't list, both `owner` and `owner_area` (or both `target` and `target_patch`) in one record, a key written twice in one object, and a line break in `summary` or `target` (LF, CR, or any other character that ends a line).
- **The store comes first.** `import` checks the existing store as `validate` does, and stops with `ERROR the store has N problem(s); run validate and fix them first` when it has any. `--dry-run` does the same.

```json
[
  {
    "summary": "Crash when a save file has no header",
    "severity": "high",
    "owner": "core",
    "author": "pm",
    "status": "done",
    "tags": ["bug"],
    "created": "2025-03-01T10:00:00Z",
    "updated": "2025-03-05T12:30:00Z",
    "links": {"tickets": ["3"], "commits": ["1a2b3c4"]},
    "body": "Migrated from the old queue, item Q-101.\n\nThe finding, as the old tracker had it.\n"
  },
  {
    "summary": "Document the save file format",
    "severity": "low",
    "owner": "docs",
    "author": "pm",
    "created": "2025-03-02T09:00:00Z"
  }
]
```

In this example the store already holds the smoke-test ticket, so the two records become numbers 2 and 3, and `"3"` links the first to the second.

**Never put a secret in a ticket.** The viewer serves every ticket to the LAN, unauthenticated. Leave passwords, tokens, keys and private data out of the file, and check the old items for them before you convert.

1. **Map the old fields.** Write down, for each field of the old tracker, the ticket field it becomes. Every item needs a `summary`, a `severity`, an `owner` and an `author`. The item's old id goes in the body, as the example shows, so the old tracker's references still lead somewhere. Anything else the schema has no field for goes in the body too: an assignee, a priority number, comments, with their dates.
   **Check:** every old field is mapped to a ticket field, to the body, or marked as dropped on purpose.
2. **Adapt the enums and tags.** Map each old state to one of the six statuses and each old priority to one of the four severities. If the old items need an area, an author or a tag you don't have, add it to `ticket.schema.json`'s two team enums (step 5), or to the tag store with `author.py tags add` (step 6), now, before the import. With `tag_groups` set, every record must satisfy each group.
   **Check:** `python <CLI_DIR>/tickets.py validate` still prints `OK: ...`, and `python <CLI_DIR>/tickets.py new --help` lists the areas and authors the mapping uses.
3. **Rehearse in a scratch copy.** Copy `REPO/<CLI_DIR>/` and `REPO/.claude/tickets/` to `<SCRATCH>/rehearsal/`, at the same relative paths. The tool works on the store of the nearest folder above it that holds `.claude/tickets/config.json`, so the copy is a store of its own and your real one stays untouched. Write the script that converts the old tracker's export to the import file; keep the script, and keep the file out of `.claude/tickets/`. Then run the two commands above with `<SCRATCH>/rehearsal/<CLI_DIR>/tickets.py`, and read a few of the tickets with `show`. Repeat from a fresh copy until it is clean.
   **Check:** in the scratch copy, the import prints `imported N tickets <first>..<last>`, `validate` prints `OK: ...`, and `REPO/.claude/tickets/` is unchanged.
4. **Dry run on the real store.** Run `python <CLI_DIR>/tickets.py import <file.json> --dry-run` from `REPO`. A problem prints one line, `FAIL record <index> (<id>): <key>: <what is wrong>`, where the index counts from 0 and the id is the one the record would get. The first 100 lines are shown. Nothing is written, with or without `--dry-run`, while any record fails.
   **Check:** it prints `OK: N records valid; would create <first>..<last>`, N is the old tracker's item count, and the range is the one the rehearsal gave.
5. **Import.** Run it without `--dry-run`. No other session files a ticket while it runs. If writing fails part-way (a full disk, an id another writer took meanwhile), the import deletes what it wrote and prints `ERROR import failed: ...; rolled back, no ticket of the batch was kept`. An existing ticket file is never replaced.

   **If the import is killed** (`taskkill /F`, a closed console, a crash of the PC), it can't remove anything. It leaves, in `.claude/tickets/`:
   - `journal.import-<pid>.tmp`, written before anything else: the batch's ids, the source file's name, and the sha256 of every ticket file the import writes;
   - `<id>.import-<pid>.tmp` for each ticket not yet in place;
   - `<id>.json` for each ticket already in place. Until you recover, `validate` may report links to tickets that never arrived.

   The next `import`, with or without `--dry-run`, refuses to start while its `journal.import-<pid>.tmp` or any `<id>.import-<pid>.tmp` file is there. Its one `ERROR an earlier import was interrupted, ...` line gives the batch's id range, the source file and how many of its tickets are in the store. `new` keeps working and takes the id after the batch's last, but **hold off filing until the re-import is done**: a ticket filed now takes an id the re-import needs, and a records file that carries ids then fails (`FAIL record 0 ... id: expected ...`). To recover:

   ```bash
   python <CLI_DIR>/tickets.py import --abort-interrupted
   ```

   It removes the batch's ticket files that still hold exactly the bytes the import wrote (by the journal's sha256), its temporary files, then the journal, and nothing else. It prints `removed K ticket(s) <first>..<last> and M temporary file(s) of the interrupted import ...`. The store is then as it was before the import, and you run the import again.
   - It refuses while that import is still running, removing nothing: `ERROR an import is running now (pid N; ...); nothing was removed`. Wait for it to finish, and run it again only if its files are still there. It checks the pid in the files' names (on Windows also when that process started, so a pid reused by a later process doesn't count). It touches only the names the tool writes; a file of yours such as `notes.import-old.tmp` stays.
   - If the `ERROR` names a pid that is not a python process running `tickets.py` (it says `not python` when it can tell), another program has that number: delete the files it names by hand, by the patterns given (`journal.import-<pid>.tmp` and `<PREFIX>[0-9]*.import-<pid>.tmp`), then run `validate`. The patterns are for bash or PowerShell (`Remove-Item -Path '<folder>\XY-[0-9]*.import-<pid>.tmp'`); cmd's `del` does not understand `[0-9]`. A pid that gets `could not be checked (access refused)` has the same way out, once you are sure no import is running.
   - A journal that doesn't read as one the import wrote (cut off, or edited: ids not contiguous, not matching its `first`, `last`, `count` or pid, without the store's prefix, or absurdly long) removes no ticket: `removed a journal that does not read as one the import wrote (...) and M temporary file(s); no ticket was removed`.
   - A ticket of the batch that was changed since, with `set`, is kept and named in a `kept N ticket(s) that are not as the import wrote them ...` line. A ticket file last written before the journal is kept the same way. Its links may point at tickets that are gone, and `import` won't start while `validate` reports that. Move that file out of `.claude/tickets/` and keep it; the fresh import brings the item back.
   - If every ticket of the batch is in place and no temporary file is left, the import had finished but for removing its journal. The tickets are kept, and only the journal goes.
   - It also clears the leftovers of other killed writers, each once its process is gone: a killed `new` or `set` leaves `<id>.new-<pid>.tmp` or `<id>.set-<pid>.tmp`. A tag store write (`author.py tags ...`) killed part-way leaves `tags.store-<pid>.tmp` beside `tags.json`, which is unchanged. `tickets.py import --abort-interrupted` removes it once that process is gone, and keeps and names one whose process still runs. The killed write also leaves `tags.json.lock`: delete it by hand once no `tickets.py` or `author.py` is running, as the lock refusal says. With nothing to clean, it prints `ERROR no interrupted import, no killed new or set and no killed tag store write: ...`.

   **Check:** it prints `imported N tickets <first>..<last>`, and `.claude/tickets/` holds no `.tmp` file.
6. **Verify.** Run `python <CLI_DIR>/tickets.py validate`, then count by status and compare each count with the old tracker's: `python <CLI_DIR>/tickets.py list --status done` ends in `<count> of <total> tickets`, and so on for each status you mapped to. Open the first and the last imported ticket in the viewer.
   **Check:** `validate` prints `OK: ...`, each status count matches the old tracker's after your mapping, and `show` gives the old dates. A wrong field on an imported ticket is fixed with `set`; a ticket is never deleted, and that is what the rehearsal is for.
7. **Retire the old tracker.** Keep it read-only until step 6 passes: nobody adds to it or edits it from the moment you export. Then mark it as retired, with a line at its top saying where the tickets are now, and keep it. Don't delete it: the bodies name its ids.
   **Check:** the old tracker says it is retired and where its items went, and your `CLAUDE.md` names only the ticket store as the place to file.
