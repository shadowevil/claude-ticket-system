"""Reading a JSON file the hooks do not own (config, tickets, the viewer's pid file, the prompt clock): at most
`max_bytes`, UTF-8 with or without a BOM (utf-8-sig, as tickets.py reads config.json), and never an
exception. A missing, unreadable, truncated, malformed or pathologically nested file (RecursionError) reads
as None, so one bad file costs its own value and never the whole rule."""
import json

READ_MAX = 256 * 1024


def load(path, max_bytes=READ_MAX):
	"""The parsed value of the JSON file at `path`, or None."""
	try:
		with open(path, encoding="utf-8-sig") as fh:
			return json.loads(fh.read(max_bytes))
	except (OSError, ValueError, RecursionError, MemoryError):
		return None


def load_dict(path, max_bytes=READ_MAX):
	"""The file's value when it is a JSON object, else {}."""
	value = load(path, max_bytes)
	return value if isinstance(value, dict) else {}
