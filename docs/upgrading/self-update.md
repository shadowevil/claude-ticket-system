# 11. The viewer's one-click update (1.5.0 and later)

*Sect. 11 of the upgrade guide, `../UPGRADING.md`: read its opening first, for `SRC`, `REPO`, `SCRATCH` and `CLI_DIR`. A copy before 1.5.0 updates by hand once more, to 1.5.0 (sect. 10).*

From 1.5.0, on the maintainer's machine, a release is installed from the viewer: a badge, a confirm dialog, one click. Nothing goes over the network: the source is the maintainer's `ticket-system/` folder on this PC, read through its release tags (user, 2026-11-01: "It doesn't have to be overly complex - it runs locally only").

## Turning it on, and off

- **On:** `update_source` in `.claude/tickets/config.json`, the absolute path of the maintainer's `ticket-system/` folder (`ADOPTING.md` step 4). The viewer needs `git` on PATH: it reads the release tags.
- **Off (the opt-out):** leave `update_source` out, or set it to `""`. The viewer then shows no badge, and `POST /api/update/apply` answers 403 whatever it carries. A value that is not a string stops `serve.py` with an error naming the key.
- `GET /api/update` tells you what the viewer sees: `"state"` is `off`, `current`, `available` (with `"latest"` and the release notes), `unknown` (no `<CLI_DIR>/VERSION`: a copy before 1.5.0) or `unavailable` (with a `"reason"`: the folder, its `releases/` or git cannot be read). The viewer logs the same once at start (`build/tickets/serve.log`).

## What one click does

The latest release is the highest `x.y.z` that has both a manifest, `<update_source>/releases/<x.y.z>.json`, and its tag, `tickets-v<x.y.z>`. A manifest without its tag is a release in progress and is never offered. The installed version is `<CLI_DIR>/VERSION`.

1. **The request.** Only a browser on this PC can ask: the page carries a token (made when the viewer starts, kept in memory), and the request must come from `127.0.0.1` with `Host` and `Origin` naming `127.0.0.1:<PORT>`, `localhost:<PORT>` or `[::1]:<PORT>`, the token in `X-Tickets-Token`, and a JSON body naming the version on offer. Anything else is refused (403); no other site's page can send it. The token, `/api/update` and `/api/update/status` are given only to such a request. First `tickets.py validate` runs: a store that is already invalid is refused before anything moves. `build/tickets/update.lock` lets one update run at a time; a second click is refused (409).
2. **Export and verify.** `python <update_source>/tools/release.py export` writes the new release, and the release you run now (the merge base), into `build/tickets/update/<new>/`. Every exported file is checked against the export's own manifest (its `raw` hash), and every manifest path must sit under `src/tools/tickets/` or `dot-claude/` with no `..`. A mismatch stops here.
3. **Merge the schema.** The release's `ticket.schema.json` is taken with your values copied in at each of its `x-project-owned` pointers (the id patterns and the `status`, `severity`, `owner_area` and `author` enums). If your schema differs from the base release's anywhere else, the update stops here and says where; nothing is guessed. (Reworded titles and descriptions are kept.)
4. **Back up** every file it will replace or delete: the tool folder's product files (never `icons/`, which are yours) and the schema, into `build/tickets/update/<new>/backup/`.
5. **Hand off.** A helper process from the new release (`updater_helper.py`) stops the viewer, installs each changed file (written as `<name>.new`, then moved over the old one; a file held by an editor or a scanner is retried for 10 s), deletes the files the release dropped and `<CLI_DIR>/__pycache__`, runs `tickets.py validate`, and starts the viewer again on the same port, bind and data folder. The page waits on `/api/health`, then reloads.
6. **Success:** the result lists the changed files and the `ACTION` lines. The helper stages what you install yourself (below) and rewrites `.claude/tickets/README.md`.
7. **Failure** in step 5 (a held file, a failing `validate`, a viewer that does not come back): the backup goes back, the old viewer is started again, and the result says which step failed with the end of its output. A stop in steps 2-4 changes nothing outside `build/tickets/`.

Only the viewer that took the click is stopped and restarted: a second viewer on the same repository (another port, a `--data-dir` test) keeps running the old code until you restart it yourself.

If the helper itself dies part-way (the PC sleeps, the process is killed), the next `serve.py` start finds the lock with no final state, puts the backup back first and prints a `note:` line.

Progress and the result are in `build/tickets/update/status.json`, and the helper's output in `build/tickets/update/<new>/helper.log`.

## What stays yours: staging, the README, the commit

- **Nothing is committed** and nothing runs `git` in your repository. Review the changed files the result lists and commit them, with `.claude/tickets/README.md`.
- **Staged, never installed** (the global rule that every skill and hook write is reviewed), in `build/tickets/staged/<new>/`, and only when the release changed them:
  - `SKILL.md`: the release's skill with your Settings rows carried over and the version row set. Have it reviewed by a separate read-only agent, then copy it to `.claude/skills/tickets/SKILL.md`. A Settings row the release added keeps its placeholder: fill it in.
  - `hooks/tickets/`: the release's hooks, if you have `.claude/hooks/tickets/`. Install them as sect. 6 says (staged self-test, review, install).
  - `tickets.md`: your rules doc merged with the release's by `release.py merge-doc --base <the release you ran>` (sect. 9 step 5). Exit 2 there shows as an `ACTION` line: resolve the conflict blocks, review the diff, then copy it over.
- **The agents README,** `.claude/tickets/README.md`: newest first, per release, its lines for agents (from the release's `Agents:` block), then the `ACTION` lines for this copy (the staged items, the files to commit). After an update, the next `tickets.py` command prints `tickets: store updated to <new> - see .claude/tickets/README.md` once, to stderr. Agents read it then, and act on an `ACTION` line only if their role allows it; otherwise they tell the user.

## Rolling back by hand

The last update's work area, with its backup, stays in `build/tickets/update/<new>/` until the next update starts. To go back to the release you ran before:

1. Stop the viewer: `python <CLI_DIR>/serve.py --stop`.
2. `build/tickets/update/<new>/plan.json` lists each file under `backed_up` (`target`, `backup`) and each file the update added under `added`. Copy every `backup` over its `target`, and delete every `added` file.
3. Delete `<CLI_DIR>/__pycache__/`.
4. **Check:** `<CLI_DIR>/VERSION` reads the old version, and `python <CLI_DIR>/tickets.py validate` prints `OK: ...`.
5. Start the viewer again. With git, `git checkout -- <CLI_DIR> .claude/tickets/ticket.schema.json` does the same before you commit the update.

The staged skill, hooks and rules doc were never installed, so they need nothing.
