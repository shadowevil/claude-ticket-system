# Optional: ticket hooks

*Part of the adoption guide, `../ADOPTING.md`: read its opening first, for `SRC`, `REPO` and `SCRATCH`. Steps 1-11 of the adoption itself are in `steps.md`, and `PAYLOAD` is the release's `payload/` folder from its step 2 (in your clone, or in the export). `UPGRADING.md` is `../UPGRADING.md`, an index too.*

Two Claude Code hooks ship with the ticket system: T1 notes when work resumes after a quiet spell of 30 minutes or more and the viewer isn't running, and T2 notes a write into the ticket system's source that no request from the maintainer covers (a ticket whose provenance line names `Ticket Master`). They are **optional and log-only**: they write rows to `build/hooks/tickets/hits.jsonl` and never block, deny or print anything. Their rules are in `PAYLOAD/dot-claude/hooks/tickets/RULES.md`. Skip this section if you don't want them.

1. **Stage and review first.** Installing them is a hook write, so the global rule applies (2026-09-28): stage the files and the settings change, have a separate read-only agent review them, and install only after a pass. They are project hooks. Wiring them into `~/.claude/settings.json` (a global install) needs the user's approval.
   - As part of the review, run the self-test on the staged copy, before anything is installed. `STAGED` is the staged `hooks/tickets` folder, wherever it sits: `PAYLOAD/dot-claude/hooks/tickets` if you review the export in place, or any folder you copied it to.

     ```bash
     python -I -S -B STAGED/prompt_guard.py --self-test --scratch <REPO>/.claude/scratch/<role>/<task>/
     ```

     It writes nothing inside `STAGED`, or inside the export's `payload/` when you run it there. Always pass `--scratch`: it names an existing folder of yours, outside `STAGED` and outside the export's `payload/`. It must not be the project root or `.claude/` itself (from 1.3.0): a killed run's folder there would be ignored by nothing. The self-test's scratch projects go there and are removed when it ends. Without it they go to the system temp folder, which your scratch rules forbid. `-B` keeps `__pycache__` out, so the reviewer still reviews exactly what was staged. Your `SCRATCH` folder itself works: the export (or a clone kept in your scratch) sits in a folder below it (`<SCRATCH>/ticket-system-1.4.0/`), and only its own `payload/` is off limits.
   - If it prints `self-test: refused: ...` and exits 2, nothing was written, not even a probe file, and the line gives the reason. Most likely the `--scratch` folder is missing, lies inside the staged folder or the export's `payload/`, or is the project root or `.claude/` itself. Create it or choose another, and run it again. (Without `--scratch`, it is that the temp folder, the first existing one of `TMPDIR`, `TEMP`, `TMP`, lies inside the staged folder, or inside the export's `payload/`, or no temp folder is usable.)

   **Check:** the staged self-test's last line ends in `0 failure(s)`, and the review passed.
2. **Copy the folder.** Copy `PAYLOAD/dot-claude/hooks/tickets/` whole to `REPO/.claude/hooks/tickets/`. A `.claude/hooks/` your project already has stays as it is: the ticket hooks import only from their own folder.
   **Check:** `REPO/.claude/hooks/tickets/prompt_guard.py`, `write_guard.py`, `shell_guard.py` and `hooklib/policy.py` exist.
3. **Merge the wiring by hand.** `settings.snippet.json` holds one `UserPromptSubmit` entry and two `PreToolUse` entries, one for `Write|Edit|MultiEdit|NotebookEdit` and one for `Bash|PowerShell`. Add them to the `hooks` arrays of `REPO/.claude/settings.json`, beside any hooks you already have. Create the file if there is none.
   - Keep every `command` string exactly as it is, `|| exit 0` included. The one exception: on a machine where Python is `python3`, replace `python` in the three commands (`../ADOPTING.md`, "Requirements"). That tail keeps a missing script or a missing `python` from blocking your prompts and tool calls.
   - Never replace an existing `settings.json` with the snippet. Claude Code doesn't read the snippet itself.

   **Check:** `python -c "import json; json.load(open('.claude/settings.json', encoding='utf-8'))"` exits 0, and the file holds the three `.claude/hooks/tickets/` commands.
4. **Ignore the runtime files.** `.gitignore` covers `build/hooks/` (`build/` does) and `__pycache__/`.
   **Check:** as in step 9.
5. **Config.** `config.json` has `viewer_port`, which T1 needs. The hooks need `tool_dir` only if the tool is in neither `tools/tickets` nor `src/tools/tickets`, and then step 4 has set it already, for `identify` too. The hooks also read an optional `source_of_truth_session`, which defaults to `Ticket Master`.
   **Check:** step 4's check still passes.
6. **Self-test again, installed.** Run it from `REPO`, on the installed path:

   ```bash
   python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test --scratch <REPO>/.claude/scratch/<role>/<task>/
   ```

   `--scratch` names your scratch folder, an existing folder: the self-test's scratch projects go there, and the system temp folder isn't used. Always pass it. The self-test itself writes nothing else in `REPO`. The live hooks, wired in step 3, write `build/hooks/tickets/` and `__pycache__/`, which step 4 ignores. It must not be the project root or `.claude/` itself (from 1.3.0): a killed run's folder there would be ignored by nothing. A `self-test: refused: ...` line with exit 2 means the `--scratch` folder is missing, lies inside a protected folder (below), or is the project root or `.claude/` itself. Nothing was written, not even a probe file. Without `--scratch` the self-test uses the temp folder (the first existing one of `TMPDIR`, `TEMP`, `TMP`) and refuses when that lies inside `REPO`, or none is usable; point them elsewhere, or pass `--scratch`, and run it again.
   - **If your project's scratch is elsewhere inside the repo** (for example a gitignored `working/` folder), pass that folder, or a folder in it, instead:

     ```bash
     python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test --scratch working/selftest
     ```

     The folder must exist, be gitignored, and lie outside `.claude/hooks/tickets/` and `.claude/tickets/`, and it is not the project root or `.claude/` itself. Inside those, or when it is missing or a file, or when it is the project root or `.claude/` itself, the self-test refuses in the same way, writing nothing. Its scratch projects are then `tickets-selftest-*` folders directly in that folder, removed when the run ends, and the system temp folder isn't used at all. Any other argument is refused too, so a mistyped option (`--Scratch`, `--scratch-dir`) never quietly runs in the system temp folder. `RULES.md`, "`--scratch <dir>`", has the exact rules.
   - **The alternative is to run it from an export.** Check that `REPO/.claude/hooks/tickets/` matches the export's `PAYLOAD/dot-claude/hooks/tickets/` file for file, then run the self-test on the export, outside `REPO`, as in step 1. It tests the same files and writes nothing in `REPO`.
   **Check:** the last line ends in `0 failure(s)`.
7. **Leave them log-only.** Rows go to `build/hooks/tickets/hits.jsonl`. Enforcing a rule (its id in `USER_ENFORCED` and `ENFORCE` in `hooklib/policy.py`) is the user's call.
   **Check:** `REPO/.claude/hooks/tickets/hooklib/policy.py` still reads `ENFORCE = frozenset()`, as shipped.
