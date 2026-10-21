"""Self-test fixtures shared by rule modules: a throwaway project root under the system temp folder (never
inside a protected_roots() folder: this package's own folder, plus the project it is installed in or the
export's payload/ it sits in, so a staged copy that is not installed yet can be self-tested without changing
it), or under the folder given with `--scratch <dir>` (never inside a scratch_roots() folder: this package's own
folder, the installed project's board .claude/tickets, or an export's payload/, nor in any board-shaped folder, nor
a project root or a .claude folder itself),
stub projects in the 1.0.0 and 1.1.0 shapes, and loopback servers for the viewer probe.
Used only by `--self-test`, never by a live hook call."""
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from hooklib import paths

PREFIX = "TK-"


class Checker:
	"""Counts assertions as they run: `count` is the number of check() calls made, so the self-test's
	reported case count is the real number of assertions, never a hand-kept constant."""

	def __init__(self, prefix):
		self.prefix = prefix
		self.count = 0
		self.failures = []

	def check(self, ok, message):
		self.count += 1
		if not ok:
			self.failures.append("%s %s" % (self.prefix, message))
		return bool(ok)

	def result(self):
		return self.count, list(self.failures)


def write_text(path, text):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8", newline="\n") as fh:
		fh.write(text)


def write_json(path, value):
	write_text(path, json.dumps(value))


def write_config(root, config):
	write_json(os.path.join(root, ".claude", "tickets", "config.json"), config)


def write_pid_file(root, port):
	"""build/tickets/serve.pid as a running viewer writes it."""
	write_json(os.path.join(root, "build", "tickets", "serve.pid"),
			   {"pid": 1, "port": port, "bind": "127.0.0.1", "script": "serve.py", "started": "x"})


def write_ticket(root, tid, status, body, prefix=PREFIX):
	""".claude/tickets/<tid>.json with the fields the rules read (and config.json's id_prefix)."""
	cfg = os.path.join(root, ".claude", "tickets", "config.json")
	if not os.path.isfile(cfg):
		write_json(cfg, {"id_prefix": prefix, "first_ticket_number": 1, "store_name": "t"})
	write_json(os.path.join(root, ".claude", "tickets", tid + ".json"),
			   {"id": tid, "summary": "s", "body": body, "status": status, "tags": ["workflow"]})


def stdin_bytes(payload):
	"""A stand-in for sys.stdin with a .buffer, like the real one: the hook reads the bytes as UTF-8."""
	import io
	data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
	return io.TextIOWrapper(io.BytesIO(data), encoding="cp1252", errors="replace")


SERVE_STUB_100 = ('"""stub viewer for the hook self-test (1.0.0 shape: constants in the script)"""\n'
				  'default_port = %d\n'
				  'service_marker = "%s"\n'
				  'health_path = "/api/health"\n')
SERVE_STUB_110 = ('"""stub viewer for the hook self-test (1.1.0 shape: port and marker from config.json)"""\n'
				  'health_path = "/api/health"\n'
				  'default_port = config.get("viewer_port")\n')


SCRATCH_PREFIX = "tickets-selftest-"
# the parent folders that make HOOKS_DIR part of a real tree: an installed copy (<project>/.claude/hooks/tickets)
# or a release export (<export>/payload/dot-claude/hooks/tickets); anywhere else only the folder itself counts
TREE_SHAPES = ((".claude", "hooks", "tickets"), ("dot-claude", "hooks", "tickets"))
# folders no --scratch folder may lie in, wherever they are: a board, or an installed or exported hooks package
BOARD_SHAPES = ((".claude", "tickets"), (".claude", "hooks", "tickets"), ("dot-claude", "hooks", "tickets"))
# the variables tempfile reads for the temp folder, in its order
TEMP_VARS = ("TMPDIR", "TEMP", "TMP")
LOCAL_HOSTS = ("localhost", "127.0.0.1")
ADMIN_SHARE = re.compile(r"^\\\\([^\\]+)\\([A-Za-z])\$(\\.*)?\Z")
NO_TEMP = "no usable temp folder in TMPDIR, TEMP, TMP or the fallbacks"
# how many random names new_folder() tries in one base when each already exists
MKDIR_TRIES = 8

# the folder given with --scratch, as explicit_base() accepted it (use_scratch()); None: the system temp folder
EXPLICIT = None


class ScratchRefused(Exception):
	"""The self-test cannot get a safe scratch folder: selftest.main() prints the message as one ASCII line and
	exits 2, before or instead of running any case."""


def ascii_path(p):
	return str(p).encode("ascii", "backslashreplace").decode("ascii")


def unverbatim(p):
	"""`p` without a Windows `\\\\?\\` or `\\\\.\\` prefix: `\\\\?\\C:\\x` is `C:\\x`, `\\\\?\\UNC\\h\\s` is `\\\\h\\s`.
	Any other path is returned as given."""
	p = str(p)
	if os.name != "nt" or not p.startswith(("\\\\?\\", "\\\\.\\", "//?/", "//./")):
		return p
	rest = p[4:]
	if rest[:4].upper() in ("UNC\\", "UNC/"):
		return "\\\\" + rest[4:]
	return rest


def norm_text(p):
	"""`p` as a comparable string, from the text alone (the filesystem is never touched): no `\\\\?\\` prefix, this
	machine's admin shares (`\\\\localhost\\c$\\x`, `\\\\127.0.0.1\\c$`, `\\\\<hostname>\\c$`) as drive paths,
	normalized, case-folded on Windows, and with no trailing separator, so `\\\\host\\share\\` equals
	`\\\\host\\share` and `C:\\` equals `C:`."""
	p = os.path.normpath(unverbatim(p))
	if os.name == "nt":
		m = ADMIN_SHARE.match(p)
		if m and m.group(1).lower() in LOCAL_HOSTS + (socket.gethostname().lower(),):
			p = m.group(2).upper() + ":" + (m.group(3) or "\\")
		p = os.path.normcase(p)
	return p.rstrip("\\/")


def canonical(p):
	"""norm_text() of `p`'s real path: 8.3 short names, links and `..` resolved."""
	return norm_text(os.path.realpath(unverbatim(p)))


def real_plain(p):
	"""`p`'s real path (relative to the working directory, 8.3 names, links and `..` resolved) without a `\\\\?\\`
	prefix: the form every scratch base is used in."""
	return unverbatim(os.path.realpath(unverbatim(p)))


def inside(path, root):
	"""True when `path` is `root` or lies under it (both canonical())."""
	p, r = canonical(path), canonical(root)
	return p == r or p.startswith(r + os.sep)


def package_tree(hooks_dir=None):
	"""(the package folder's real path, the tree around it, the tree's shape). The tree is the project an installed
	copy sits in (shape "installed") or an export's payload/ ("export"), from TREE_SHAPES; for a copy staged in
	any other folder both are None. The shape is read from the real path, so a start through an 8.3 name or a
	junction is judged as the folder it reaches."""
	hooks = os.path.realpath(unverbatim(hooks_dir or paths.HOOKS_DIR))
	parts = []
	d = hooks
	for _ in range(3):
		parts.insert(0, os.path.basename(d).lower())
		d = os.path.dirname(d)
	shape = {TREE_SHAPES[0]: "installed", TREE_SHAPES[1]: "export"}.get(tuple(parts))
	return hooks, (d if shape else None), shape


def protected_roots(hooks_dir=None):
	"""The folders the self-test must never write in when it uses the system temp folder: this package's own
	folder, and the tree it sits in when its parents have a known shape (package_tree(): the project it is
	installed in, or an export's payload/). A copy staged anywhere else protects only its own folder, never an
	arbitrary ancestor three levels up."""
	hooks, tree, _shape = package_tree(hooks_dir)
	return [hooks] + ([tree] if tree else [])


def scratch_roots(hooks_dir=None):
	"""The folders a --scratch folder must lie outside: this package's own folder always, the board
	(<project>/.claude/tickets) of the project it is installed in, and an export's whole payload/ (a staged copy
	stays unchanged). The rest of an installed project is allowed, for a project that keeps every write inside
	the repo."""
	hooks, tree, shape = package_tree(hooks_dir)
	roots = [hooks]
	if shape == "installed":
		roots.append(os.path.join(tree, ".claude", "tickets"))
	elif shape == "export":
		roots.append(tree)
	return roots


def board_shaped(path):
	"""True when `path`'s real path runs through a folder shaped like a board or a hooks package (BOARD_SHAPES),
	in any project, so that a staged copy, which knows no project, never puts a --scratch folder in one either."""
	segs = [s.lower() for s in canonical(path).replace("\\", "/").split("/")]
	for shape in BOARD_SHAPES:
		n = len(shape)
		if any(tuple(segs[i:i + n]) == shape for i in range(len(segs) - n + 1)):
			return True
	return False


def project_folder(path, hooks_dir=None):
	"""Why `path` is no --scratch folder of its own, or None: it is a project root (the project this package is
	installed in, or any folder holding a .claude folder) or a .claude folder itself. Only the folder itself counts:
	its subfolders, such as .claude/scratch/<role>/<task>, are fine."""
	_hooks, tree, shape = package_tree(hooks_dir)
	real = canonical(path)
	if os.path.basename(real) == ".claude":
		return "is a .claude folder itself"
	if (shape == "installed" and real == canonical(tree)) or os.path.isdir(os.path.join(real_plain(path), ".claude")):
		return "is a project root"
	return None


def guarded_roots():
	"""The protected folders in effect: scratch_roots() with --scratch, else protected_roots()."""
	return scratch_roots() if EXPLICIT else protected_roots()


def outside_package(path):
	"""True when `path` lies outside every guarded_roots() folder, and with --scratch in no board-shaped folder."""
	if any(inside(path, root) for root in guarded_roots()):
		return False
	return not (EXPLICIT and board_shaped(path))


def hint():
	"""The way out a refusal names."""
	if EXPLICIT:
		return "pass a writable --scratch folder"
	return "point TMP at a writable folder, or pass --scratch <dir>"


def temp_candidates():
	"""[(source, folder)]: the folders tempfile.gettempdir() tries, in its order, none of them tried (trying one
	writes a probe file in it): tempfile.tempdir alone when it is set; else TMPDIR, TEMP, TMP, the platform's
	fallbacks and the working directory, from tempfile's own list when this Python has one, else rebuilt the same
	way. `source` names where each came from, for the refusal message."""
	if tempfile.tempdir is not None:
		return [("tempfile.tempdir", os.fsdecode(tempfile.tempdir))]
	dirs = None
	lister = getattr(tempfile, "_candidate_tempdir_list", None)
	if callable(lister):
		try:
			dirs = [os.fsdecode(d) for d in lister()]
		except Exception:
			dirs = None
	if dirs is None:
		dirs = [os.environ[name] for name in TEMP_VARS if os.environ.get(name)]
		if os.name == "nt":
			dirs += [os.path.expanduser(r"~\AppData\Local\Temp"), os.path.expandvars(r"%SYSTEMROOT%\Temp"),
					 r"c:\temp", r"c:\tmp", r"\temp", r"\tmp"]
		else:
			dirs += ["/tmp", "/var/tmp", "/usr/tmp"]
		try:
			dirs.append(os.getcwd())
		except OSError:
			dirs.append(os.curdir)
	try:
		cwd = os.getcwd()
	except OSError:
		cwd = None
	out = []
	for d in dirs:
		source = next((name for name in TEMP_VARS if os.environ.get(name) == d), None)
		if source is None:
			source = "the working directory" if d in (cwd, os.curdir) else "a fallback"
		out.append((source, d))
	return out


def temp_bases(candidates=None, roots=None):
	"""Yields, in order, the real path of each candidate (temp_candidates()) that is an existing folder, skipping
	the others as tempfile does. Raises ScratchRefused at the first existing one that lies inside a protected
	folder (`roots`, by default protected_roots()), never skipping on to the next, so a TMP that points into the
	package or its project is refused rather than quietly replaced. It only reads (real paths, is-a-folder):
	nothing is written and tempfile.gettempdir() is never called, so a refused folder never sees a file."""
	guard = None
	for source, folder in (temp_candidates() if candidates is None else candidates):
		if not folder:
			continue
		real = real_plain(folder)
		if not os.path.isdir(real):
			continue
		if guard is None:
			guard = protected_roots() if roots is None else roots
		for root in guard:
			if inside(real, root):
				raise ScratchRefused("the temp folder %s (from %s) lies inside %s; point TMPDIR, TEMP and TMP "
									 "elsewhere, or pass --scratch <dir>" % (ascii_path(real), source, ascii_path(root)))
		yield real


def temp_base(roots=None):
	"""The first of temp_bases(): the system temp folder as a plain real path, found without writing anything.
	Raises ScratchRefused when it lies inside a protected folder, or when no candidate is a folder."""
	for base in temp_bases(roots=roots):
		return base
	raise ScratchRefused("%s; %s" % (NO_TEMP, hint()))


def explicit_base(raw, hooks_dir=None):
	"""The folder given with --scratch, as a plain real path, checked before anything is written: an existing
	folder outside every scratch_roots() folder, in no board-shaped folder, and neither a project root nor a .claude
	folder itself (project_folder()). A relative path is taken from the
	working directory, an MSYS path (/c/...) as its drive path. A link or a junction, on the way or as the folder
	itself, is followed: every check, every scratch folder and the guarded removal use the real path it reaches,
	so what is checked is where the writes land. Raises ScratchRefused otherwise. The system temp folder is not
	looked at."""
	text = "" if raw is None else str(raw)
	if not text:
		raise ScratchRefused("--scratch needs a folder")
	given = paths.msys_to_windows(text)
	real = real_plain(given)
	for root in scratch_roots(hooks_dir):
		if inside(real, root):
			raise ScratchRefused("the --scratch folder %s lies inside %s; pick one outside the hooks package and "
								 ".claude/tickets" % (ascii_path(given), ascii_path(root)))
	if board_shaped(real):
		raise ScratchRefused("the --scratch folder %s lies in a board or a hooks package (%s); pick another folder"
							 % (ascii_path(given), ascii_path(real)))
	why = project_folder(real, hooks_dir)
	if why:
		raise ScratchRefused("the --scratch folder %s %s, where a killed run's %s* folder would stay with nothing "
							 "ignoring it; pick a folder under it, e.g. .claude/scratch/<role>/<task>"
							 % (ascii_path(given), why, SCRATCH_PREFIX))
	if not os.path.isdir(real):
		raise ScratchRefused("the --scratch folder %s is missing or not a folder; create it first" % ascii_path(given))
	return real


def use_scratch(raw):
	"""Makes the folder given with --scratch (explicit_base()) the parent of every scratch folder, instead of the
	system temp folder. Raises ScratchRefused, before anything is written, when it is not acceptable."""
	global EXPLICIT
	EXPLICIT = explicit_base(raw)
	return EXPLICIT


def scratch_base():
	"""The parent of every scratch folder as a plain real path, found without writing anything: the --scratch
	folder when one was given (use_scratch()), else the system temp folder (temp_base())."""
	return EXPLICIT or temp_base()


def new_folder(base):
	"""A new, empty tickets-selftest-<random> folder directly in `base`: one os.mkdir per try, at most MKDIR_TRIES
	tries, and a further try only when the name already exists. Any other OSError means `base` cannot hold a
	folder and is raised at once. Not tempfile.mkdtemp(): on Windows it retries a PermissionError for os.TMP_MAX
	names, which never ends in a folder whose ACL denies creating one."""
	clash = None
	for _ in range(MKDIR_TRIES):
		path = os.path.join(base, SCRATCH_PREFIX + os.urandom(6).hex())
		try:
			os.mkdir(path, 0o700)
			return path
		except FileExistsError as exc:
			clash = exc
	raise clash


def make_scratch(roots=None):
	"""(base, a new tickets-selftest-* folder directly in it), from new_folder(). With --scratch only that folder
	is tried. Otherwise each temp_bases() folder in turn (`roots` as there), as tempfile.gettempdir() tries them:
	one that cannot hold a folder is skipped after one try, and the first existing one inside a protected folder
	refuses before anything is made. Raises ScratchRefused when no folder can be made."""
	bases = [EXPLICIT] if EXPLICIT else temp_bases(roots=roots)
	first = None
	for base in bases:
		try:
			return base, new_folder(base)
		except (OSError, ValueError) as exc:
			first = first or (base, exc)
	if first is None:
		raise ScratchRefused("%s; %s" % (NO_TEMP, hint()))
	raise ScratchRefused("cannot create a scratch folder in %s (%s); %s"
						 % (ascii_path(first[0]), type(first[1]).__name__, hint()))


@contextmanager
def scratch_root():
	"""A fresh directory tickets-selftest-* directly under the scratch base (the --scratch folder, else the system
	temp folder), removed afterwards even when a check fails or raises. Nothing is written in a protected folder:
	the base is checked before the folder is made in it. Raises ScratchRefused when no safe base is usable."""
	base, tmp = make_scratch()
	try:
		yield tmp
	finally:
		remove_scratch(tmp, base)


def preflight():
	"""Proves the scratch base usable before any case runs: one scratch folder with a nested file, removed.
	Raises ScratchRefused when it is not."""
	with scratch_root() as tmp:
		try:
			write_text(os.path.join(tmp, "a", "b", "c.txt"), "x")
		except (OSError, ValueError) as exc:
			raise ScratchRefused("cannot write in a scratch folder under %s (%s); %s"
								 % (ascii_path(os.path.dirname(tmp)), type(exc).__name__, hint()))


def decline_reason(tmp, base):
	"""Why remove_scratch() must not delete `tmp`, or None when it may: `tmp` must be a real directory (not a
	link or a junction) named tickets-selftest-* directly under `base`, and outside every protected folder
	(outside_package())."""
	is_junction = getattr(os.path, "isjunction", None)
	if canonical(os.path.dirname(tmp)) != canonical(base):
		return "not directly under the scratch base"
	if not os.path.basename(tmp).startswith(SCRATCH_PREFIX):
		return "not a %s* folder" % SCRATCH_PREFIX
	if not outside_package(tmp):
		return "inside a protected folder"
	if os.path.islink(tmp) or (is_junction is not None and is_junction(tmp)):
		return "a link, not a folder"
	if not os.path.isdir(tmp):
		return "not a folder"
	return None


def remove_scratch(tmp, base):
	"""Deletes `tmp`, the folder scratch_root() created, and nothing else (decline_reason()). Whenever it leaves
	the folder, declined or not removable (a file still held open), it names it on stderr; the folder stays in
	the scratch base (never in a protected folder). Returns True when `tmp` is gone."""
	if not os.path.lexists(tmp):
		return True
	why = decline_reason(tmp, base)
	if why is None:
		shutil.rmtree(tmp, ignore_errors=True)
		if not os.path.lexists(tmp):
			return True
		why = "could not remove it (a file still held open?)"
	sys.stderr.write("self-test: left %s: %s\n" % (ascii_path(tmp), why))
	return False


def write_stub_project(root, port, service, config=None, tool="tools/tickets"):
	"""A minimal 1.0.0-shape project at `root`: <tool>/tickets.py and a serve.py carrying the three constants,
	and optionally a .claude/tickets/config.json."""
	write_text(os.path.join(root, tool, "tickets.py"), '"""stub CLI"""\n')
	write_text(os.path.join(root, tool, "serve.py"), SERVE_STUB_100 % (port, service))
	if config is not None:
		write_config(root, config)


def write_stub_project_110(root, config, tool="src/tools/tickets"):
	"""A minimal 1.1.0-shape project: <tool>/tickets.py, a serve.py with no port or marker constant, and the
	config.json that carries them."""
	write_text(os.path.join(root, tool, "tickets.py"), '"""stub CLI"""\n')
	write_text(os.path.join(root, tool, "serve.py"), SERVE_STUB_110)
	write_config(root, config)


@contextmanager
def http_server(body, status=200):
	"""A loopback HTTP server answering every GET with `body` (JSON-encoded unless bytes); yields its port."""
	payload = body if isinstance(body, bytes) else json.dumps(body).encode("ascii")

	class Handler(BaseHTTPRequestHandler):
		def do_GET(self):
			self.send_response(status)
			self.send_header("Content-Type", "application/json")
			self.send_header("Content-Length", str(len(payload)))
			self.end_headers()
			self.wfile.write(payload)

		def log_message(self, *_args):
			pass

	srv = HTTPServer(("127.0.0.1", 0), Handler)
	thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
	thread.start()
	try:
		yield srv.server_address[1]
	finally:
		srv.shutdown()
		srv.server_close()


@contextmanager
def silent_listener():
	"""A loopback socket that accepts connections and never answers; yields its port."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.bind(("127.0.0.1", 0))
	sock.listen(8)
	try:
		yield sock.getsockname()[1]
	finally:
		sock.close()


def closed_port():
	"""A loopback port that was free a moment ago (bound, then released)."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.bind(("127.0.0.1", 0))
	port = sock.getsockname()[1]
	sock.close()
	return port
