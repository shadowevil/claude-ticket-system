"""The `--self-test` collector: every rule module named by the entry points' rule_modules() runs its own
checks, then the checks that span modules - every message is ASCII, ENFORCE holds only ids the user chose,
the library is the one in this folder (never a project's own .claude/hooks/hooklib), a rule module that raises
is isolated (no output, one breadcrumb carrying the exception type but never its message), a logged sample
never carries a secret, a hostile JSON file reads as None, and the scratch folders lie outside this package
and its project, are removed even when a case raises, and are refused (one line, exit 2) rather than put
inside them. The reported count is the number of assertions actually made. Any entry point runs it,
installed or from a copy staged in any folder (it writes nothing inside either; -B, and the entry point
itself, keep __pycache__ out):

	python -I -S -B .claude/hooks/tickets/prompt_guard.py --self-test [--scratch <dir>]

--scratch puts every scratch folder in <dir> instead of the system temp folder, which is then not used at all:
for a project that keeps every write inside the repo. <dir> must exist and may lie inside the project, but
outside this package folder and the board (.claude/tickets), and is neither the project root nor .claude itself
(e.g. .claude/scratch/<role>/<task>); see fixtures.explicit_base(). Any other argument
is refused (exit 2), so a mistyped --scratch never falls back to the temp folder.
"""
import json
import os
import sys
import time
import types

import hooklib
from hooklib import fixtures
from hooklib import jsonfile
from hooklib import output
from hooklib import paths
from hooklib import runner
from hooklib.policy import ENFORCE, USER_ENFORCED


ENTRY_POINTS = ("prompt_guard", "write_guard", "shell_guard")

# (text, secrets that must not survive in the sample, text that must survive)
REDACT_CASES = [
	("curl -H 'Authorization: Bearer abcDEF123456ghiJKL789xyz' https://api.example.test/x",
	 ["abcDEF123456ghiJKL789xyz"], "curl -H"),
	("curl -H \"Authorization: Basic dXNlcjpwYXNzd29yZA==\" http://127.0.0.1/", ["dXNlcjpwYXNzd29yZA"], "curl"),
	("export GITHUB_TOKEN=ghp_AbCdEf1234567890AbCdEf1234567890abcd && make", ["ghp_AbCdEf", "1234567890abcd"], "make"),
	("mysql --password=hunter2 -u root db", ["hunter2"], "-u root db"),
	("tool --token s3cr3t --verbose", ["s3cr3t"], "--verbose"),
	("$env:API_KEY = 'xyzzy-plugh'; python run.py", ["xyzzy-plugh"], "python run.py"),
	("git clone https://user:pa55word@git.example.test/repo.git", ["pa55word"], "user:"),
	('{"client_secret": "abc", "name": "n"}', ['"abc"'], '"name": "n"'),
	("New-Object PSCredential('u', (ConvertTo-SecureString -String 'Pw1!' -AsPlainText)) -Password 'Pw2!'",
	 ["Pw2!"], "New-Object"),
	("echo Zm9vYmFyQmF6cXV4c2VjcmV0MTIzNDU2Nzg5MA/QmF6cXV4c2VjcmV0MTIzNDU2 | base64 -d",
	 ["Zm9vYmFyQmF6cXV4c2VjcmV0MTIzNDU2Nzg5MA"], "base64 -d"),
	("aws configure set aws_secret_access_key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
	 ["wJalrXUtnFEMI", "bPxRfiCYEXAMPLEKEY"], "aws configure"),
	("SESSION_ID=0123456789abcdef0123456789abcdef python x.py", ["0123456789abcdef"], "python x.py"),
]
# (text that must come through unchanged)
KEEP_CASES = [
	"cp a.py tools/tickets/serve.py",
	"python tools/tickets/tickets.py set TK-0002 --status done --author pm",
	"git log --oneline 7aeed49",
	"rules.write.t2_ticket_system_fork evaluate_tool RuntimeError",
	"C:\\Users\\Someone\\AppData\\Local\\Programs\\Python\\Python313\\python.exe -I -S x.py",
	"/c/Users/Someone/AppData/Local/Programs/Python/Python313/python.exe",
	"reset the password tokens for the keyboard author",
	"resume the codec work after lunch",
]


def collect_modules():
	"""Every rule module, once, in entry-point order - from the same rule_modules() the hooks run."""
	import importlib
	seen = []
	for name in ENTRY_POINTS:
		for mods in importlib.import_module(name).rule_modules().values():
			for mod in mods:
				if mod not in seen:
					seen.append(mod)
	return seen


def short_name(path):
	"""`path`'s 8.3 form on Windows, or None when there is none (elsewhere, or a volume that keeps no short names)."""
	if os.name != "nt":
		return None
	try:
		import ctypes
		buf = ctypes.create_unicode_buffer(1024)
		n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 1024)
	except (ImportError, AttributeError, OSError):
		return None
	short = buf.value if 0 < n < 1024 else ""
	return short if short and short.lower() != str(path).lower() else None


def clean_refusal(why):
	"""True when `why` is a refusal selftest.refused() prints as one ASCII line."""
	return bool(why) and "\n" not in why and "\r" not in why and all(ord(c) < 128 for c in why)


def scratch_checks(ck):
	"""The scratch folders: outside the protected folders (a staged copy stays unchanged), removed afterwards also
	when a case raises, a refusal instead of a write into a protected folder, and a note whenever one is left.
	The same cases run with and without --scratch; none looks at the real temp folder beyond the run's own
	scratch folders, and a --scratch run never at all."""
	import io
	import tempfile
	ok = ck.check
	j = os.path.join
	with fixtures.scratch_root() as root:
		fixtures.write_text(j(root, "build", "hooks", "tickets", "x.txt"), "x")
		ok(fixtures.outside_package(root), "the scratch folder %s lies inside %s"
		   % (output.ascii_text(root), output.ascii_text(fixtures.guarded_roots())))
	ok(not os.path.exists(root), "the scratch folder was not removed: %s" % output.ascii_text(root))
	try:
		with fixtures.scratch_root() as root:
			fixtures.write_text(j(root, "a", "b.txt"), "x")
			raise RuntimeError("forced")
	except RuntimeError:
		pass
	ok(not os.path.exists(root), "the scratch folder survived a raising case: %s" % output.ascii_text(root))

	# what is protected: the package folder always; the tree above it only in an installed or exported shape, so
	# a copy staged in any plain folder runs (never an arbitrary ancestor three levels up)
	for hooks, tree in ((j("S", "stage", "hooks", "tickets"), None), (j("S", "stage", "tickets"), None),
						(j("S", "tickets"), None), (j("P", ".claude", "hooks", "tickets"), "P"),
						(j("P", ".Claude", "Hooks", "Tickets"), "P"),
						(j("X", "payload", "dot-claude", "hooks", "tickets"), j("X", "payload")),
						(j("S", "claude", "hooks", "tickets"), None),
						(j("P", "x", "..", ".claude", "hooks", "tickets"), "P")):
		# the shape is read from the real path (8.3 names, junctions and `..` resolved)
		want = [os.path.realpath(hooks)] + ([os.path.realpath(tree)] if tree else [])
		got = fixtures.protected_roots(hooks)
		ok(got == want, "protected_roots(%r) = %r, want %r" % (hooks, got, want))

	# trailing separators, verbatim prefixes and this machine's admin shares compare equal (text only)
	if os.name == "nt":
		host = __import__("socket").gethostname()
		for a, b in (("\\\\host\\share\\", "\\\\host\\share"), ("C:\\", "C:"),
					 (os.path.dirname("\\\\host\\share\\tickets-selftest-x"), "\\\\host\\share"),
					 (os.path.dirname("C:\\tickets-selftest-x"), "C:\\"),
					 ("\\\\?\\C:\\Temp\\X", "c:\\temp\\x"), ("\\\\?\\UNC\\host\\share\\x", "\\\\host\\share\\x"),
					 ("\\\\.\\C:\\x", "C:\\x"), ("\\\\localhost\\c$\\Temp", "C:\\Temp"),
					 ("\\\\127.0.0.1\\C$\\Temp\\", "c:\\temp"), ("\\\\%s\\d$\\x" % host, "D:\\x"),
					 ("\\\\localhost\\c$", "C:\\")):
			ok(fixtures.norm_text(a) == fixtures.norm_text(b), "norm_text(%r) != norm_text(%r)" % (a, b))
		ok(fixtures.norm_text("\\\\otherhost\\c$\\x") != fixtures.norm_text("C:\\x"), "another host's share read as local")

	with fixtures.scratch_root() as root:
		temp_checks(ck, root)
		explicit_checks(ck, root)

		# a \\?\ alias of a usable base gives a plain, usable scratch folder: of the --scratch folder in a --scratch
		# run, else of the temp folder
		if os.name == "nt":
			alias = j(root, "alias-base")
			os.makedirs(alias)
			real_explicit, real_tempdir = fixtures.EXPLICIT, tempfile.tempdir
			try:
				if real_explicit:
					fixtures.EXPLICIT = fixtures.explicit_base("\\\\?\\" + alias)
				else:
					tempfile.tempdir = "\\\\?\\" + alias
				with fixtures.scratch_root() as made_in:
					fixtures.write_text(j(made_in, "a", "b", "c.txt"), "x")
					made = (os.path.isfile(j(made_in, "a", "b", "c.txt")) and not made_in.startswith("\\\\?\\")
							and fixtures.canonical(os.path.dirname(made_in)) == fixtures.canonical(alias))
				made = made and not os.listdir(alias)
			except (OSError, fixtures.ScratchRefused):
				made = False
			finally:
				fixtures.EXPLICIT, tempfile.tempdir = real_explicit, real_tempdir
			ok(made, "a \\\\?\\ scratch base did not give a plain, usable scratch folder")

		# a folder remove_scratch() declines is left and named on stderr
		stray = j(root, fixtures.SCRATCH_PREFIX + "nested")
		os.makedirs(stray)
		real_stderr = sys.stderr
		sys.stderr = captured = io.StringIO()
		try:
			gone = fixtures.remove_scratch(stray, fixtures.scratch_base())
		finally:
			sys.stderr = real_stderr
		note = captured.getvalue()
		ok(not gone and os.path.isdir(stray) and note.startswith("self-test: left ") and "not directly under" in note,
		   "a declined folder was removed or not named: %r" % note)

	# the command line: --scratch <dir> or --scratch=<dir>; without a folder, or twice, it refuses
	for argv, want in ((["--self-test"], None), (["--self-test", "--scratch", "d"], "d"),
					   (["--scratch=d", "--self-test"], "d"), (["--scratch="], "")):
		try:
			got = scratch_arg(argv)
		except fixtures.ScratchRefused as exc:
			got = exc
		ok(got == want, "scratch_arg(%r) = %r, want %r" % (argv, got, want))
	for argv in (["--self-test", "--scratch"], ["--scratch", "--self-test"], ["--scratch", ""],
				 ["--scratch", "a", "--scratch=b"], ["--self-test", "--Scratch", "d"], ["--self-test", "--scratch-dir", "d"],
				 ["--self-test", "-scratch", "d"], ["--self-test", "d"], ["--self-test", "--scratch", "d", "x"],
				 ["--self-test", ""], ["--SELF-TEST"]):
		try:
			scratch_arg(argv)
			why = None
		except fixtures.ScratchRefused as exc:
			why = str(exc)
		ok(clean_refusal(why), "scratch_arg(%r) did not refuse: %r" % (argv, why))
	ok(scratch_arg(["--self-test", "--self-test", "--scratch", "-d"]) == "-d", "a folder named -d was not taken")

	out = io.StringIO()
	real_stdout = sys.stdout
	sys.stdout = out
	try:
		code = refused(fixtures.ScratchRefused("the temp folder C:\\x lies inside C:\\x;\npoint TMP elsewhere"))
	finally:
		sys.stdout = real_stdout
	text = out.getvalue()
	ok(code == 2 and text.count("\n") == 1 and text.startswith("self-test: refused: ") and all(ord(c) < 128 for c in text),
	   "a refusal is not one ASCII line with exit 2: %r" % text)


def temp_checks(ck, root):
	"""The system temp folder route (B39), in a --scratch run too: its candidates are tempfile's, in tempfile's
	order; the first existing one decides, and one inside a protected folder refuses (one line) without a file or
	folder being tried anywhere and without tempfile.gettempdir(). Each case sets tempfile.tempdir or TMPDIR /
	TEMP / TMP to folders under `root` or in this package, so the real temp folder is never looked at."""
	import builtins
	import tempfile
	ok = ck.check
	j = os.path.join
	pkg = j(paths.HOOKS_DIR, "hooklib")
	pkg_only = [os.path.realpath(paths.HOOKS_DIR)]
	good = j(root, "tmp-good")
	missing = j(root, "tmp-missing")
	fake_hooks = j(root, "P", ".claude", "hooks", "tickets")
	fake_work = j(root, "P", "working")
	for d in (good, fake_hooks, fake_work):
		os.makedirs(d)

	def set_env(tempdir=None, **values):
		tempfile.tempdir = tempdir
		for name in fixtures.TEMP_VARS:
			if values.get(name):
				os.environ[name] = values[name]
			else:
				os.environ.pop(name, None)

	def attempt(fn):
		"""(fn()'s result, its refusal or None, the writes it tried): every way to create a file or a folder, and
		tempfile's probing, is recorded and failed while fn runs, so none happens even if one is tried."""
		tried = []

		def spy(name):
			def blocked(*_args, **_kwargs):
				tried.append(name)
				raise OSError("blocked by the self-test: %s" % name)
			return blocked
		targets = ((os, "open"), (os, "mkdir"), (os, "makedirs"), (builtins, "open"), (tempfile, "gettempdir"),
				   (tempfile, "gettempdirb"), (tempfile, "_get_default_tempdir"))
		real = [(mod, name, getattr(mod, name)) for mod, name in targets if hasattr(mod, name)]
		for mod, name, _fn in real:
			setattr(mod, name, spy(name))
		try:
			try:
				return fn(), None, tried
			except fixtures.ScratchRefused as exc:
				return None, str(exc), tried
			except Exception as exc:  # a write or a gettempdir() call that was tried and blocked
				return None, "raised %s" % type(exc).__name__, tried + ["raised"]
		finally:
			for mod, name, fn in real:
				setattr(mod, name, fn)

	saved = (tempfile.tempdir, fixtures.EXPLICIT, dict((name, os.environ.get(name)) for name in fixtures.TEMP_VARS))
	try:
		fixtures.EXPLICIT = None  # the temp route, also in a --scratch run

		# tempfile.tempdir, when set, is the only candidate: inside the package (plain or \\?\) -> a clean refusal
		for label, tmp in (("the package folder", pkg),
						   ("a verbatim alias of it", "\\\\?\\" + j(os.path.realpath(paths.HOOKS_DIR), "hooklib"))):
			if label.startswith("a verbatim") and os.name != "nt":
				continue
			set_env(tempdir=tmp)
			_got, why, tried = attempt(fixtures.make_scratch)
			ok(clean_refusal(why) and "lies inside" in why and not tried,
			   "a temp folder in %s was not refused cleanly before any write: %r, tried %r" % (label, why, tried))

		# TMPDIR, TEMP and TMP inside the package -> refused, and no file or folder was even tried (B39), neither by
		# make_scratch() nor by preflight()
		set_env(TMPDIR=pkg, TEMP=pkg, TMP=pkg)
		_got, why, tried = attempt(fixtures.make_scratch)
		ok(clean_refusal(why) and "(from TMPDIR)" in why and not tried,
		   "TMPDIR/TEMP/TMP in the package: %r, tried %r" % (why, tried))
		_got, why, tried = attempt(fixtures.preflight)
		ok(clean_refusal(why) and not tried, "preflight with TMP in the package: %r, tried %r" % (why, tried))
		# a missing TEMP is skipped as tempfile skips it, and the TMP after it is judged, not passed over
		set_env(TEMP=missing, TMP=pkg)
		_got, why, tried = attempt(fixtures.make_scratch)
		ok(clean_refusal(why) and "(from TMP)" in why and not tried,
		   "a missing TEMP then TMP in the package: %r, tried %r" % (why, tried))
		# TMP inside an installed project (outside its package) -> refused, nothing tried
		set_env(TMP=fake_work)
		_got, why, tried = attempt(lambda: fixtures.temp_base(roots=fixtures.protected_roots(fake_hooks)))
		ok(clean_refusal(why) and "lies inside" in why and not tried,
		   "TMP in an installed project: %r, tried %r" % (why, tried))
		# the first existing candidate decides: a protected TMPDIR refuses even when TEMP is fine (no silent skip),
		# and a fine TEMP is used without TMP being looked at, without gettempdir() and without a write
		set_env(TMPDIR=pkg, TEMP=good)
		got, why, tried = attempt(lambda: fixtures.temp_base(roots=pkg_only))
		ok(got is None and clean_refusal(why) and not tried, "a protected TMPDIR was skipped: %r %r" % (got, why))
		set_env(TEMP=good, TMP=pkg)
		got, why, tried = attempt(lambda: fixtures.temp_base(roots=pkg_only))
		ok(why is None and got is not None and fixtures.canonical(got) == fixtures.canonical(good) and not tried,
		   "a usable TEMP before a protected TMP: %r %r, tried %r" % (got, why, tried))
		# the candidates are tempfile's, in its order, each named by the variable it came from
		set_env(TMPDIR=j(root, "a"), TEMP=j(root, "b"), TMP=j(root, "c"))
		got = fixtures.temp_candidates()
		ok(got[:3] == [("TMPDIR", j(root, "a")), ("TEMP", j(root, "b")), ("TMP", j(root, "c"))] and len(got) > 3,
		   "temp candidates out of tempfile's order: %r" % (got[:4],))
		set_env(tempdir=good)
		ok(fixtures.temp_candidates() == [("tempfile.tempdir", good)], "a set tempfile.tempdir is not the only candidate")

		# a base that cannot hold a folder (os.mkdir raises PermissionError, as in a folder whose ACL denies it)
		# costs one try, never a retry loop: the temp route skips to the next candidate, a route with no other
		# refuses, and so does --scratch; a name that exists is retried MKDIR_TRIES times, no more
		denied = j(root, "tmp-denied")
		os.makedirs(denied)
		real_mkdir = os.mkdir
		calls = []

		def deny(path, *args, **kwargs):
			if fixtures.canonical(os.path.dirname(path)) == fixtures.canonical(denied):
				calls.append(path)
				if len(calls) > 4 * fixtures.MKDIR_TRIES:  # a retry loop: end it, so the case fails and never hangs
					raise OSError(5, "too many tries")
				raise PermissionError(13, "denied by the self-test")
			return real_mkdir(path, *args, **kwargs)

		def clash(path, *_args, **_kwargs):
			calls.append(path)
			if len(calls) > 4 * fixtures.MKDIR_TRIES:  # as in deny(): the case must fail, not hang
				raise OSError(5, "too many tries")
			raise FileExistsError(17, "taken by the self-test")

		def refusal(**kwargs):
			try:
				fixtures.make_scratch(**kwargs)
				return None
			except fixtures.ScratchRefused as exc:
				return str(exc)
		os.mkdir = deny
		try:
			set_env(TEMP=denied, TMP=good)
			try:
				base, made = fixtures.make_scratch(roots=pkg_only)
			except fixtures.ScratchRefused as exc:
				base, made = None, str(exc)
			ok(base is not None and fixtures.canonical(base) == fixtures.canonical(good) and os.path.isdir(made)
			   and len(calls) == 1, "a TEMP that cannot hold a folder was not skipped after one try: %r, %d tries"
			   % (made, len(calls)))
			if base is not None:
				os.rmdir(made)
			del calls[:]
			set_env(tempdir=denied)
			why = refusal(roots=pkg_only)
			ok(clean_refusal(why) and "cannot create" in why and len(calls) == 1,
			   "the only temp folder cannot hold a folder: %r, %d tries" % (why, len(calls)))
			del calls[:]
			fixtures.EXPLICIT = fixtures.real_plain(denied)
			why = refusal()
			fixtures.EXPLICIT = None
			ok(clean_refusal(why) and "cannot create" in why and "--scratch" in why and len(calls) == 1,
			   "a --scratch folder that cannot hold a folder: %r, %d tries" % (why, len(calls)))
			del calls[:]
			os.mkdir = clash
			set_env(tempdir=good)
			why = refusal(roots=pkg_only)
			ok(clean_refusal(why) and len(calls) == fixtures.MKDIR_TRIES and not os.listdir(good),
			   "taken names were not retried a bounded number of times: %r, %d tries" % (why, len(calls)))
		finally:
			os.mkdir = real_mkdir

		# a temp folder that cannot hold a folder -> a refusal, not a traceback, and nothing created
		set_env(tempdir=j(root, "missing", "deeper"))
		try:
			with fixtures.scratch_root():
				why = None
		except fixtures.ScratchRefused as exc:
			why = str(exc)
		ok(clean_refusal(why) and not os.path.exists(j(root, "missing")), "an unusable temp folder was not refused: %r"
		   % (why,))
	finally:
		tempfile.tempdir, fixtures.EXPLICIT = saved[0], saved[1]
		for name, value in saved[2].items():
			if value is None:
				os.environ.pop(name, None)
			else:
				os.environ[name] = value


def explicit_checks(ck, root):
	"""--scratch (B38), in a run without it too: accepted inside an installed project outside its package and its
	board; refused before anything is written (one ASCII line) inside those in any spelling, when missing, a
	file or empty, and in a board-shaped folder anywhere; an export's payload/ stays whole; a scratch folder made
	under an accepted one is removed also when a case raises, and one in a board is never removed."""
	import io
	ok = ck.check
	j = os.path.join
	proj = j(root, "E")
	hooks = j(proj, ".claude", "hooks", "tickets")
	board = j(proj, ".claude", "tickets")
	work = j(proj, "working", "x")
	xhooks = j(root, "X", "payload", "dot-claude", "hooks", "tickets")
	shooks = j(root, "S", "tickets")
	task = j(proj, ".claude", "scratch", "worker", "x")
	for d in (j(hooks, "hooklib"), j(board, "sub"), work, task, j(root, "Q", ".claude", "tickets"),
			  j(root, "Q", ".claude", "hooks", "tickets", "x"), xhooks, j(root, "X", "payload", "docs"),
			  j(root, "X", "out"), j(shooks, "hooklib"), j(root, "S", "other"), j(root, "R", ".claude")):
		os.makedirs(d)
	fixtures.write_text(j(proj, "f.txt"), "x")

	def verdict(raw, hooks_dir=hooks):
		try:
			return fixtures.explicit_base(raw, hooks_dir), None
		except fixtures.ScratchRefused as exc:
			return None, str(exc)

	for raw in (work, j(proj, "working"), task, j(proj, ".claude", "scratch")):
		got, why = verdict(raw)
		ok(why is None and got == fixtures.real_plain(raw), "--scratch %s in the project was refused: %r"
		   % (output.ascii_text(raw), why))
	# the project root and .claude itself are refused (B45): a killed run's folder there is ignored by nothing; so is
	# any folder holding a .claude folder (a project root a staged copy cannot know) and any .claude folder
	refuse = [hooks, j(hooks, "hooklib"), board, j(board, "sub"), board + os.sep,
			  j(proj, "working", "..", ".claude", "tickets"), j(proj, "missing"), j(proj, "f.txt"), "", None,
			  j(root, "Q", ".claude", "tickets"), j(root, "Q", ".claude", "hooks", "tickets", "x"),
			  proj, proj + os.sep, j(proj, ".claude"), j(proj, ".claude") + os.sep, j(proj, "working", ".."),
			  j(root, "R"), j(root, "R", ".claude")]
	if os.name == "nt":
		refuse += [j(proj, ".CLAUDE", "Tickets"), "\\\\?\\" + board, board + ".", board + " ",
				   board.replace("\\", "/"), j(proj, ".CLAUDE"), j(proj, ".claude") + ".", "\\\\?\\" + proj]
		for protected in (board, hooks):
			short = short_name(protected)
			if short:
				refuse.append(short)
	for raw in refuse:
		got, why = verdict(raw)
		ok(got is None and clean_refusal(why), "--scratch %r was not refused cleanly: %r"
		   % (output.ascii_text(raw), got))
	ok(verdict(j(root, "X", "payload", "docs"), xhooks)[0] is None and verdict(j(root, "X", "out"), xhooks)[1] is None,
	   "an export's payload/ is not kept whole under --scratch")
	ok(verdict(j(shooks, "hooklib"), shooks)[0] is None and verdict(j(root, "S", "other"), shooks)[1] is None,
	   "a plain staged copy does not protect exactly its own folder under --scratch")
	ok(verdict(j(paths.HOOKS_DIR, "hooklib"), None)[0] is None, "--scratch inside this package was accepted")
	why = verdict(proj)[1]
	ok(clean_refusal(why) and "project root" in why and verdict(j(proj, ".claude"))[1] and
	   "itself" in verdict(j(proj, ".claude"))[1], "a project root or .claude refusal does not say why: %r" % (why,))
	# from a staged copy (no project known) a project root is still refused by its .claude folder
	ok(verdict(proj, shooks)[0] is None and verdict(work, shooks)[1] is None,
	   "a staged copy took a project root, or refused a folder in a project, as --scratch")

	saved = fixtures.EXPLICIT
	try:
		fixtures.EXPLICIT = fixtures.explicit_base(work)
		with fixtures.scratch_root() as made:
			fixtures.write_text(j(made, "a", "b.txt"), "x")
			direct = fixtures.canonical(os.path.dirname(made)) == fixtures.canonical(work)
		try:
			with fixtures.scratch_root() as made:
				fixtures.write_text(j(made, "a", "b.txt"), "x")
				raise RuntimeError("forced")
		except RuntimeError:
			pass
		ok(direct and os.listdir(work) == [], "a --scratch folder was not used directly or not emptied: %r"
		   % (os.listdir(work),))
		# a tickets-selftest-* folder in a board is never removed, whatever base it is handed with
		stray = j(board, fixtures.SCRATCH_PREFIX + "x")
		os.makedirs(stray)
		real_stderr = sys.stderr
		sys.stderr = captured = io.StringIO()
		try:
			gone = fixtures.remove_scratch(stray, board)
		finally:
			sys.stderr = real_stderr
		ok(not gone and os.path.isdir(stray) and "inside a protected folder" in captured.getvalue(),
		   "a folder in a board was removed under --scratch: %r" % captured.getvalue())
	finally:
		fixtures.EXPLICIT = saved


def scratch_arg(argv):
	"""The folder given with `--scratch <dir>` or `--scratch=<dir>` in `argv`, or None when there is none. Raises
	ScratchRefused when --scratch has no folder after it or is given more than once, and for any argument other
	than those two forms and --self-test: a mistyped --scratch must not quietly fall back to the system temp
	folder in a project that never uses it."""
	found = []
	i = 0
	while i < len(argv):
		arg = argv[i]
		if arg == "--scratch":
			if i + 1 >= len(argv) or not argv[i + 1] or argv[i + 1].startswith("--"):
				raise fixtures.ScratchRefused("--scratch needs a folder")
			found.append(argv[i + 1])
			i += 2
			continue
		if arg.startswith("--scratch="):
			found.append(arg[len("--scratch="):])
		elif arg != "--self-test":
			raise fixtures.ScratchRefused("unknown argument %s; the self-test takes --self-test [--scratch <dir>]"
										  % (arg or "''"))
		i += 1
	if len(found) > 1:
		raise fixtures.ScratchRefused("--scratch is given more than once")
	return found[0] if found else None


def refused(exc):
	"""Prints a ScratchRefused as one ASCII line; the self-test's exit code is 2."""
	text = str(exc).replace("\r", " ").replace("\n", " ")
	print("self-test: refused: " + text.encode("ascii", "backslashreplace").decode("ascii"))
	return 2


def framework_checks(ck, modules):
	ok = ck.check
	msgs = {}
	for mod in modules:
		msgs.update(mod.MSG)
	for rid, msg in msgs.items():
		ok(all(ord(ch) < 128 for ch in msg), "%s message is not ASCII" % rid)
	ok(ENFORCE <= USER_ENFORCED, "ENFORCE holds an id the user did not choose to enforce")

	# namespacing: the library and the rules are this folder's, whatever else is on sys.path
	here = os.path.normcase(paths.HOOKS_DIR)
	ok(os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(hooklib.__file__)))) == here,
	   "hooklib was imported from %s, not from this folder" % output.ascii_text(hooklib.__file__))
	ok(all(os.path.normcase(os.path.abspath(m.__file__)).startswith(here + os.sep) for m in modules),
	   "a rule module was imported from outside this folder")
	ok(os.path.normcase(os.path.abspath(sys.path[0])) == here, "this folder is not first on sys.path")
	ok(paths.runtime_dir("R").replace("\\", "/") == "R/build/hooks/tickets", "runtime dir is not build/hooks/tickets")
	# a live call from a release export writes nothing in its payload/ (B46): payload/ is the root it falls back to
	xhooks = os.path.join("X", "payload", "dot-claude", "hooks", "tickets")
	ihooks = os.path.join("P", ".claude", "hooks", "tickets")
	ok(paths.payload_root(xhooks) == os.path.realpath(os.path.join("X", "payload")) and paths.payload_root(ihooks) is None
	   and paths.payload_root(os.path.join("S", "dot-claude", "hooks", "tickets")) is None, "payload_root() misread a tree")
	ok(not paths.runtime_allowed(os.path.join("X", "payload"), xhooks)
	   and not paths.runtime_allowed(os.path.join("X", "payload", "sub"), xhooks)
	   and paths.runtime_allowed("X", xhooks) and paths.runtime_allowed("P", xhooks)
	   and paths.runtime_allowed(os.path.join("X", "payload"), ihooks), "runtime_allowed() misjudged an export")

	scratch_checks(ck)

	# a logged sample never carries a secret; ordinary commands and paths come through
	for text, secrets, keep in REDACT_CASES:
		got = output.sample_text(text)
		ok(not any(s in got for s in secrets) and keep in got and output.MASK in got,
		   "redact(%r) = %r" % (text[:40], got))
	for text in KEEP_CASES:
		got = output.sample_text(text)
		ok(got == output.excerpt(text), "over-masked %r -> %r" % (text[:40], got))
	# masking happens before the cut: a secret straddling the excerpt limit leaves no fragment
	pad = "x " * ((output.EXCERPT_MAX - 20) // 2)
	got = output.sample_text(pad + "--password=CorrectHorseBatteryStaple1234567890 tail")
	ok("Correct" not in got and len(got) <= output.EXCERPT_MAX, "a secret at the cut left a fragment: %r" % got[-40:])
	got = output.sample_text(pad + "k " + "aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xYz")
	ok("aB3dE" not in got, "a key at the cut left a fragment: %r" % got[-40:])
	started = time.perf_counter()
	got = output.sample_text("--token=" + "a" * 5000000)
	ok((time.perf_counter() - started) < 1.0 and "aaaa" not in got, "a 5 MB sample was slow or leaked")

	# the isolation of a raising module, and hostile JSON files
	def boom(*_args):
		raise RuntimeError("secret detail")
	broken = types.SimpleNamespace(__name__="rules.x.broken", evaluate_prompt=boom, log_rows=boom, decide=boom, MSG={})
	half = types.SimpleNamespace(__name__="rules.x.half", evaluate_prompt=lambda _e, _c: [{"x": 1}],
								 log_rows=boom, decide=boom, MSG={})
	with fixtures.scratch_root() as root:
		ctx = {"root": root, "now": time.time(), "kind": "human", "previous": None, "gap_s": None}
		rows, texts = runner.run({}, ctx, [broken, half], enforce=frozenset({"X"}))
		ok(not rows and output.prompt_context(texts) is None, "a raising module produced rows or context")
		try:
			with open(paths.hits_path(root), encoding="ascii") as fh:
				crumbs = [json.loads(line) for line in fh.read().splitlines()]
		except OSError:
			crumbs = []
		samples = sorted(c["sample"][0] for c in crumbs if c.get("rule") == "hook-error")
		ok(samples == ["rules.x.broken evaluate_prompt RuntimeError", "rules.x.half decide RuntimeError",
					   "rules.x.half log_rows RuntimeError"], "breadcrumbs: %r" % (samples,))
		ok(not any("secret detail" in json.dumps(c) for c in crumbs), "a breadcrumb carried the exception message")
		ok(paths.hits_path(root).replace("\\", "/").endswith("/build/hooks/tickets/hits.jsonl"),
		   "the hit log is not under build/hooks/tickets/")

		deep = os.path.join(root, "deep.json")
		fixtures.write_text(deep, "[" * 200000 + "]" * 200000)
		ok(jsonfile.load(deep) is None, "deeply nested JSON did not read as None")
		fixtures.write_text(deep, '{"a": ' * 100000 + "1" + "}" * 100000)
		ok(jsonfile.load_dict(deep, 10 ** 7) == {}, "deeply nested JSON object did not read as {}")
		fixtures.write_text(deep, '{"a": 1')
		ok(jsonfile.load(deep) is None and jsonfile.load(os.path.join(root, "missing.json")) is None,
		   "truncated or missing JSON did not read as None")
		with open(deep, "wb") as fh:
			fh.write(b'{"a": "\xff\xfe"}')
		ok(jsonfile.load(deep) is None, "a file that is not UTF-8 did not read as None")
		with open(deep, "wb") as fh:
			fh.write(b'\xef\xbb\xbf{"id_prefix": "BOM-"}')
		ok(jsonfile.load_dict(deep) == {"id_prefix": "BOM-"}, "a config.json with a UTF-8 BOM was not read")

	# no case, rule or fixture called tempfile.gettempdir(), whose first call writes a probe file in the temp folder
	# (B39): it keeps its answer in tempfile.tempdir, which is therefore still unset
	import tempfile
	ok(tempfile.tempdir is None, "tempfile.gettempdir() was called during the self-test")


def main(argv=None):
	"""Runs every check; exit 0 when all pass, 1 on a failure, 2 when no safe scratch folder can be had or an
	argument is not known (one ASCII line, no traceback, nothing written). `argv` (default sys.argv[1:]) may carry
	`--scratch <dir>`: every scratch folder then goes in <dir>, checked before anything is written
	(fixtures.use_scratch()), and the system temp folder is not used at all."""
	try:
		raw = scratch_arg(sys.argv[1:] if argv is None else argv)
		if raw is not None:
			fixtures.use_scratch(raw)
		fixtures.preflight()
		return run_all()
	except fixtures.ScratchRefused as exc:
		return refused(exc)


def run_all():
	modules = collect_modules()
	ck = fixtures.Checker("framework")
	n_cases = 0
	failures = []
	per_rule = []
	for mod in modules:
		count, found = mod.run_self_test()
		per_rule.append("%s %d" % (mod.RULE, count))
		n_cases += count
		failures.extend(found)
	framework_checks(ck, modules)
	count, found = ck.result()
	per_rule.append("framework %d" % count)
	n_cases += count
	failures.extend(found)
	n_rules = len({rid for mod in modules for rid in mod.MSG})
	print("self-test: %d assertions (%s), %d rule(s), %d failure(s)"
		  % (n_cases, ", ".join(per_rule), n_rules, len(failures)))
	for f in failures:
		print("  FAIL " + f.encode("ascii", "backslashreplace").decode("ascii"))
	return 0 if not failures else 1
