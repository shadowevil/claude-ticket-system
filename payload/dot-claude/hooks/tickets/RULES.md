# ticket-system hooks (optional, log-only)

Two Claude Code hooks that ship with the ticket system from 1.1.0, maintained by the `Ticket Master` session
like the CLI, the viewer and the tickets skill. They are **optional**: a project installs them itself, into its
own `.claude/hooks/tickets/`, and wires them into its own `.claude/settings.json`. They are **log-only**: they
record what they would do in `build/hooks/tickets/hits.jsonl` and never block, deny or print anything unless
the user of that project chooses to enforce a rule (`ENFORCE` in `hooklib/policy.py`, empty as shipped).

| id | rule | module | mode |
| --- | --- | --- | --- |
| T1 | the ticket viewer runs when work resumes after a quiet spell | `rules/prompt/t1_viewer_after_quiet_spell.py` | log-only |
| T2 | the board is the project's own; the ticket system's source is not changed locally | `rules/write/t2_ticket_system_fork.py` | log-only |

Two standing rules apply to these files wherever they are installed:
- **Every hook write goes through a review phase** (the user's global rule, 2026-09-28). Installing, upgrading,
  editing or removing any file here, or the hook wiring in a `settings.json`, is staged first, reviewed by a
  separate read-only agent, and installed only after the review passes. Hotfixes included.
- **A global install needs the user's approval.** These are project hooks. Wiring them into
  `~/.claude/settings.json` is the user's call, never an agent's.

## install and upgrade

The step lists are in the ticket system's `docs/ADOPTING.md` (a new install) and `docs/UPGRADING.md` (an
existing copy). In short:

1. For the review, run the self-test on the staged copy, before anything is installed. It must end in
   `0 failure(s)`, and it writes nothing inside the staged folder (see "The self-test writes nothing in a
   staged copy" below):

       python -I -S -B <staged copy>/prompt_guard.py --self-test --scratch <project>/.claude/scratch/<role>/<task>/

   `<staged copy>` is the staged `hooks/tickets` folder, wherever it sits: for example
   `<export>/payload/dot-claude/hooks/tickets`, or any folder you copied it to. Pass `--scratch` with your
   project's scratch folder, an existing folder (see "`--scratch <dir>`" below): the self-test's throwaway
   folders go there. Without `--scratch` they go to the system temp folder, which a project that keeps scratch
   inside `.claude/scratch/` must not write to.
2. Copy `payload/dot-claude/hooks/tickets/` to `<repo>/.claude/hooks/tickets/`, the whole folder. On an
   upgrade, replace the folder but keep your own `hooklib/policy.py` if you have enforced a rule.
3. Merge `settings.snippet.json` into `<repo>/.claude/settings.json` by hand: add its three entries to the
   `hooks` object next to any hooks you already have. Never replace your `settings.json` with it.
   `settings.snippet.json` itself is not read by Claude Code.
4. Gitignore `build/hooks/` (the runtime files) and `__pycache__/` (see "bytecode" below).
5. Run the self-test again, from `<repo>` on the installed path. It must end in `0 failure(s)`:

       python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test --scratch <project>/.claude/scratch/<role>/<task>/

   `--scratch` names your scratch folder (it must exist, outside `.claude/hooks/tickets/` and
   `.claude/tickets/`, and not the project root or `.claude/` itself; gitignore it), so the self-test never writes to the system temp folder. A project whose
   scratch is elsewhere inside the repo passes that folder instead, such as `working/selftest`.

   Or skip the installed run and rely on the staged one of step 1, run from an export outside the repo: it
   tests the same files.

6. Check the config keys below. Nothing else is edited: the hooks read everything from the project.

A project that already has its own `.claude/hooks/` (and its own `hooklib/`) keeps it. These hooks live in
their own folder and import only from it (see "namespacing").

## config

Read from `.claude/tickets/config.json` (UTF-8, a BOM is accepted), never written. Unknown keys are ignored by
the CLI, so the hook-only keys below sit there safely.

| Key | Used by | When absent |
| --- | --- | --- |
| `viewer_port` | T1 | the 1.0.0 fallback: `default_port = N` in the viewer script. Neither -> T1 is silent |
| `viewer_service` | T1 | `service_marker = "..."` in a 1.0.0 viewer script, else derived from `store_name` exactly as `tickets.py` does it: lowercase, runs of anything but `[a-z0-9]` as `-`, trimmed, plus `-tickets` (`tickets` when nothing is left) |
| `store_name` | T1 | no derived marker |
| `tool_dir` | T1, T2 | the folder of `viewer_script`, else the first of `tools/tickets` and `src/tools/tickets` that holds `tickets.py` |
| `id_prefix` | T2 | any `<LETTERS>-NNNN.json` file in `.claude/tickets` counts as a ticket |
| `source_of_truth_session` (hook-only) | T2 | `Ticket Master` |
| `viewer_script` (hook-only) | T1, T2 | `serve.py` in the tool's folder |
| `viewer_health_path` (hook-only) | T1 | `/api/health` |
| `viewer_pid_file` (hook-only) | T1 | `build/tickets/serve.pid` |

A `tool_dir` (or a `viewer_script` folder) that lies outside the project, is the project root, or overlaps the
board (`.claude/tickets`, or a folder holding it such as `.claude`) is **ignored**: the next source is used, and
T2 logs one `hook-config` row naming the key and the reason (never the value; capped at 5 repeats). Treating
the board as the tool's source would flag every ticket edit.

## the framework

Hooks are separate files grouped by action (the user's standard, 2026-09-28): thin entry points, a shared
library by concern, and one module per rule under `rules/<action>/`, each module carrying its own check,
message and self-test cases. Stdlib-only Python, run as `python -I -S`.

    <repo>/.claude/settings.json   UserPromptSubmit -> prompt_guard.py; PreToolUse Write|Edit|MultiEdit|NotebookEdit
                                   -> write_guard.py; PreToolUse Bash|PowerShell -> shell_guard.py (each timeout 5 s,
                                   each `|| exit 0`; merged from settings.snippet.json)
    <repo>/.claude/hooks/tickets/
      prompt_guard.py          UserPromptSubmit                             -> action prompt
      write_guard.py           PreToolUse Write|Edit|MultiEdit|NotebookEdit -> action write
      shell_guard.py           PreToolUse Bash|PowerShell                   -> action write
                               (each entry point's rule_modules() is its one rule list)
      replay.py                offline: the same rule modules over recorded transcripts
      settings.snippet.json    the wiring, to merge by hand
      RULES.md                 this file
      hooklib/                 paths.py         project root (CLAUDE_PROJECT_DIR, else a cwd holding
                                                .claude/hooks/tickets, else this file's project), build/hooks/tickets/
                               jsonfile.py      JSON reads that never raise (bad, BOM, deeply nested)
                               project.py       config.json, the tool's folder, the default service marker
                               output.py        hit log, breadcrumbs, secret masking, the printed output
                               policy.py        MODE, USER_ENFORCED, ENFORCE (both empty as shipped)
                               prompt_clock.py  per-project prompt clock, prompt classification
                               viewer.py        the viewer's config, health probe
                               shell.py         static write/delete targets of a Bash/PowerShell command
                               ticket_store.py  read-only view of the ticket store (active tickets by requester)
                               runner.py        the UserPromptSubmit flow and the PreToolUse flow
                               fixtures.py      self-test fixtures (Checker, scratch root and its checks, stub projects,
                                                loopback servers)
                               selftest.py      the `--self-test` collector
      rules/prompt/            t1_viewer_after_quiet_spell.py (T1)
      rules/write/             t2_ticket_system_fork.py (T2)

- **Namespacing.** Everything resolves inside `.claude/hooks/tickets/`. Each entry point puts its own folder
  first on `sys.path` (under `python -I -S` the script's folder and the working directory are not on it at
  all), so `hooklib` and `rules` are always this folder's, even beside a project's own `.claude/hooks/hooklib/`.
  The self-test asserts it. Runtime files go to `build/hooks/tickets/`, never to a project's `build/hooks/`.
- **Action groups.** Tool-call rules go under the action the call performs (`write/`, `delete/`, `read/`,
  `execute/`, `dispatch/`), created with their first rule. T2 judges where a write lands, so it lives in
  `rules/write/`; both the file tools and a shell command's redirects, copies, moves, in-place edits and
  deletes are writes (a delete is a write to the filesystem too). T1 fires on no tool call at all: it fires
  when a prompt arrives, the moment work starts or resumes, so its group is `rules/prompt/`. SessionStart was
  rejected: it knows nothing about the gap and runs before any work is asked for, and a session that resumes
  after a quiet spell shows itself only through its next prompt.
- **One rule list.** Each entry point's `rule_modules()` maps each action to its rule modules. The runner and
  the self-test collector (`selftest.ENTRY_POINTS`) both read them, so a new rule is one module plus one line
  in its entry point. It is a function rather than a module constant, so that a broken rule import stays
  inside `main()`'s fail-open.
- **Fail open, never block.** Every entry point swallows every error and exits 0. A rule module that raises
  is skipped and leaves one breadcrumb row (module, phase, exception type, never the message; capped at 5
  repeats). Only an id in `ENFORCE` prints anything: for T1 an `additionalContext` reminder, for T2 a
  PreToolUse deny. No prompt rule ever returns `decision: block`.
- **The command fails open too.** If Python cannot open the script (the file is missing or the path is
  wrong), it exits 2, and exit 2 blocks: on UserPromptSubmit it erases the prompt, on PreToolUse it blocks the
  tool call. The wiring is therefore
  `python -I -S "$CLAUDE_PROJECT_DIR/.claude/hooks/tickets/prompt_guard.py" || exit 0`, which also covers a
  missing `python` (127). Claude Code runs hook commands through Git Bash on Windows, and the string is bash
  syntax (not valid in PowerShell 5.1).
- **Input encoding.** The event is read from stdin as UTF-8 bytes (`sys.stdin.buffer`), never through the
  cp1252 console text layer. A deeply nested or malformed event is silent.
- **Secrets stay out of the log.** A row's `sample` (the prompt for T1, the command or path for T2) is masked
  before it is cut: values after secret-like names (`password`, `token`, `secret`, `*key`, `auth`,
  `credential`, `cookie`, `session_id`, as `name=value`, `name: value`, JSON `"name": "value"` or a `--name
  value` flag), `Authorization:` and `Bearer` credentials, URL passwords, and long high-entropy runs (mixed
  case with digits, 20+ characters; hex, 32+) become `***`. Masking comes before the cut, so a secret
  straddling it leaves no fragment. It errs on masking more (a commit hash is masked too); `targets` are
  logged unmasked, since they are paths inside the ticket system's source. T1 samples 80 characters, T2 160.
- **The root.** `CLAUDE_PROJECT_DIR` (Claude Code always sets it for hooks), else the hook input's `cwd`
  only when that folder holds `.claude/hooks/tickets/`, else the project this file sits in. A session that
  cd'd into a subfolder therefore never grows a stray `build/hooks/tickets/` there.
- **Runtime files** (gitignored, under `build/`): `build/hooks/tickets/hits.jsonl` (rotates to `.1` at 5 MB)
  and `build/hooks/tickets/prompt_clock.json` (the previous prompt: `ts`, `iso`, `session`, `kind`). A copy run
  from a release export (`<export>/payload/dot-claude/hooks/tickets`) writes neither file inside the export's
  `payload/` (B46): with no `CLAUDE_PROJECT_DIR` its root falls back to that `payload/`, and the hit log and the
  clock are then skipped. Run the self-test there, not live hooks.
- **The self-test writes nothing in a staged copy, and nothing in the project unless you name a folder there.**
  A staged copy can sit in any folder. The self-test's throwaway projects are folders named
  `tickets-selftest-*` directly under one scratch base, one per case group, each removed when its group ends,
  also when a case fails or raises. The scratch base is the system temp folder, or the folder given with
  `--scratch <dir>`.
  - **The system temp folder (the default, when `--scratch` is not given).** Pass `--scratch` instead (below)
    unless your rules allow temp writes. The candidates are `tempfile`'s own, in its order: `TMPDIR`,
    `TEMP`, `TMP`, the platform's fallbacks (on Windows `~\AppData\Local\Temp`, `%SYSTEMROOT%\Temp`, `c:\temp`,
    `c:\tmp`, `\temp`, `\tmp`), then the working directory. The first one that is an existing folder decides,
    and it is checked against the protected folders before anything is written. A candidate that is missing, or
    that cannot hold a folder (one `os.mkdir` fails, for example in a folder whose ACL denies it), is skipped, as
    `tempfile` skips it. The scratch folder is made with one `os.mkdir` under a random name, retried at most 8
    times and only when the name is taken, never with `tempfile.mkdtemp()`, which on Windows retries without end
    in such a folder. **Known limit:** the list comes from `tempfile._candidate_tempdir_list()`, a private
    function of the standard library; on a Python without it the self-test rebuilds the same list itself. From 1.2.2 the self-test reads this list
    itself and never calls `tempfile.gettempdir()`, whose first call creates and deletes a probe file in the
    folder it picks (B39); up to 1.2.1 a refused `TMP` got that one transient file.
  - **Protected folders (temp folder):** this package's own folder always, and the tree around it only when it
    has a known shape: `<project>/.claude/hooks/tickets` (installed: the project) or
    `<export>/payload/dot-claude/hooks/tickets` (an export: its `payload/`). A copy staged in any other folder
    protects only its own folder, so the folders above it are never mistaken for a project.
  - **`--scratch <dir>`** (from 1.2.2, B38) is what to pass: a project whose rules keep every write inside the
    repo (scratch in `<project>/.claude/scratch/<role>/<task>/`) gives that folder, and the default, which
    refuses any `TMP` inside the project, is not used. Every entry point's `--self-test` takes it, also as
    `--scratch=<dir>`:

        python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test --scratch <project>/.claude/scratch/<role>/<task>/

    - `<dir>` must exist and be a folder; the self-test does not create it. A relative path is taken from the
      working directory. Gitignore it: a killed run can leave a `tickets-selftest-*` folder there.
    - It may lie inside the project. It must lie outside this package's folder and outside the board,
      `<project>/.claude/tickets`. For a copy run inside an export it must lie outside the export's whole
      `payload/`. Wherever the copy sits, it must not lie in any folder shaped `.claude/tickets`,
      `.claude/hooks/tickets` or `dot-claude/hooks/tickets`: a staged copy knows no project, and still never
      writes into a board.
    - It must not be the project root or `.claude/` itself (from 1.3.0, B45): a killed run's `tickets-selftest-*`
      folder there would be ignored by nothing. That covers the project this copy is installed in and, for any
      copy, every folder holding a `.claude` folder and every folder named `.claude`. Subfolders are fine, such as
      `.claude/scratch/<role>/<task>/`. The refusal reads `self-test: refused: the --scratch folder <dir> is a
      project root, ...` or `... is a .claude folder itself, ...`.
    - A link or a junction is followed, on the way or as the folder itself. Every check, every scratch folder
      and the removal use the real path it reaches, so what is checked is where the writes land: a junction
      into the board is refused, and a junction to an allowed folder works.
    - The system temp folder is not used: no scratch folder goes there, the `TMPDIR` / `TEMP` / `TMP` check is
      skipped, and `tempfile.gettempdir()` is not called. The cases that test the temp-folder check still
      run, with those variables set to folders inside `<dir>` and this package, and restored afterwards.
    - **The alternative** needs no option: run the self-test from an export, or from any staged copy outside
      the repo (step 1 of "install and upgrade"). It tests the same files.
  - **Refusal:** the self-test prints one line, `self-test: refused: <reason>`, and exits 2 (1 means a case
    failed). Nothing is written before a refusal: no scratch folder, and no probe file either. It refuses when:
    - the first existing temp candidate lies inside a protected folder. The line names the folder and where it
      came from (`from TMPDIR`, `from TEMP`, `from TMP`, a fallback, the working directory). The candidates
      after it are not tried, so a `TMP` pointing into the project is never quietly replaced by a fallback.
      Point `TMPDIR`, `TEMP` and `TMP` at another folder, or pass `--scratch <dir>`;
    - no temp candidate is a folder that can hold a scratch folder;
    - the `--scratch` folder lies inside a protected folder, is the project root or a `.claude` folder itself, is
      missing, is not a folder or cannot hold a
      folder, or `--scratch` has no folder after it or is given twice;
    - an argument is not `--self-test`, `--scratch <dir>` or `--scratch=<dir>`. The line names it. A mistyped
      option (`--Scratch`, `--scratch-dir`, `-scratch`) therefore never falls back to the system temp folder.
      Up to 1.2.1 other arguments were ignored. A live hook call takes no arguments and is not affected.
  - **Paths are compared** on their real paths (8.3 short names and links resolved), and the installed or
    exported shape is read from the package folder's real path too, so a start through an 8.3 name or a
    junction is judged as the folder it reaches. The comparison is case-insensitive on
    Windows, with no trailing separator (`\\host\share\` equals `\\host\share`, `C:\` equals `C:`). A
    `\\?\` or `\\.\` prefix is dropped (`\\?\UNC\host\share` is `\\host\share`), and this machine's admin
    shares (`\\localhost\c$\...`, `\\127.0.0.1\c$\...`, `\\<its hostname>\c$\...`) read as drive paths. A
    `--scratch` folder goes through the same comparison.
    **Known limit:** other aliases of a protected folder are not recognised: a `subst` or mapped drive letter,
    another share of the same folder, or another address of this machine. A `TMP` or a `--scratch` pointing
    into a protected folder through one of those gets past the refusal.
  - **Removal is guarded:** it deletes only the folder it created, which must be a real directory with that
    prefix, directly under the scratch base and outside every protected folder, never a link or a junction.
    Whenever it leaves a folder it created, whether declined or not removable (a file still held open), it
    names it on stderr (`self-test: left <folder>: <reason>`). That folder stays in the scratch base, never in
    a protected folder.
  - **Leftovers:** a killed run (no `finally`) can leave a `tickets-selftest-*` folder in the scratch base (the
    temp folder, or your `--scratch` folder); it is safe to delete. Up to and including 1.2.0 the self-test
    used `build/hooks/tickets/selftest/`, so a leftover there from an interrupted older run is safe to delete
    too.
- **Bytecode.** `python -I` ignores every `PYTHON*` environment variable, `PYTHONDONTWRITEBYTECODE` included,
  so a live hook call creates `__pycache__/` under `.claude/hooks/tickets/` on its first run. Gitignore
  `__pycache__/`. The self-test never does: the documented command passes `-B`, and the entry points also
  turn bytecode off before `--self-test` imports anything, so a staged copy stays byte-identical even
  without `-B`.
- **Known limit: the Windows clock race.** Two sessions in one project submitting prompts in the same instant
  can both read the same previous prompt, and on Windows `os.replace` can fail while another process holds
  the state file open (that write is dropped). The worst case is one missed or one extra probe, accepted
  because T1 is log-only and the window is milliseconds wide, so there is no locking.
- **Commands.**

      python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test --scratch <dir>   (or write_guard.py / shell_guard.py; scratch in <dir>)
      python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test                   (no --scratch: the system temp folder)
      python .claude/hooks/tickets/replay.py [--show T1|T2|T2-miss] [--sample N] [--sweep] [--root <transcript dir> ...]
      python .claude/hooks/tickets/replay.py --probe 5          (times the live health probe; read-only GETs)

## T1. the ticket viewer runs when work resumes after a quiet spell (class c, log-only)

User rule, 2026-09-30: "Make sure that your ticket system is running anytime you detect a long period of no
conversation and work is just starting". The viewer runs as a visible background task of the session
(`.claude/docs/tickets.md`, "The viewer").

**Class (c), partly checkable.**

- **Checkable exactly:** the quiet spell, which is the time since the previous prompt in this project, from the
  hook's own clock. Also checkable: whether the viewer is running, via one GET on `/api/health` that answers
  with the project's service marker.
- **Not checkable, part 1: "work is just starting".** That is the prompt's intent. It is over-approximated as
  every human or peer prompt after a quiet spell (in the measured sample, about 1 in 5 such prompts was a
  status ping or a question).
- **Not checkable, part 2: the remedy.** The viewer must run as a visible background task of the session, and
  a hook cannot create one. A hook could start `serve.py` detached, but that would go around the documented
  procedure, so it does not.

The enforced form is therefore a reminder injected as `additionalContext`, never a block and never a start.
A build-time check or a git hook would not fit: neither runs when a conversation resumes, and neither can see
prompt timing.

**The check** (`rules/prompt/t1_viewer_after_quiet_spell.py`):

1. `prompt_clock.classify()` reads the prompt text, which is all the live input carries:
   - `human`: the user typing, slash commands included.
   - `peer`: "Another Claude session sent a message:" followed by `<cross-session-message`, for example a
     downstream ticket request.
   - `agent-report`: the same header followed by `<agent-message`: this session's own sub-agent reporting, so
     work is already running.
   - `task-notification`.

   Only `human` and `peer` count as conversation. They read and move the clock and can fire T1. The other two
   are ignored completely.
2. The runner moves the project's clock once per conversation prompt, before any rule runs, and hands T1
   `gap_s`, the seconds since the previous conversation prompt in this project, from any session.
3. **Quiet spell:** `gap_s >= QUIET_SPELL_S` (30 min), or no previous prompt on record (the first prompt after
   install, or a corrupt state file). A negative gap (the clock moved back) does not count.
4. On a quiet spell, T1 reads the viewer config (see "config") and probes it:
   - **1.1.0 and later:** `viewer_port` and `viewer_service` (or the marker derived from `store_name`) from
     `config.json`; the viewer script has no port or marker constants.
   - **A 1.0.0 copy:** the viewer script's module-level `default_port`, `service_marker` and `health_path`
     fill whatever `config.json` lacks, so an adopter who installs the hooks before upgrading the tool still
     gets a working T1.
   - **Ports probed:** the port a running viewer recorded in `build/tickets/serve.pid` (JSON `{pid, port,
     ...}`) comes first, then the configured port if different. A viewer started with `--port N` therefore
     reads as up. A stale pid file costs one extra timeout. The first port that answers as up wins;
     otherwise `foreign` beats `down`.
   - The probe is `http.client` to 127.0.0.1 with a 0.3 s timeout and no proxy lookup, imported lazily (about
     100 ms) so only a quiet-spell prompt pays for it.
   - The result is `up`, `down` (no answer) or `foreign` (something else answers on the port, so `serve.py`
     would refuse to start).
   - A project with no viewer config makes T1 silent.
5. The verdict is `remind` when the viewer is `down` or `foreign`, `ok` when it is `up`. Both are logged, so
   the log shows how often the probe runs. The row carries the mode the call ran in, the port that answered,
   the ports probed, the config source (`config`, `script`, `store_name`, `pidfile`) and the masked sample.
6. Enforced (`"T1"` in `ENFORCE`, which it is not as shipped), the reminder names the gap, the health URL,
   the state and the fix: `python <tool>/serve.py --stop`, then `python -u <tool>/serve.py --foreground`
   with run_in_background.

**Threshold: `QUIET_SPELL_S = 30 * 60`.** It sits past the p90 of the gap between conversation prompts in every
corpus with real volume (see "measured evidence"). An ordinary pause between turns does not reach 30 minutes,
while a break, a meal, a night or a context restart does.

**Not confirmed live:** whether peer messages, sub-agent reports and task notifications reach the live
UserPromptSubmit input with the same text as the transcript records. The classifier is proven on transcript
text only. Confirm on the first `hits.jsonl` rows (`kind`, `sample`).

**Enforce readiness.** The mechanics are ready: it never blocks, fails open, uses a bounded probe and stays
under 0.6 s in the worst case. Enforcing is each project's user's call, after a few live quiet-spell rows.

## T2. the board is the project's own; the ticket system's source is not changed locally (class c, log-only)

User rule, 2026-09-30: "The Ticket Master project will now be the source of truth for any future changes, so
you may get tickets from him to update your ticket system", clarified the same day: "Our ticket system is
still ours. The ticket master is just the maintainer of the source code and versioning and changes. We just
use the board." The tickets skill and `.claude/docs/tickets.md` carry the procedure.

**Class (c), partly checkable.** A write into the ticket system's source is exactly detectable. "Tied to a
Ticket Master request" is approximated as "a ticket whose body carries the provenance line `Requested by
Ticket Master ...` is active (`in_progress` or `in_review`)". The provenance line is the skill's format:
`Requested by <session name> (<from-session id>) on <YYYY-MM-DD> via cross-session message.` Filing the
request, replying, and telling Ticket Master when an update is committed are about message content, which no
hook sees. A git pre-commit hook could catch a commit touching the tool, but the rule is about making the
change at all, and it cannot see the ticket store at the time of the edit, so a PreToolUse hook is the earlier
and more exact place.

**The board is never judged.** The tickets (written by `tickets.py new` / `set`), `tags.json` and the settings
(`config.json`) are the project's own. `ticket.schema.json` is left out too: the format is maintained upstream,
but the file also carries the project's own enums and id pattern, and a static check cannot tell a format
change from a settings change. `hooklib/policy.py` is the project's own enforce setting and is not judged.

**The check** (`rules/write/t2_ticket_system_fork.py`):

1. **Targets.**
   - Write/Edit/MultiEdit/NotebookEdit: `file_path` / `notebook_path`.
   - Bash/PowerShell: `hooklib/shell.py`, a static parser that never runs anything. It covers:
     - output redirects (`>`, `>>`, `>|`, `&>`, `*>`, `N>`) and the read-write `<>`; input redirects (`<`,
       `<<`, `<<<`) and their operand are reads and never a target;
     - `cp`, `mv`, `install`, `ln`, `xcopy`, `robocopy`, `Copy-Item`, `Move-Item`, `Rename-Item` (a move also
       changes its source);
     - `touch`, `mkdir`, `tee`, `truncate`, `Set-Content`, `Add-Content`, `Out-File`, `New-Item`,
       `Clear-Content`;
     - `rm`, `rmdir`, `del`, `unlink`, `Remove-Item`;
     - `sed -i` and `perl -i`;
     - `git rm`, `mv`, `checkout` and `restore`.

     PowerShell `-Path` / `-Destination` / `-FilePath` values are read by name, and comma lists are split.
     Heredoc and here-string bodies are dropped first, because a `>` inside them is data.
   - **Cost: linear and bounded.** One regex pass finds the separators and the redirections, the text is
     rebuilt once, wrappers are skipped by index, and here-strings are dropped in one forward pass. Only the
     first 1 MiB of a command is read, and only the first 64 KiB after heredoc bodies are dropped is parsed;
     a longer command loses its last (possibly cut) segment, so a cut never invents a target, and its row
     says `"partial": true`.
2. **Where it lands.** `paths.resolve()` works lexically: MSYS paths are mapped, a relative path is joined to
   the call's `cwd`, and `..` is collapsed. A variable, a substitution or `~` does not resolve.
   `paths.rel_to_root()` then compares case-insensitively.
3. **Protected.**
   - The tool's folder (see "config"). When no folder is known, both `tools/tickets` and `src/tools/tickets`.
   - The tickets skill, `.claude/skills/tickets/**`, and these hooks, `.claude/hooks/tickets/**`.
   - A delete of an ancestor (`rm -r tools`, `rm -r .claude`) counts. A write into an ancestor (a copy into
     `tools/`) does not.
   - `__pycache__` and `.claude/hooks/tickets/hooklib/policy.py` never count.
4. **Verdict.** `tied` if `ticket_store.active_from(root, "Ticket Master")` finds an `in_progress` or
   `in_review` ticket with that provenance line (review fixes happen while the ticket is in review). The
   session name can be overridden in `config.json` `source_of_truth_session`. Otherwise the verdict is `fork`.
   A ticket file that does not parse (malformed, oversized, or nested deep enough to raise `RecursionError`) is
   skipped and the others still count. A ticket file's number has 4 to 9 digits (more only for a longer
   `first_ticket_number`), the same rule as the CLI's. Both verdicts are logged, with the targets, the verbs, the tied ticket
   ids, `partial`, `agent` when a sub-agent made the call, and the masked sample.
5. **Enforced** (`"T2"` in `ENFORCE`, which it is not as shipped): a PreToolUse deny for a `fork` naming the
   paths and the way out: send the change to Ticket Master as a request (with no such session on this machine,
   draft an issue for the GitHub repo's issues, `https://github.com/shadowevil/claude-ticket-system/issues`, and
   post it only with the user's OK); or, if it is a Ticket Master update, file it with the provenance line and set
   it `in_progress` first. A `tied` write is never denied.

**Not seen** (a static parser's blind spot): writes made inside an interpreter (`python script.py --apply`,
`python -c`), variables and substitutions as targets. `replay.py --show T2-miss` lists commands that mention
the tool but yield no target, for hand-checking.

**Enforce readiness.** The mechanics are ready. A deny would stop an update whose ticket is not yet
`in_progress`, and that nudge is itself the tickets rule "status tracks the work". Enforcing is each project's
user's call, after the first live Ticket Master update logs `tied`.

## changes from the reviewed source (1.1.0)

The hooks were first written and reviewed in one adopting project and moved here on 2026-09-30. For 1.1.0:

- Namespaced: `.claude/hooks/tickets/` and `build/hooks/tickets/`; the root test looks for
  `.claude/hooks/tickets/`. Wiring ships as `settings.snippet.json`.
- Config-driven: T1 reads `viewer_port` / `viewer_service` (default from `store_name`) from `config.json` and
  parses a viewer script's constants only as the 1.0.0 fallback; T2's tool folder is `tool_dir`, else the
  folder of `viewer_script`, else the installed one of `tools/tickets` and `src/tools/tickets`.
- T2 also protects `.claude/hooks/tickets/**` (these hooks are ticket-system source now), except `policy.py`.
- T2 ties on `in_review` as well as `in_progress`.
- The four follow-ups of the first review are fixed, each with self-test cases: `shell.py` is linear and
  bounded (it was quadratic on many here-strings, redirections or `VAR=x` prefixes); a `<` operand is a read,
  not a write target; every JSON read (`ticket_store`, config, pid file, clock) also survives
  `RecursionError`; a `tool_dir` overlapping `.claude/tickets` is ignored with a breadcrumb, and log samples
  are secret-masked before they are cut.

## measured here (Ticket Master, 2026-09-30)

- **Self-test** from an installed copy in a scratch project (`python -I -S -B .claude/hooks/tickets/prompt_guard.py
  --self-test`, with and without `CLAUDE_PROJECT_DIR`): **382 assertions, 0 failures** (T1 104, T2 139,
  framework 139) on Windows from 1.3.0 (365, framework 125, in 1.2.2; 308, framework 68, in 1.2.1), the same through `write_guard.py` and
  `shell_guard.py`, and the same with `--scratch`. Elsewhere the framework count is lower, because the Windows
  path-alias cases are skipped, and one case fewer runs on a volume that keeps no 8.3 short names. The count is
  the number of assertions actually made (`fixtures.Checker`), never a hand-kept constant.
- **Self-test on a staged copy** (B35), a release export's `payload/dot-claude/hooks/tickets/prompt_guard.py`
  run in place, through all three entry points and once without `-B`: 0 failures, and every file and folder
  of the export identical before and after (listing and hashes). The same held for copies staged in plain
  folders (`<scratch>/stage/tickets`, `<scratch>/hooks/tickets`), also with `TMP` inside the folder three
  levels up. The installed run left the scratch project's listing identical too. With `TMP` inside the project
  (plain, `\\?\`, `\\localhost\c$` and `\\?\UNC\localhost\c$` forms) or inside the package, every entry
  point printed one `self-test: refused:` line and exited 2, and the project was unchanged. A forced failing
  check and a forced raise each left no `tickets-selftest-*` folder behind in the temp folder.
- **`--scratch` and the probe file** (B38, B39; 1.2.2, on Windows), an installed copy in a scratch project:
  - With `--scratch <project>/working/x` (also relative, as `--scratch=<dir>`, as a nested gitignored folder `working/<sub>/<role>`,
    as the project root, and through a junction to `working/x`), every entry point passed and left the folder
    empty and the project's listing and hashes identical. `TMPDIR` / `TEMP` / `TMP` pointed at an empty folder
    under a `ReadDirectoryChangesW` watcher, which saw no event; a run with `tempfile.gettempdir()` patched to
    raise and every `os.open`, `os.mkdir` and writing `open()` logged passed, with all 275 creations under
    `working/x`.
  - `--scratch` inside `.claude/hooks/tickets` or `.claude/tickets` (plain, a subfolder, a trailing separator
    or dot, upper case, `\\?\`, `\\localhost\c$`, `\\?\UNC\localhost\c$`, the 8.3 name `CLAUDE~1\...`, and a
    junction into the board), a missing folder, a file, an empty value and no value: each printed one
    `self-test: refused:` line and exited 2, with no event under `.claude/` and the project unchanged. A
    staged export refused `--scratch` inside its `payload/`.
  - With `TMPDIR` / `TEMP` / `TMP` inside the package, the board or the project (plain, `\\?\` and
    `\\localhost\c$` forms), every entry point refused with exit 2. The watcher saw no event in the folder, and
    the logging run recorded no creation attempt in the project and no `gettempdir()` call. The same watcher
    and log on the 1.2.1 package showed its probe file (added, modified, removed), so both can see one.
  - A forced failing check and a forced raise, each with and without `--scratch`, left no `tickets-selftest-*`
    folder in the scratch base. Three runs at once sharing one `--scratch` folder, and three sharing one temp
    folder, all passed and left it empty.
  - A folder whose ACL denies creating files and folders (`icacls <dir> /deny <user>:(AD,WD)`): as `--scratch`
    it was refused in 0.2-0.3 s; as `TMPDIR` / `TEMP` / `TMP` it was skipped and the run passed in the fallback
    temp folder in under 5 s, as the 1.2.1 package does.
  - `--Scratch <dir>`, `--scratch-dir <dir>`, `-scratch <dir>`, `--SCRATCH=<dir>` and a stray word: each
    entry point refused with exit 2 and no event in the project or the temp folder. A live call with a stray
    argument still exited 0 and printed nothing.
- **The wiring**, the exact `settings.snippet.json` strings through `bash -c`, with both
  `C:\Program Files\Git\bin\bash.exe` and `usr\bin\bash.exe`: exit 0 with the scripts present (one row each,
  empty stdout and stderr) and exit 0 with them missing (Python's "can't open file" on stderr only).
- **Namespacing:** a scratch project with its own `.claude/hooks/hooklib/` whose `__init__.py` raises: the
  ticket hooks ran from `.claude/hooks` as the working directory, and with `PYTHONPATH` pointing at the dummy
  and without `-I -S`, logged their rows, and the self-test passed; the dummy was never imported.
- **Parser cost** at 60,000 characters: many here-string openers 0.10 s (the first version took 8.5 s), many
  redirections 0.03 s, many `VAR=x` prefixes 0.04 s; a 2.4 MB command 0.08 s (parsed to 64 KiB, `partial`).

## measured evidence (from the adopting project that first ran these hooks, 2026-09-30)

Measured by that project (project A below) on its own and its peers' transcripts, before the move; kept as the
calibration record. The projects are named neutrally: they are the corpora measured, not configuration.

- **Threshold calibration.** Gap between conversation prompts:

  | Corpus | Conversation prompts | Gap median | Gap p90 | Quiet spells at 30 min |
  | --- | --- | --- | --- | --- |
  | project B | 274 | 0.9 min | 21.1 min | 23 (8.4%) |
  | project C (before a move) | 888 | 2.8 min | 28.2 min | 78 (8.8%) |
  | project D | 14 | 3.2 min | 19.0 min | 1 (7.1%) |
  | project A | 7 | 19.3 min | 32.2 min | 2 |

  The sweep showed no knee to prefer instead; 20 minutes added about 30% more probes and very few extra
  reminders, because the viewer is normally up mid-session. The text classifier agreed with the transcript's
  `origin.kind` on 1,969 of 1,969 records.
- **Hand-checked sample** of 37 quiet-spell prompts: 29 were work starting or resuming, 8 were not (status
  pings, bare questions, a `/compact`, a "Disregard"). Such a prompt costs one probe, and a reminder only if
  the viewer is actually down.
- **T2 replay:** 229 write/shell calls in project A (2 hits) and 14,316 in the project B corpus (26 hits),
  every hit a real write into the tool's source or the skill: 0 parser false positives in 28 hits. 52 board
  edits through the CLI or directly: 0 flagged. Check cost 0.17-0.18 ms median per call.
- **Probe latency:** loopback stub up 1-23 ms; a live viewer up, median 14 ms; a closed port or a silent
  listener 309-314 ms, capped by the 0.3 s timeout.
- **Hook wall time** (`python -I -S`, interpreter start included, median of 7): no quiet spell 61 ms; quiet
  spell with the viewer up 116 ms, down 426 ms. `write_guard` and `shell_guard` through `bash -c` about
  95-100 ms, of which the rule itself is under 1 ms.
