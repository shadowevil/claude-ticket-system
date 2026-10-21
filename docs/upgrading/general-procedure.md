# 3. Upgrade to a newer release

*Sect. 3 of the upgrade guide, `../UPGRADING.md`: read its opening first, for `SRC`, `REPO`, `SCRATCH` and `CLI_DIR`. A bare "sect. N" here is that guide's sect. N, and its index names the file. `ADOPTING.md` is `../ADOPTING.md`, an index too.*

This is the general procedure. For a copy on 1.0.0, follow sect. 4 instead: it adds the one-time steps of the move to config. Then go on to 1.2.0 with sect. 5. To 1.3.0, follow sect. 7: it moves your tags and tickets to numbered tags. From 1.3.0 to 1.3.1, follow this procedure with the 1.3.1 per-release note (`release-notes.md`).

**From a public clone.** The public repo publishes 1.3.1 and later, with release tags from `tickets-v1.3.1` on; older release trees are not published. `identify` still names an older copy's release (every manifest is published), so sect. 1 works as usual, but diff local changes against the clone's `payload/` (sect. 1). Then go straight to the clone's release:
- **1.3.0:** this procedure, with the clone as the release (step 2), and the per-release notes after 1.3.0.
- **1.2.0, 1.2.1 or 1.2.2:** sect. 7, with the clone's release in place of 1.3.0 (its step 2 takes the clone). Copy everything in the tool folder except `icons/`, and read the 1.2.1 and 1.2.2 notes and every note after 1.3.0.
- **1.0.0 or 1.1.0:** sect. 4 and 5 install 1.1.0's and 1.2.0's own files, which only the maintainer's source holds. Ask the maintainer for them (an issue, drafted for your user's OK) before you start.

Read the release's `CHANGELOG.md` entry first. It says whether the release is major, minor or patch, and lists any steps beyond these.

**The tool folder, in every release (B43): copy everything except `icons/`.** Your three icons are baked per project (`adapted`), and the release's say `XY`, so never copy `icons/`. Each per-release note (`release-notes.md`) names the files that actually changed, and copying just those is the other stated option. If you copied the folder whole by mistake, re-bake (step 6): `make_icons.py` redraws your `icon_text` and, from 1.2.0, your `icon_color`, both from `config.json`.

1. **File the upgrade.** Per the skill ("File on a peer project's board", step 6), file the release as a request on your board, and set it `in_progress`: on the maintainer's machine, the maintainer's announcement; elsewhere, the release you take from GitHub. The provenance line names `Ticket Master` either way, such as `Requested by Ticket Master (GitHub release <new>) on <YYYY-MM-DD>.`, because that is the name the optional hooks look for (the default of `config.json`'s `source_of_truth_session`). With the hooks installed, T2 then logs the copy as tied to it.
   **Check:** `python <CLI_DIR>/tickets.py list --active` shows it `in_progress`.
2. **Get the release.** With a clone, bring it to the new release (`git -C <SRC> pull`), and call `<SRC>/payload/` `PAYLOAD`. On the maintainer's machine (or in a clone, for 1.3.1 and later, if you prefer an export), export it:
   ```bash
   python <SRC>/tools/release.py export <new> <SCRATCH>/ts-<new>
   ```
   and call the export's `payload/` folder `PAYLOAD`. The export reads the release's tag, `tickets-v<new>`, so it works only once that tag exists.
   **Check:** `PAYLOAD/../VERSION` reads `<new>`.
3. **Back up** the files you will replace, the way your project requires.
   **Check:** your backup lists the tool folder, the schema, the rules doc and the skill.
4. **Stop the viewer:** `python <CLI_DIR>/serve.py --stop`.
   **Check:** it prints `stopped the ticket viewer (pid N)`, or that nothing was recorded.
5. **Replace the tool folder, except `icons/`:** copy every file and folder of `PAYLOAD/src/tools/tickets/` except `icons/` (`lib/` included) over `REPO/<CLI_DIR>/`, or just the files the release's per-release note names. Delete any file the release removed; its changelog lists them. Nothing is edited after the copy: `config.json` carries your values.
   **Check:** `REPO/<CLI_DIR>/lib/marked/marked.umd.min.js` exists, and `icons/` is unchanged (`git status` shows nothing under it).
6. **Icons: leave them, unless the release's note says to re-bake.** Step 5 kept yours. Re-bake with `python <CLI_DIR>/make_icons.py` only when the note says the drawing or the colour logic changed (1.1.0, 1.2.0), when you changed `icon_text` or `icon_color`, or when you copied `icons/` by mistake and have the release's `XY` icons. `make_icons.py` takes both values from `config.json`: your `icon_text` (by default the id prefix without its hyphen) and, from 1.2.0, your `icon_color` (by default `#007acc`). Icons that were made any other way are not restored: take them from your backup.
   **Check:** nothing changed under `icons/`, or three `wrote icons/...` lines with your icon text (and, from 1.2.0, your colour).
7. **Merge the schema and the rules doc:**
   - Your `ticket.schema.json` keeps your enums. Take any other change the changelog lists.
   - Your `tickets.md` keeps your project text. Take any rule change the changelog lists.

   **Check:** `python <CLI_DIR>/tickets.py validate` passes on your existing tickets.
8. **The skill:**
   - Take `PAYLOAD/dot-claude/skills/tickets/SKILL.md`.
   - Put your Settings rows back in, and set the version row to `<new>`.
   - **Replace a scratch row that points at a temp folder** rather than keep it (B54): if your "Scratch for body files" row names the harness's scratchpad or a system temp folder (`AppData\Local\Temp`, `%TEMP%`, `/tmp`), set it to the release's wording, `.claude/scratch/<role>/<task>/` inside the project, git-ignored. Change your rules doc's `<SCRATCH>` wording and any CLI example that names the temp folder to match, and make sure `.gitignore` has `.claude/scratch/` (`ADOPTING.md` step 9).
   - Have a separate read-only agent review it.
   - Install it only after a pass.

   **Check:** the review passed.
9. **The hooks,** if you installed them: sect. 6.
10. **Verify:**
    - `python <CLI_DIR>/tickets.py validate` passes;
    - start the viewer again (`python -u <CLI_DIR>/serve.py --foreground` as a background task), and `/api/health` answers with your marker;
    - the page shows your tickets under the same title as before;
    - run `identify` again: the new release's block shows every product file matching, the icons `adapted` (`yours: adapted per project, not compared`), and the skill `settings-only`.
11. **Commit** in your repo, the way your project does.
12. **Tell the maintainer** the version you now run, and close the upgrade ticket on that evidence. If a step failed, say which, and what you saw.
