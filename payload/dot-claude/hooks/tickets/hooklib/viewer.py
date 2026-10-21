"""The project's ticket viewer: where it listens and how it identifies itself, read from the project (never
hard-coded, so this works unchanged in any project carrying the ticket system), and the health probe.

Config, first source wins per value:
	.claude/tickets/config.json   viewer_port, viewer_service (the ticket system's keys), and the hook-only
								  overrides viewer_health_path, viewer_script, viewer_pid_file
	<viewer_script>               only as a fallback for a 1.0.0 copy, whose serve.py still carries
								  module-level `default_port = N`, `service_marker = "..."`,
								  `health_path = "..."`. Default: serve.py in the tool's folder
								  (project.tool_dir), else tools/tickets/serve.py
	store_name                    the service marker's default, as serve.py derives it
								  ("My Board" -> "my-board-tickets")
	<viewer_pid_file>             default build/tickets/serve.pid, JSON {pid, port, ...} written by a running
								  viewer (serve.py records it for detached and --foreground runs alike)
No port or no service marker -> None: this project has no viewer to check, and the rule stays silent.

Ports probed, in order, each at most once: the pid file's port (the one actually in use, e.g. after
`--port N`), then the configured port. A stale pid file therefore costs one extra timeout, never a false
"down" while the viewer runs on its configured port.

The probe is one GET on 127.0.0.1 through http.client (no proxy lookup, unlike urllib; imported lazily -
about 100 ms - so a prompt with no quiet spell never pays for it), with a hard timeout, reading at most
PROBE_READ_MAX bytes. It never starts, stops or signals anything."""
import json
import os
import re
import time

from hooklib import jsonfile
from hooklib import project

DEFAULT_SCRIPT_REL = "tools/tickets/serve.py"
SCRIPT_NAME = "serve.py"
DEFAULT_PID_REL = "build/tickets/serve.pid"
DEFAULT_HEALTH_PATH = "/api/health"
PROBE_HOST = "127.0.0.1"
PROBE_TIMEOUT_S = 0.3  # the viewer answers in single-digit ms locally; a hook must stay well under 1 s
PROBE_READ_MAX = 4096
SCRIPT_READ_MAX = 256 * 1024
PID_READ_MAX = 4096

UP = "up"            # answered with our service marker
DOWN = "down"        # no answer: refused, timed out, or not HTTP
FOREIGN = "foreign"  # something answered, but not our viewer (serve.py refuses to start over it)

PORT_RE = re.compile(r"^default_port\s*=\s*(\d{1,5})\s*(?:#.*)?$", re.M)
SERVICE_RE = re.compile(r"^service_marker\s*=\s*[\"']([^\"'\r\n]+)[\"']", re.M)
HEALTH_RE = re.compile(r"^health_path\s*=\s*[\"'](/[^\"'\r\n]*)[\"']", re.M)


def valid_port(value):
	return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536


def parse_serve_text(text):
	"""{port, service, health_path} found in a viewer script's module-level constants (missing keys absent)."""
	found = {}
	m = PORT_RE.search(text or "")
	if m and valid_port(int(m.group(1))):
		found["port"] = int(m.group(1))
	m = SERVICE_RE.search(text or "")
	if m:
		found["service"] = m.group(1)
	m = HEALTH_RE.search(text or "")
	if m:
		found["health_path"] = m.group(1)
	return found


def pid_file_port(root, rel=DEFAULT_PID_REL):
	"""The port a running viewer recorded in its pid file, or None (no file, unreadable, no valid port)."""
	rec = jsonfile.load(os.path.join(root, rel), PID_READ_MAX)
	port = rec.get("port") if isinstance(rec, dict) else None
	return port if valid_port(port) else None


def script_rel(root, raw):
	"""The viewer script, relative to the root: config viewer_script, else serve.py in the tool's folder."""
	if isinstance(raw.get("viewer_script"), str) and raw["viewer_script"].strip():
		return raw["viewer_script"].strip()
	tool = project.tool_dir(root, raw)[0]
	return tool + "/" + SCRIPT_NAME if tool else DEFAULT_SCRIPT_REL


def load_config(root):
	"""{port, ports, service, health_path, script, source} for the project at `root`, or None if it has
	no viewer. `port` is the configured port; `ports` the ones to probe, pid-file port first; `source` the
	'+'-joined sources used (config, script, store_name, pidfile)."""
	raw = project.read_config(root)
	cfg, sources = {}, []
	if valid_port(raw.get("viewer_port")):
		cfg["port"] = raw["viewer_port"]
	if isinstance(raw.get("viewer_service"), str) and raw["viewer_service"].strip():
		cfg["service"] = raw["viewer_service"]  # as serve.py uses it: not stripped
	if isinstance(raw.get("viewer_health_path"), str) and raw["viewer_health_path"].startswith("/"):
		cfg["health_path"] = raw["viewer_health_path"]
	if cfg:
		sources.append("config")
	script = script_rel(root, raw)
	pid_rel = raw.get("viewer_pid_file") if isinstance(raw.get("viewer_pid_file"), str) else DEFAULT_PID_REL
	if not ("port" in cfg and "service" in cfg and "health_path" in cfg):
		try:
			with open(os.path.join(root, script), encoding="utf-8", errors="replace") as fh:
				parsed = parse_serve_text(fh.read(SCRIPT_READ_MAX))
		except (OSError, ValueError):
			parsed = {}
		filled = [key for key in parsed if key not in cfg]
		for key in filled:
			cfg[key] = parsed[key]
		if filled:
			sources.append("script")
	if "service" not in cfg:
		derived = project.service_from_store_name(raw.get("store_name"))
		if derived:
			cfg["service"] = derived
			sources.append("store_name")
	if "port" not in cfg or "service" not in cfg:
		return None
	running = pid_file_port(root, pid_rel)
	cfg["ports"] = [running, cfg["port"]] if running and running != cfg["port"] else [cfg["port"]]
	if running:
		sources.append("pidfile")
	cfg.setdefault("health_path", DEFAULT_HEALTH_PATH)
	cfg["script"] = script.replace("\\", "/")
	cfg["source"] = "+".join(sources)
	return cfg


def probe(port, service, health_path=DEFAULT_HEALTH_PATH, timeout=PROBE_TIMEOUT_S):
	"""(UP | DOWN | FOREIGN, elapsed ms). Never raises."""
	started = time.perf_counter()
	state = DOWN
	conn = None
	try:
		import http.client  # lazy: only a quiet-spell prompt probes
		conn = http.client.HTTPConnection(PROBE_HOST, port, timeout=timeout)
		conn.request("GET", health_path, headers={"Connection": "close", "Accept": "application/json"})
		resp = conn.getresponse()
		body = resp.read(PROBE_READ_MAX)
		state = FOREIGN
		try:
			value = json.loads(body.decode("utf-8", "replace"))
		except (ValueError, RecursionError):
			value = None
		if resp.status == 200 and isinstance(value, dict) and value.get("service") == service:
			state = UP
	except Exception:
		state = DOWN
	finally:
		try:
			if conn is not None:
				conn.close()
		except Exception:
			pass
	return state, int(round((time.perf_counter() - started) * 1000))


def check(cfg, timeout=PROBE_TIMEOUT_S):
	"""(state, total ms, port) over cfg["ports"] in order: the first port that is UP wins; otherwise the
	first port's state (FOREIGN beats DOWN, so a squatter on the port is reported)."""
	total = 0
	states = []
	for port in cfg.get("ports") or [cfg["port"]]:
		state, ms = probe(port, cfg["service"], cfg["health_path"], timeout)
		total += ms
		if state == UP:
			return UP, total, port
		states.append((state, port))
	for state, port in states:
		if state == FOREIGN:
			return FOREIGN, total, port
	return states[0][0], total, states[0][1]


def health_url(cfg, port=None):
	return "http://%s:%d%s" % (PROBE_HOST, cfg["port"] if port is None else port, cfg["health_path"])
