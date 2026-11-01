"""Release tooling for the ticket system: manifests, the pre-release check, and version identification.

    python ticket-system/tools/release.py manifest         record releases/<VERSION>.json from payload/
    python ticket-system/tools/release.py check            payload, VERSION, CHANGELOG and manifest agree,
                                                           the bump level fits the JSON structure change, and
                                                           BACKLOG.md's open items are listed (WARN)
    python ticket-system/tools/release.py check --release  the same, but open BACKLOG.md items FAIL (run it to release)
    python ticket-system/tools/release.py identify <repo>  which release an installed copy matches, file by file;
                                                           the CLI is found by --cli-dir, else the repo's
                                                           .claude/tickets/config.json tool_dir (a relative
                                                           folder inside the repo holding tickets.py), else
                                                           src/tools/tickets or tools/tickets
    python ticket-system/tools/release.py export <x.y.z> <folder>  extract a tagged release for installing
    python ticket-system/tools/release.py merge-doc <release-doc> <project-doc> --base <old-release-doc> --out <file>
                                                           the release's rules doc with the project's values,
                                                           free-text lines, project blocks and (with --base) edits
                                                           kept; a project line it drops that is not the base's
                                                           wording is listed (exit 2), never dropped silently

Every file is hashed several ways:
  raw       - the exact bytes; `check` compares it, so a manifest proves byte identity with payload/;
  exact     - the bytes after CRLF -> LF (a Windows checkout with autocrlf still matches);
  loose     - also with all-tab leading indentation expanded to 4 spaces per tab and trailing spaces and
              tabs dropped on every line (a copy re-indented from tabs to spaces still matches; any other
              change, a line indented with a mix of tabs and spaces included, does not);
  and, for the skill, exact and loose again without the table rows of its "## Settings" section,
  which hold the per-project values. `identify` uses exact, loose and the Settings pair, never raw.

How loose and the Settings pair are computed is versioned: a manifest records its "normalize" scheme, and
one without it (1.0.0) used scheme 1. The scheme also fixes the files' kinds (from scheme 2 the icons are
adapted, since each project bakes its own). `identify` and `check` hash with the scheme the manifest records, so
a released manifest never has to be rewritten when the scheme improves.

Stdlib only; ASCII console output.
"""

import argparse
import difflib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile

tool_dir = os.path.dirname(os.path.abspath(__file__))
system_dir = os.path.dirname(tool_dir)
repo_root = os.path.dirname(system_dir)
payload_dir = os.path.join(system_dir, "payload")
releases_dir = os.path.join(system_dir, "releases")
version_path = os.path.join(system_dir, "VERSION")
changelog_path = os.path.join(system_dir, "CHANGELOG.md")
backlog_path = os.path.join(system_dir, "BACKLOG.md")

version_pattern = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
skill_payload_path = "dot-claude/skills/tickets/SKILL.md"
settings_title = "## Settings (per project)"
binary_suffixes = (".png",)

# How an installed copy is expected to relate to each payload file.
#   product  - installed unchanged; any difference is a local edit.
#   skill    - installed unchanged except its Settings table.
#   adapted  - a starting point every project edits (its config, tags, schema enums, rules doc).
#   optional - product that a project may leave out (the hooks); compared like product when installed.
kinds = ("product", "skill", "adapted", "optional")
adapted_files = {
	"dot-claude/tickets/config.json",
	"dot-claude/tickets/tags.json",
	"dot-claude/tickets/ticket.schema.json",
	"dot-claude/docs/tickets.md",
	# Shipped in 1.0.0 only (B14 took it out); kept so kind_of still rebuilds 1.0.0's manifest exactly.
	"dot-claude/docs/portable_workflow.md",
}
optional_prefix = "dot-claude/hooks/tickets/"
# The viewer's icons. From 1.1.0 every project bakes its own with make_icons.py (from its config), so a manifest of
# normalize scheme 2 or later records them as adapted (B22). 1.0.0's manifest (scheme 1) recorded them as product
# and still rebuilds that way; identify reports them there as unverified (adapted_in_1_0_0), as before.
baked_prefix = "src/tools/tickets/icons/"
# 1.0.0 predates config-driven settings: these product files carry per-project edits (brand, id regexes,
# port, service marker, repo depth, library paths) in every adopter's copy. A hash cannot tell those
# required edits from a local change, so `identify` reports such a file as `unverified`, never as a match.
adapted_in_1_0_0 = {
	"src/tools/tickets/tickets.py",
	"src/tools/tickets/serve.py",
	"src/tools/tickets/app.js",
	"src/tools/tickets/index.html",
	"src/tools/tickets/style.css",
	"src/tools/tickets/manifest.webmanifest",
	"src/tools/tickets/make_icons.py",
	"src/tools/tickets/icons/apple-touch-icon.png",
	"src/tools/tickets/icons/icon-192.png",
	"src/tools/tickets/icons/icon-512.png",
	"external/marked/refresh.md",
	"external/dompurify/refresh.md",
}
# Per release, the product files adopting it required editing. Only 1.0.0 has any: later releases are
# config-driven, so a release not listed here required none.
required_edits = {"1.0.0": adapted_in_1_0_0}
cli_dir_candidates = ["src/tools/tickets", "tools/tickets"]
# identify reads the CLI's folder from the adopter's config.json key tool_dir before the candidates above (B32),
# vetted as check_tool_dir says. The board is never the tool's folder (the hooks ignore such a tool_dir too).
config_rel = os.path.join(".claude", "tickets", "config.json")
config_read_max = 256 * 1024
board_rel = ".claude/tickets"
# 1.0.0 serves marked and DOMPurify from <repo>/external/; some adopters moved them next to the CLI
# (serve.py's two /lib/ routes edited), so those folders are looked in too.
vendored_fallbacks = ["lib", "vendor"]
# A manifest with files under src/tools/tickets/lib/ ships them in <CLI_DIR>/lib/; a copy not yet moved still
# has them in <repo>/external/ (or <CLI_DIR>/vendor/). The lookup goes by path, never by version.
cli_lib_prefix = "src/tools/tickets/lib/"

# The normalize scheme a new manifest records; a manifest without the key used scheme 1.
normalize_scheme = 2
normalize_schemes = (1, 2)

fence_pattern = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# "## Settings", "## Settings (per project)", "## Settings:" - not "## Settingsfoo".
settings_heading = re.compile(r"^## Settings(?![0-9A-Za-z_])")
# A Markdown table row: a "|" after at most 3 spaces (4 or more, or a tab, make it code).
table_row = re.compile(r"^ {0,3}\|")

# Names Windows treats as devices, with any extension ("CON.txt" is CON too).
windows_devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
# COM and LPT with 0-9 or a superscript 1-3 (Windows reserves those too).
windows_devices |= {prefix + digit for prefix in ("COM", "LPT") for digit in list("0123456789") + [chr(0xb9), chr(0xb2), chr(0xb3)]}
windows_forbidden = set('<>:"/\\|?*')
short_name_pattern = re.compile(r"~[0-9]")
# Control characters a note writes out as \xNN (CR, LF and tab are written \r, \n, \t first).
control_pattern = re.compile(r"[\x00-\x1f\x7f]")

# The version gate (B19). Its structure set is the store folder's JSON files (config, tags, schema); a bump is
# minor when their structure changes, patch otherwise (user rule, 2026-09-30; README "Versioning").
structure_prefix = "dot-claude/tickets/"
# JSON files that hold a map of tags: a new tag is data, a key every tag carries is structure. Format 1 (to 1.2.2)
# is a name -> object map at the root; format 2 (1.3.0 on) is {"format", "next_id", "tags": {id: object}}, where
# only the "tags" map collapses (see map_collapse).
map_root_files = ("tags.json",)
# Schema keywords whose value is structure (in *.schema.json); title and description text is data.
schema_value_keys = frozenset(("type", "$ref", "pattern", "format", "const", "additionalProperties", "minLength",
	"maxLength", "minimum", "maximum", "minItems", "maxItems"))
schema_skip_keys = frozenset(("title", "description", "$comment", "examples"))
# A list of scalars under one of these keys records its sorted members ("status" gaining "in_review").
member_list_keys = ("enum", "required")
# How many changes one file lists before "...".
shown_changes = 6
# A CHANGELOG.md line naming a structure change no file comparison sees (the viewer API's JSON): "Structure: ...",
# "- Structure: ..." or "**Structure:** ...", with text after the colon.
structure_line = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?(?:\*\*)?Structure(?:\*\*)?:(?:\*\*)?[ \t]*\S")
# A "#" or "##" heading (not "###"): the end of a CHANGELOG entry or of BACKLOG.md's Open section.
top_heading = re.compile(r"^#{1,2}(?!#)\s")

# The open-items gate (B20): nothing ships while BACKLOG.md lists an open item (user rule, 2026-09-30).
open_heading = re.compile(r"^##\s+Open\b", re.I)
# A column-0 bullet starting with an item id ("- **B1. ..."); a struck-through one ("- ~~**B9 ...~~") is resolved.
backlog_item = re.compile(r"^[-*][ \t]+(?!~~)\**(?!~~)[ \t]*(B[0-9]+)\b")
# A column-0 line that looks like a list item: a "-", "*" or "+" marker, or a number with "." or ")", each followed
# by a space or tab (or ending the line); or a marker run straight into an id, the typo "-**B5**" / "-B5" (an
# emphasised paragraph such as "*Note:* ..." and a line such as "1.1.0 ships ..." are not list items). Under
# "## Open", one that backlog_item does not count is WARNed about.
list_like_line = re.compile(r"^(?:(?:[-*+]|[0-9]+[.)])(?:[ \t]|$)|[-*+]\*\*B[0-9]|[-+]B[0-9])")
# Not items: a thematic break ("---", "* * *"), and a struck-through item (resolved, like backlog_item's).
thematic_break = re.compile(r"^([-*_])(?:[ \t]*\1){2,}[ \t]*$")
struck_item = re.compile(r"^(?:[-*+]|[0-9]+[.)])[ \t]*\**[ \t]*~~")
# How much of an uncounted line its WARN quotes.
quoted_line_chars = 60


def read_version():
	with open(version_path, "r", encoding="utf-8") as handle:
		value = handle.read().strip()
	if not version_pattern.match(value):
		raise SystemExit("ERROR VERSION is not x.y.z: " + value)
	return value


def payload_files():
	found = []
	for root, dirs, files in os.walk(payload_dir):
		dirs[:] = sorted(name for name in dirs if name != "__pycache__")
		for name in sorted(files):
			path = os.path.join(root, name)
			found.append(os.path.relpath(path, payload_dir).replace(os.sep, "/"))
	return found


def kind_of(relative, scheme=normalize_scheme):
	"""A payload file's kind, as a manifest of the given normalize scheme records it (the scheme versions the
	classification too, so an older manifest always rebuilds exactly)."""
	if relative == skill_payload_path:
		return "skill"
	if relative in adapted_files:
		return "adapted"
	if scheme >= 2 and relative.startswith(baked_prefix):
		return "adapted"
	if relative.startswith(optional_prefix):
		return "optional"
	return "product"


def sha256(text_or_bytes):
	if isinstance(text_or_bytes, str):
		text_or_bytes = text_or_bytes.encode("utf-8")
	return hashlib.sha256(text_or_bytes).hexdigest()


def to_text(data):
	"""A text file's content with CRLF line endings made LF."""
	return data.decode("utf-8", "replace").replace("\r\n", "\n")


def normalize_v1(text):
	"""Scheme 1 (1.0.0): per line, tabs in the leading indentation become 4 spaces and trailing whitespace
	(str.rstrip, so NBSP and form feed too) goes. Kept only to compare against 1.0.0's stored hashes."""
	lines = []
	for line in text.split("\n"):
		body = line.lstrip(" \t")
		indent = line[:len(line) - len(body)]
		lines.append((indent.expandtabs(4) + body).rstrip())
	return "\n".join(lines)


def normalize_v2(text):
	"""Scheme 2: per line, leading indentation made only of tabs becomes 4 spaces per tab, and trailing spaces
	and tabs go. Indentation mixing tabs and spaces stays as it is, so a line re-indented halfway (which Python
	may reject) does not match its tab-indented original. Every other character stays."""
	lines = []
	for line in text.split("\n"):
		body = line.lstrip("\t")
		tabs = len(line) - len(body)
		if tabs and not body.startswith(" "):
			line = "    " * tabs + body
		lines.append(line.rstrip(" \t"))
	return "\n".join(lines)


def normalize(text, scheme=normalize_scheme):
	"""Whitespace that carries no meaning, removed, by the given scheme (see normalize_v1 and normalize_v2)."""
	if scheme == 1:
		return normalize_v1(text)
	return normalize_v2(text)


def strip_settings_rows_v1(text):
	"""Scheme 1 (1.0.0) of strip_settings_rows: no code-fence awareness, "## Settings" as a plain prefix,
	and only rows starting in column 1. Kept only to compare against 1.0.0's stored hashes."""
	lines = text.split("\n")
	start = None
	for index, line in enumerate(lines):
		if line.rstrip() == settings_title:
			start = index
			break
	if start is None:
		for index, line in enumerate(lines):
			if line.startswith("## Settings"):
				start = index
				break
	if start is None:
		return text
	end = len(lines)
	for index in range(start + 1, len(lines)):
		if lines[index].startswith("# ") or lines[index].startswith("## "):
			end = index
			break
	section = [line for line in lines[start + 1:end] if not line.startswith("|")]
	return "\n".join(lines[:start + 1] + section + lines[end:])


def fenced_lines(lines):
	"""Per line, True when it is part of a fenced code block (``` or ~~~), its fence lines included. A fence
	left open runs to the end, as in CommonMark."""
	flags = []
	opener = None
	for line in lines:
		match = fence_pattern.match(line)
		if opener is None:
			# A backtick fence's info string cannot hold a backtick; such a line is inline code, not a fence.
			if match and not (match.group(1)[0] == "`" and "`" in line[match.end():]):
				opener = match.group(1)
				flags.append(True)
			else:
				flags.append(False)
		else:
			flags.append(True)
			if (match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener)
					and not line[match.end():].strip(" \t")):
				opener = None
	return flags


def strip_settings_rows_v2(text):
	"""Scheme 2: the skill without the table rows of its first Settings section.

	The section is the one headed exactly "## Settings (per project)", or failing that the first heading
	"## Settings" followed by the line's end or a character that is not a letter, digit or underscore
	("## Settingsfoo" is another section). It runs to the next "#" or "##" heading. Headings inside a fenced
	code block count for neither. A table row is a line whose first character after at most 3 spaces is "|",
	outside a code block. The section's prose and code, and any later "## Settings..." section, are kept, so
	a rule added there is still compared."""
	lines = text.split("\n")
	fenced = fenced_lines(lines)
	start = None
	for index, line in enumerate(lines):
		if not fenced[index] and line.rstrip(" \t") == settings_title:
			start = index
			break
	if start is None:
		for index, line in enumerate(lines):
			if not fenced[index] and settings_heading.match(line):
				start = index
				break
	if start is None:
		return text
	end = len(lines)
	for index in range(start + 1, len(lines)):
		if not fenced[index] and (lines[index].startswith("# ") or lines[index].startswith("## ")):
			end = index
			break
	section = [line for index, line in enumerate(lines[start + 1:end], start + 1)
		if fenced[index] or not table_row.match(line)]
	return "\n".join(lines[:start + 1] + section + lines[end:])


def strip_settings_rows(text, scheme=normalize_scheme):
	if scheme == 1:
		return strip_settings_rows_v1(text)
	return strip_settings_rows_v2(text)


def digests(data, relative, scheme=normalize_scheme):
	"""The raw, exact and loose hashes of one file's content (plus the Settings-free pair for the skill)."""
	raw = sha256(data)
	if relative.endswith(binary_suffixes):
		return {"raw": raw, "exact": raw, "loose": raw}
	text = to_text(data)
	result = {"raw": raw, "exact": sha256(text), "loose": sha256(normalize(text, scheme))}
	if relative == skill_payload_path:
		body = strip_settings_rows(text, scheme)
		result["exact_no_settings"] = sha256(body)
		result["loose_no_settings"] = sha256(normalize(body, scheme))
	return result


def read_json(path):
	with open(path, "r", encoding="utf-8") as handle:
		return json.load(handle)


def read_manifest(path):
	"""A release manifest, checked for the shape this tool relies on; exits with an ERROR line otherwise."""
	shown = os.path.relpath(path, system_dir).replace(os.sep, "/")
	try:
		value = read_json(path)
	except (ValueError, OSError) as error:
		raise SystemExit("ERROR {} is not a readable JSON manifest: {}: {}".format(shown, type(error).__name__, error))
	problem = None
	if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
		problem = "no \"files\" object"
	elif value.get("normalize", 1) not in normalize_schemes or isinstance(value.get("normalize"), bool):
		problem = "normalize scheme {!r} is unknown to this tool (it knows {}); use a newer release.py".format(
			value.get("normalize"), ", ".join(str(scheme) for scheme in normalize_schemes))
	else:
		for relative, entry in value["files"].items():
			if not isinstance(entry, dict) or entry.get("kind") not in kinds:
				problem = "entry {!r} has no known kind".format(relative)
			elif not all(isinstance(entry.get(key), str) for key in ("exact", "loose")):
				problem = "entry {!r} lacks its exact or loose hash".format(relative)
			if problem:
				break
	if problem:
		raise SystemExit("ERROR {} is not a valid manifest: {}".format(shown, problem))
	return value


def scheme_of(manifest):
	return manifest.get("normalize", 1)


def read_bytes(path):
	with open(path, "rb") as handle:
		return handle.read()


def build_manifest(version, scheme=normalize_scheme):
	files = {}
	for relative in payload_files():
		entry = {"kind": kind_of(relative, scheme)}
		entry.update(digests(read_bytes(os.path.join(payload_dir, relative)), relative, scheme))
		files[relative] = entry
	manifest = {"version": version, "files": files}
	if scheme != 1:
		manifest["normalize"] = scheme
	return manifest


def manifest_path(version):
	return os.path.join(releases_dir, version + ".json")


def write_json(path, value):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8", newline="\n") as handle:
		json.dump(value, handle, indent=2, sort_keys=True)
		handle.write("\n")


def run_git(where, arguments):
	try:
		return subprocess.run(["git", "-C", where] + list(arguments), capture_output=True)
	except OSError:
		return None


def git_layout():
	"""(the git work tree root, this release folder's path in it, '/'-ended or ''), asked of git once. In the
	maintainer's repository the release folder is its ticket-system/ folder: (repo root, "ticket-system/"). In a clone
	of the public repository it is the root: (clone, ""). Where git cannot tell (no git, no repository), the
	maintainer's layout is assumed, (repo_root, "ticket-system/"), and the git calls fail as they would there."""
	global git_layout_cache
	if git_layout_cache is None:
		found = run_git(system_dir, ["rev-parse", "--show-toplevel", "--show-prefix"])
		lines = found.stdout.decode("utf-8", "replace").splitlines() if found is not None and found.returncode == 0 else []
		if len(lines) == 2 and lines[0].strip():
			git_layout_cache = (os.path.normpath(lines[0].strip()), lines[1].strip())
		elif len(lines) == 1 and lines[0].strip():
			# git prints an empty prefix as an empty line, which splitlines() keeps only before a final newline.
			git_layout_cache = (os.path.normpath(lines[0].strip()), "")
		else:
			git_layout_cache = (repo_root, os.path.basename(system_dir) + "/")
	return git_layout_cache


git_layout_cache = None


def git(*arguments, where=None):
	"""Run git in this repo's work tree root (git_layout), or in the folder `where`; the CompletedProcess, or None when
	git cannot be started."""
	return run_git(where or git_layout()[0], arguments)


def command_manifest(args):
	version = read_version()
	path = manifest_path(version)
	if os.path.isfile(path) and not args.force:
		existing = read_manifest(path)
		if existing != build_manifest(version, scheme_of(existing)):
			print("ERROR {} exists and differs from payload/; a released version is never rewritten.".format(
				os.path.relpath(path, system_dir)))
			print("      Bump VERSION for a new release, or pass --force before the release is tagged.")
			return 1
		print("unchanged: {}".format(os.path.relpath(path, system_dir)))
		return 0
	if args.force:
		tag = "refs/tags/tickets-v" + version
		found = git("rev-parse", "-q", "--verify", tag)
		if found is None or found.returncode not in (0, 1):
			print("ERROR cannot check whether {} exists (git unavailable or not a repository); refusing --force.".format(tag))
			return 1
		if found.returncode == 0:
			print("ERROR {} exists: {} is released and is never rewritten. Bump VERSION instead.".format(
				tag, version))
			return 1
	write_json(path, build_manifest(version))
	print("wrote {} ({} files)".format(os.path.relpath(path, system_dir), len(payload_files())))
	return 0


def uncommitted_warnings():
	"""WARN lines when payload/ or releases/ differ from the commit: `check` reads the working tree, and a
	tag holds only what is committed."""
	system = git_layout()[1].rstrip("/") or "."
	found = git("status", "--porcelain", "--", git_layout()[1] + "payload", git_layout()[1] + "releases")
	if found is None or found.returncode != 0:
		return ["WARN cannot run git status; check compares the working tree, which may not be what is committed"]
	changed = [line for line in found.stdout.decode("ascii", "replace").splitlines() if line.strip()]
	if not changed:
		return []
	lines = ["WARN {} uncommitted change(s) under {}/payload or {}/releases; check compares the working tree, "
		"and a tag holds only what is committed:".format(len(changed), system, system)]
	lines += ["       " + line for line in changed]
	return lines


def version_tuple(value):
	return tuple(int(part) for part in value.split("."))


def bump_level(old, new):
	"""major | minor | patch for a bump from old to new (x.y.z strings), or None when new is not above old."""
	old, new = version_tuple(old), version_tuple(new)
	if new <= old:
		return None
	if new[0] != old[0]:
		return "major"
	if new[1] != old[1]:
		return "minor"
	return "patch"


def json_kind(value):
	if isinstance(value, bool):
		return "boolean"
	if isinstance(value, (int, float)):
		return "number"
	if value is None:
		return "null"
	return "string"


def scalar_list(value):
	return isinstance(value, list) and all(not isinstance(item, (dict, list)) for item in value)


def members_text(values):
	return ",".join(sorted(json.dumps(item, sort_keys=True) for item in values))


def walk_shape(value, path, collapse, value_keys, skip_keys, out):
	"""Adds the structure under `path` to `out` (path -> descriptor); see json_shape."""
	if isinstance(value, dict):
		out[path or "$"] = "object"
		if path in collapse:
			for child in value.values():
				walk_shape(child, (path + "." if path else "") + "*", collapse, value_keys, skip_keys, out)
			return
		for key, child in value.items():
			key = str(key)
			child_path = (path + "." if path else "") + key
			if key in skip_keys and not isinstance(child, dict):
				continue
			if key in value_keys and not isinstance(child, dict) and (scalar_list(child) or not isinstance(child, list)):
				out[child_path] = "=" + members_text(child if isinstance(child, list) else [child])
				continue
			walk_shape(child, child_path, collapse, value_keys, skip_keys, out)
	elif isinstance(value, list):
		out[path or "$"] = "array"
		if path.rsplit(".", 1)[-1] in member_list_keys and scalar_list(value):
			out[path + " (members)"] = members_text(value)
		for item in value:
			if isinstance(item, (dict, list)):
				walk_shape(item, path + "[]", collapse, value_keys, skip_keys, out)
	else:
		out[path or "$"] = json_kind(value)


def map_collapse(value):
	"""The paths of a tags.json whose keys are data: "tags" (the id map) for format 2 or later (a root dict whose
	"format" is an int, not a bool, >= 2), else the root (format 1, a name -> object map)."""
	fmt = value.get("format") if isinstance(value, dict) else None
	if isinstance(fmt, int) and not isinstance(fmt, bool) and fmt >= 2:
		return frozenset(("tags",))
	return frozenset(("",))


def json_shape(relative, data):
	"""The structure of one JSON file, without its data: {path: descriptor}. Paths are dotted key names, and
	an array adds "[]" for its element objects. A descriptor is the value's kind (object, array, string,
	number, boolean, null), except:
	  - in tags.json the tag map's keys are data, so every tag shares one path: "*" at the root in format 1,
	    "tags.*" in format 2 (a new tag is data, a key every tag carries is structure, and the root keys
	    "format" and "next_id" stay structure);
	  - in *.schema.json the constraint keywords (schema_value_keys: type, $ref, pattern, ...) record their
	    value, and title, description, $comment and examples text is skipped;
	  - a list of scalars under "enum" or "required" records its sorted members.
	Raises ValueError when the bytes are not UTF-8 JSON or nest too deeply to walk."""
	name = relative.rsplit("/", 1)[-1]
	try:
		value = json.loads(data.decode("utf-8"))
	except RecursionError:
		raise ValueError("nested too deeply to read")
	except ValueError as error:
		raise ValueError("not UTF-8 JSON: {}".format(error))
	schema = name.endswith(".schema.json")
	out = {}
	try:
		walk_shape(value, "", map_collapse(value) if name in map_root_files else frozenset(),
			schema_value_keys if schema else frozenset(), schema_skip_keys if schema else frozenset(), out)
	except RecursionError:
		raise ValueError("nested too deeply to compare")
	return out


def shape_diff(old, new):
	"""["+path", "-path", "~path"] for structure added, removed, or changed (kind, constraint or members)."""
	changes = []
	for path in sorted(set(old) | set(new)):
		if path not in old:
			changes.append("+" + path)
		elif path not in new:
			changes.append("-" + path)
		elif old[path] != new[path]:
			changes.append("~" + path)
	# Key names are data from the file; keep the console ASCII.
	return [change.encode("ascii", "backslashreplace").decode("ascii") for change in changes]


def structure_files(relatives):
	"""The paths in the version gate's structure set: dot-claude/tickets/*.json."""
	return {relative for relative in relatives if relative.startswith(structure_prefix)
		and "/" not in relative[len(structure_prefix):] and relative.endswith(".json")}


def structure_changes(previous, previous_files):
	"""How the structure set changed from release `previous` (its manifest's files) to payload/: a list of
	"<file>: +path ~path ...", "<file> added", "<file> removed" (empty: unchanged), and a list of (file, reason)
	for files that could not be compared."""
	changes = []
	unverified = []
	then = structure_files(previous_files)
	now = structure_files(payload_files())
	for relative in sorted(then | now):
		name = relative[len(structure_prefix):]
		if relative not in then:
			changes.append(name + " added")
			continue
		if relative not in now:
			changes.append(name + " removed")
			continue
		old = release_bytes(previous, relative, previous_files[relative])
		if old is None:
			unverified.append((name, "the {} copy is neither in payload/ nor at tag tickets-v{}".format(previous, previous)))
			continue
		try:
			old_shape = json_shape(relative, old)
		except ValueError as error:
			unverified.append((name, "the {} copy is {}".format(previous, error)))
			continue
		try:
			new_shape = json_shape(relative, read_bytes(os.path.join(payload_dir, relative)))
		except (ValueError, OSError) as error:
			unverified.append((name, "the payload/ copy is {}".format(error)))
			continue
		delta = shape_diff(old_shape, new_shape)
		if delta:
			more = " ..." if len(delta) > shown_changes else ""
			changes.append("{}: {}{}".format(name, " ".join(delta[:shown_changes]), more))
	return changes, unverified


def changelog_entry(text, version):
	"""The lines of CHANGELOG.md's entry for `version`, outside code fences: after its "## [x.y.z]" or
	"## x.y.z" heading, up to the next "#" or "##" heading. None when there is no such heading."""
	heading = re.compile(r"^## (?:\[" + re.escape(version) + r"\]|" + re.escape(version) + r"(?![0-9A-Za-z.\-]))")
	lines = text.split("\n")
	fenced = fenced_lines(lines)
	for index, line in enumerate(lines):
		if fenced[index] or not heading.match(line):
			continue
		entry = []
		for later in range(index + 1, len(lines)):
			if fenced[later]:
				continue
			if top_heading.match(lines[later]):
				break
			entry.append(lines[later])
		return entry
	return None


def recorded_versions():
	"""The versions releases/ holds a manifest for (files named x.y.z.json; anything else is ignored)."""
	if not os.path.isdir(releases_dir):
		return []
	return [name[:-5] for name in os.listdir(releases_dir)
		if name.endswith(".json") and version_pattern.match(name[:-5])]


def version_gate(version, changelog_text):
	"""B19: does VERSION's bump level fit the JSON structure change since the previous release (the highest
	recorded one below it)? Returns (problems, warnings, summary for the OK line)."""
	problems = []
	warnings = []
	others = [other for other in recorded_versions() if other != version]
	above = [other for other in others if version_tuple(other) >= version_tuple(version)]
	if above:
		highest = max(above, key=version_tuple)
		problems.append("version {} is not above the recorded release {} (releases/{}.json); a new release is "
			"numbered above every recorded one".format(version, highest, highest))
		return problems, warnings, ""
	if not others:
		return problems, warnings, " (first release: no earlier manifest, bump not checked)"
	previous = max(others, key=version_tuple)
	level = bump_level(previous, version)
	if level == "major":
		warnings.append("major bump {} -> {}: needs the user, docs/workflow.md sect. 7".format(previous, version))
		return problems, warnings, " (bump: major from {}, needs the user)".format(previous)
	try:
		previous_manifest = read_manifest(manifest_path(previous))
	except SystemExit as error:
		message = str(error)
		if message.startswith("ERROR "):
			message = message[len("ERROR "):]
		problems.append("cannot check the bump level against {}: {}".format(previous, message))
		return problems, warnings, ""
	changes, unverified = structure_changes(previous, previous_manifest["files"])
	for name, reason in unverified:
		warnings.append("cannot verify the structure of {} against {}: {}".format(name, previous, reason))
	listed = "; ".join(changes)
	if level == "patch":
		if changes:
			problems.append("version {} is a patch bump but the JSON structure changed since {} ({}); a structure "
				"change is a minor bump".format(version, previous, listed))
			return problems, warnings, ""
		if unverified:
			return problems, warnings, " (bump: patch from {}, structure not fully verified)".format(previous)
		return problems, warnings, " (bump: patch from {}, structure unchanged)".format(previous)
	if changes:
		return problems, warnings, " (bump: minor from {}, structure changed: {})".format(previous, listed)
	if unverified:
		return problems, warnings, " (bump: minor from {}, structure not fully verified)".format(previous)
	entry = changelog_entry(changelog_text, version) or []
	if any(structure_line.match(line) for line in entry):
		return problems, warnings, " (bump: minor from {}, structure change named by the CHANGELOG.md Structure: line)".format(
			previous)
	problems.append("version {} is a minor bump but no JSON structure changed since {}; a minor bump needs a structure "
		"change, or a line starting \"Structure:\" in its CHANGELOG.md entry naming one (such as the viewer API's JSON)"
		.format(version, previous))
	return problems, warnings, ""


def open_section(text):
	"""(seen, lines): whether BACKLOG.md has a "## Open" heading, and the (line number, line) pairs under it
	(every "###" subsection counts, up to the next "#" or "##" heading), headings and code fences left out."""
	found = []
	seen = False
	inside = False
	lines = text.split("\n")
	fenced = fenced_lines(lines)
	for index, line in enumerate(lines):
		if fenced[index]:
			continue
		if top_heading.match(line):
			inside = bool(open_heading.match(line))
			seen = seen or inside
			continue
		if inside:
			found.append((index + 1, line))
	return seen, found


def open_items(text):
	"""B20: the ids of the items BACKLOG.md lists under "## Open", in file order; None when it has no "## Open"
	heading. An item is a column-0 bullet starting with its id; a struck-through one, an indented sub-bullet, and
	anything in a code fence are not."""
	seen, found = open_section(text)
	if not seen:
		return None
	ids = []
	for _, line in found:
		match = backlog_item.match(line)
		if match:
			ids.append(match.group(1))
	return ids


def uncounted_open_lines(text):
	"""The (line number, line) pairs under "## Open" that look like a column-0 list item but that open_items does
	not count: a "+" bullet, a numbered item, a bullet without a B<n> id, "-**B11**" without the space. A thematic
	break and a struck-through item are not listed."""
	listed = []
	for number, line in open_section(text)[1]:
		line = line.rstrip("\r")
		if not list_like_line.match(line) or backlog_item.match(line):
			continue
		if thematic_break.match(line) or struck_item.match(line):
			continue
		listed.append((number, line))
	return listed


def quoted_line(line):
	"""A BACKLOG.md line as a WARN quotes it: ASCII only, cut at quoted_line_chars."""
	if len(line) > quoted_line_chars:
		line = line[:quoted_line_chars] + "..."
	return line.encode("ascii", "backslashreplace").decode("ascii")


def backlog_gate():
	"""(problem, warnings): why BACKLOG.md does not allow a release (open items, no Open section, unreadable), or
	None; and a warning for each line under Open that looks like an item but is not counted, in every mode."""
	try:
		with open(backlog_path, "r", encoding="utf-8") as handle:
			text = handle.read()
	except (OSError, ValueError) as error:
		return ("cannot read BACKLOG.md ({}); nothing ships until its Open section is known to be empty".format(
			type(error).__name__), [])
	warnings = ["BACKLOG.md line {} under \"## Open\" looks like a list item but is not counted as an open item "
		"(the gate counts a column-0 \"- \" or \"* \" bullet starting with its B<n> id); fix or strike it: {}".format(
		number, quoted_line(line)) for number, line in uncounted_open_lines(text)]
	ids = open_items(text)
	if ids is None:
		return "BACKLOG.md has no \"## Open\" section; nothing ships until it shows Open is empty", warnings
	if ids:
		return ("BACKLOG.md still lists {} open item(s): {}; nothing ships until Open is empty".format(
			len(ids), ", ".join(ids)), warnings)
	return None, warnings


def command_check(args):
	problems = []
	warnings = []
	version = read_version()
	path = manifest_path(version)
	if not os.path.isfile(path):
		problems.append("no manifest for {} (run: release.py manifest)".format(version))
	else:
		recorded = read_manifest(path)
		if recorded.get("version") != version:
			problems.append("releases/{}.json records version {!r}, VERSION says {}".format(
				version, recorded.get("version"), version))
		current = build_manifest(version, scheme_of(recorded))
		recorded_files = recorded["files"]
		for relative in sorted(set(recorded_files) | set(current["files"])):
			if relative not in current["files"]:
				problems.append("in manifest, missing from payload: " + relative)
			elif relative not in recorded_files:
				problems.append("in payload, missing from manifest: " + relative)
			elif "raw" not in recorded_files[relative]:
				problems.append("manifest has no raw-byte hash (rewrite it before tagging): " + relative)
			elif recorded_files[relative]["raw"] != current["files"][relative]["raw"]:
				problems.append("bytes changed since the manifest was written: " + relative)
			elif recorded_files[relative] != current["files"][relative]:
				problems.append("manifest entry out of date (kind or hashes): " + relative)
	# "## [1.0.0]" or "## 1.0.0", ending there: "## [1.0.01]" and "## 1.0.0.1" are other versions.
	heading = re.compile(r"^## (?:\[" + re.escape(version) + r"\]|" + re.escape(version) + r"(?![0-9A-Za-z.\-]))", re.M)
	with open(changelog_path, "r", encoding="utf-8") as handle:
		changelog_text = handle.read()
	if not heading.search(changelog_text):
		problems.append("CHANGELOG.md has no entry for " + version)
	pycache = [relative for relative in payload_files() if relative.endswith(".pyc")]
	problems += ["compiled file in payload: " + relative for relative in pycache]
	gate_problems, gate_warnings, bump = version_gate(version, changelog_text)
	problems += gate_problems
	warnings += gate_warnings
	releasing = getattr(args, "release", False)
	blocked, backlog_warnings = backlog_gate()
	warnings += backlog_warnings
	if blocked and releasing:
		problems.append(blocked)
	elif blocked:
		warnings.append(blocked + " (check --release fails on this)")
	for warning in uncommitted_warnings():
		print(warning)
	for warning in warnings:
		print("WARN " + warning)
	for problem in problems:
		print("FAIL " + problem)
	if problems:
		return 1
	print("OK: payload matches releases/{}.json byte for byte and CHANGELOG.md has its entry{}{}".format(
		version, bump, "; BACKLOG.md lists no open item" if releasing else ""))
	return 0


def installed_path(repo, cli_dir, relative):
	if relative.startswith("src/tools/tickets/"):
		path = os.path.join(repo, cli_dir, relative[len("src/tools/tickets/"):])
		if relative.startswith(cli_lib_prefix) and not os.path.isfile(path):
			# The libraries moved from <repo>/external/ into <CLI_DIR>/lib/; a copy not moved yet.
			inner = relative[len(cli_lib_prefix):]
			for candidate in (os.path.join(repo, "external", inner), os.path.join(repo, cli_dir, "vendor", inner)):
				if os.path.isfile(candidate):
					return candidate
		return path
	if relative.startswith("dot-claude/"):
		return os.path.join(repo, ".claude", relative[len("dot-claude/"):])
	path = os.path.join(repo, relative)
	if relative.startswith("external/") and not os.path.isfile(path):
		for folder in vendored_fallbacks:
			candidate = os.path.join(repo, cli_dir, folder, relative[len("external/"):])
			if os.path.isfile(candidate):
				return candidate
	return path


def shown_value(value):
	"""A config value as a note quotes it: on one line (CR, LF and tab written as \\r, \\n, \\t, any other control
	character as \\xNN), ASCII only, cut at quoted_line_chars."""
	value = value.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
	value = control_pattern.sub(lambda match: "\\x{:02x}".format(ord(match.group())), value)
	return quoted_line(value).replace("'", "\\'")


def read_config(repo):
	"""(config dict or None, why): the adopter's .claude/tickets/config.json, read as the hooks read it (UTF-8
	with or without a BOM, at most config_read_max characters), never raising."""
	path = os.path.join(repo, config_rel)
	if not os.path.isfile(path):
		return None, "not found"
	try:
		with open(path, "r", encoding="utf-8-sig") as handle:
			text = handle.read(config_read_max + 1)
		if len(text) > config_read_max:
			return None, "larger than {} KB".format(config_read_max // 1024)
		value = json.loads(text)
	except (OSError, ValueError, RecursionError, MemoryError) as error:
		return None, "not readable JSON ({})".format(type(error).__name__)
	if not isinstance(value, dict):
		return None, "not a JSON object"
	return value, None


def inside(path, root):
	"""`path` relative to `root` as a lower-case '/'-joined string ('' for the root itself), or None when it lies
	outside it. Both are compared as given, so pass real paths; case-insensitive, as the Windows filesystem is."""
	root = os.path.normcase(os.path.normpath(root)).rstrip("\\/")
	path = os.path.normcase(os.path.normpath(path))
	if path == root:
		return ""
	if path.startswith(root + os.sep):
		return path[len(root) + 1:].replace("\\", "/").lower()
	return None


def check_tool_dir(repo, value):
	"""(rel, None) when config.json's tool_dir names a usable CLI folder, '/'-joined; (None, why) otherwise.

	Usable: a relative path of plain segments ("/" or "\\" between them, "." and a trailing separator dropped),
	with no drive, UNC or absolute start and no ".." segment; a folder, not the repo root and not overlapping the
	board (.claude/tickets), as the hooks require; that resolves inside the repo with symlinks and junctions
	followed; and that holds a tickets.py resolving inside the repo too. Stricter than the hooks (which accept
	an absolute path inside the project), since release.py reads files from wherever it points."""
	if not isinstance(value, str):
		return None, "is not a string"
	text = value.replace("\\", "/")
	if text.startswith("/") or ":" in text:
		return None, "is not a relative path (absolute, drive or UNC)"
	parts = [part for part in text.split("/") if part not in ("", ".")]
	if any(part == ".." for part in parts):
		return None, "has a '..' segment"
	for part in parts:
		problem = windows_name_problem(part)
		if problem:
			return None, "segment '{}': {}".format(shown_value(part), problem)
	if not parts:
		return None, "is the repo root"
	rel = "/".join(parts)
	if board_overlaps(rel.lower()):
		return None, "overlaps the board (.claude/tickets)"
	folder = os.path.join(repo, *parts)
	if not os.path.isdir(folder):
		return None, "is not a folder in the repo"
	real_repo = os.path.realpath(repo)
	real = inside(os.path.realpath(folder), real_repo)
	if real is None:
		return None, "resolves outside the repo (a symlink or junction)"
	if real == "":
		return None, "resolves to the repo root"
	if board_overlaps(real):
		return None, "resolves into the board (.claude/tickets)"
	marker = os.path.join(folder, "tickets.py")
	if not os.path.isfile(marker):
		return None, "holds no tickets.py"
	if inside(os.path.realpath(marker), real_repo) is None:
		return None, "its tickets.py resolves outside the repo (a symlink)"
	return rel, None


def board_overlaps(rel):
	"""True when the lower-case '/'-joined folder `rel` is the board, holds it, or lies in it (the hooks' rule)."""
	return rel == board_rel or rel.startswith(board_rel + "/") or board_rel.startswith(rel + "/")


def find_cli_dir(repo, requested):
	"""The CLI's folder relative to the repo: --cli-dir when given, else config.json's tool_dir when it is usable
	(check_tool_dir), else the first of cli_dir_candidates holding tickets.py. A tool_dir that is set but not used,
	or a config.json that cannot be read, prints one note; nothing found exits with an ERROR naming every path
	tried."""
	if requested:
		return requested
	tried = []
	config, why = read_config(repo)
	if config is None:
		print("note: {} ignored, tool_dir not read: {}".format(config_rel.replace(os.sep, "/"), why))
	else:
		value = config.get("tool_dir")
		# As the hooks do: a null or blank tool_dir means not set.
		if value is not None and not (isinstance(value, str) and not value.strip()):
			if isinstance(value, str):
				shown = "'{}'".format(shown_value(value))
			else:
				# The value itself is not quoted: an object or array could be long.
				shown = "(a JSON {})".format("object" if isinstance(value, dict) else "array"
					if isinstance(value, list) else json_kind(value))
			rel, why = check_tool_dir(repo, value)
			if rel:
				return rel
			print("note: config.json tool_dir {} ignored: {}".format(shown, why))
			tried.append("tool_dir {} ({})".format(shown, why))
	for candidate in cli_dir_candidates:
		if os.path.isfile(os.path.join(repo, candidate, "tickets.py")):
			return candidate
	tried += cli_dir_candidates
	raise SystemExit("ERROR no tickets.py under {} (tried {}); pass --cli-dir".format(repo, ", ".join(tried)))


def compare(entry, installed, relative, scheme=normalize_scheme):
	"""exact | whitespace | settings-only | differs | missing, for one installed file, hashed by the manifest's
	normalize scheme."""
	if not os.path.isfile(installed):
		return "missing"
	got = digests(read_bytes(installed), relative, scheme)
	if got["exact"] == entry["exact"]:
		return "exact"
	if got["loose"] == entry["loose"]:
		return "whitespace"
	if entry["kind"] == "skill" and "exact_no_settings" in got:
		if (got["exact_no_settings"] == entry.get("exact_no_settings")
				or got["loose_no_settings"] == entry.get("loose_no_settings")):
			return "settings-only"
	return "differs"


def release_bytes(version, relative, entry):
	"""A release's own copy of one payload file: payload/ when its bytes are that release's, else the
	release tag in git. None when neither holds it."""
	path = os.path.join(payload_dir, relative)
	if os.path.isfile(path):
		data = read_bytes(path)
		if sha256(data) == entry.get("raw"):
			return data
	found = git("cat-file", "blob", "tickets-v{}:{}payload/{}".format(version, git_layout()[1], relative))
	if found is not None and found.returncode == 0 and sha256(found.stdout) == entry.get("raw"):
		return found.stdout
	return None


def differing_lines(version, relative, entry, installed, scheme=normalize_scheme):
	"""How many lines a unified diff (after normalize) removes or adds between the release's file and the
	installed one, as text for the report."""
	if relative.endswith(binary_suffixes):
		return "binary"
	original = release_bytes(version, relative, entry)
	if original is None:
		return "? lines (release copy not found)"
	old = normalize(to_text(original), scheme).split("\n")
	new = normalize(to_text(read_bytes(installed)), scheme).split("\n")
	count = 0
	for line in difflib.unified_diff(old, new, lineterm="", n=0):
		if line.startswith(("---", "+++")):
			continue
		if line.startswith(("-", "+")):
			count += 1
	return "{} diff line(s)".format(count)


def release_names():
	"""The recorded releases' manifest file names, oldest first; anything not named x.y.z.json is skipped."""
	names = []
	for name in os.listdir(releases_dir):
		if not name.endswith(".json"):
			continue
		if not version_pattern.match(name[:-5]):
			print("skipped releases/{} (not named x.y.z.json)".format(name))
			continue
		names.append(name)
	return sorted(names, key=lambda name: [int(part) for part in name[:-5].split(".")])


def command_identify(args):
	repo = os.path.abspath(args.repo)
	cli_dir = find_cli_dir(repo, args.cli_dir)
	print("repo: {}  (CLI at {})".format(repo, cli_dir))
	names = release_names()
	if not names:
		raise SystemExit("ERROR no releases recorded in " + releases_dir)
	# Every manifest is read (and vetted) before anything is compared, so a broken one stops the run cleanly.
	manifests = [(name[:-5], read_manifest(os.path.join(releases_dir, name))) for name in names]
	matching = ("exact", "whitespace", "settings-only")
	# Per release, the exact hashes of the files it ships (all but the adapted ones), for the ranking below.
	shipped = {version: {entry["exact"] for entry in manifest["files"].values() if entry["kind"] != "adapted"}
		for version, manifest in manifests}
	best = None
	# Each release's summary line and per-file rows, printed once the closest release is known: every summary, but the
	# rows only under the closest one (B63: the same local change repeated for every older release was noise). With
	# --verbose every release keeps its rows.
	reports = []
	for version, manifest in manifests:
		rows = []
		scheme = scheme_of(manifest)
		files = manifest["files"]
		editable = required_edits.get(version, set())
		results = {}
		located = {}
		for relative, entry in files.items():
			located[relative] = installed_path(repo, cli_dir, relative)
			results[relative] = compare(entry, located[relative], relative, scheme)
		product = [relative for relative, entry in files.items() if entry["kind"] in ("product", "skill")]
		matched = [relative for relative in product if results[relative] in matching]
		# Adopting this release required editing these files, so a hash cannot vouch for them: diff them.
		unverified = [relative for relative in product if results[relative] == "differs" and relative in editable]
		local = [relative for relative in product if results[relative] == "differs" and relative not in editable]
		missing = [relative for relative in product if results[relative] == "missing"]
		optional = [relative for relative, entry in files.items() if entry["kind"] == "optional"]
		optional_installed = [relative for relative in optional if results[relative] != "missing"]
		optional_matched = [relative for relative in optional if results[relative] in matching]
		optional_local = [relative for relative in optional if results[relative] == "differs"]
		summary = "release {}: {} product files - {} match, ".format(version, len(product), len(matched))
		if editable:
			summary += "{} unverified ({} per-project edits - diff them), ".format(len(unverified), version)
		summary += "{} local change(s), {} missing".format(len(local), len(missing))
		if optional:
			summary += "; {} optional files - {} installed".format(len(optional), len(optional_installed))
			if optional_installed:
				summary += ": {} match, {} local change(s)".format(len(optional_matched), len(optional_local))
		for relative in sorted(files):
			entry = files[relative]
			state = results[relative]
			note = ""
			if state == "missing" and entry["kind"] in ("adapted", "optional"):
				# Not counted as missing: the summary's count and these rows agree.
				state = "not installed"
				note = "  (yours, optional)" if entry["kind"] == "adapted" else "  (optional)"
			elif entry["kind"] == "adapted":
				note = "  (yours: adapted per project, not compared)"
			elif relative in unverified:
				state = "unverified"
				note = "  ({}; {} required editing this - diff it (UPGRADING.md sect. 1))".format(
					differing_lines(version, relative, entry, located[relative], scheme), version)
			elif relative in local or relative in optional_local:
				note = "  <- local change: diff it (UPGRADING.md sect. 1)"
			if args.verbose or state != "exact":
				shown = os.path.relpath(located[relative], repo).replace(os.sep, "/")
				where = "installed" if os.path.isfile(located[relative]) else "expected at"
				rows.append("  {:<14} {:<8} {}  [{}: {}]{}".format(state, entry["kind"], relative, where, shown, note))
		reports.append((version, summary, rows))
		score = len(matched) + len(unverified)
		# The closest release (B22) has the fewest files that contradict it: local changes, missing files, and
		# unverified files byte-identical to a file another release ships (that release's file, not a per-project
		# edit of this one; every copy of a later release differs from 1.0.0 in all its unverified files). Ties go
		# to the larger share of product files matching (a share, so a release that simply lists more files does
		# not win), then the most unverified, then the newest.
		foreign = 0
		for relative in unverified:
			exact = digests(read_bytes(located[relative]), relative, scheme)["exact"]
			if any(exact in hashes for other, hashes in shipped.items() if other != version):
				foreign += 1
		share = float(len(matched)) / len(product) if product else 0.0
		rank = (-(len(local) + len(missing) + foreign), share, len(unverified), version_tuple(version))
		if best is None or rank > best["rank"]:
			best = {"version": version, "rank": rank, "score": score, "product": len(product), "matched": len(matched),
				"unverified": len(unverified), "local": len(local), "missing": len(missing),
				"optional": len(optional), "optional_installed": len(optional_installed)}
	hidden = 0
	for version, summary, rows in reports:
		print("")
		print(summary)
		if args.verbose or version == best["version"]:
			for row in rows:
				print(row)
		else:
			hidden += len(rows)
	if hidden:
		print("")
		print("({} per-file line(s) of other releases not shown; --verbose shows every release's)".format(hidden))
	print("")
	line = ("closest release: {version} ({score} of {product} product files: {matched} match, {unverified} unverified, "
		"{local} local change(s), {missing} missing)").format(**best)
	if best["optional"]:
		line += "; optional: {optional_installed} of {optional} installed".format(**best)
	print(line)
	if best["unverified"]:
		print("  {} unverified file(s) carry the per-project edits adopting {} required; a hash cannot check them."
			.format(best["unverified"], best["version"]))
		print("  Diff each against the release before upgrading, or local changes in them are lost (UPGRADING.md sect. 1).")
	return 0


# --- merge-doc (B61) ------------------------------------------------------------------------------
# The rules doc, dot-claude/docs/tickets.md, is adapted per project. merge-doc takes a release's copy and an adopter's
# ported copy (and, with --base, the release that copy was ported from) and writes the release text with the project's
# parts kept:
#   values   - the value placeholders below, filled from --set, then config.json, then what the project doc shows
#              (each release or base line holding one is matched against the project's lines to read the value off);
#   lines    - a release line holding a free-text placeholder (capitals that are not a value placeholder, with an
#              optional ": hint") is the project's: the placeholder is filled with the text the project wrote in its
#              place when that can be read off, else the line's counterpart in the project doc is kept whole;
#   blocks   - <!-- project:begin name --> ... <!-- project:end name --> in the release keep the project's content
#              (by name when the project doc has the markers, else by aligning the two docs); a block only the project
#              has is kept after the line it follows. <!-- template:begin/end --> content is the porting note: dropped;
#   edits    - with --base, a three-way merge: where the release left the base text alone, the project's version of it
#              (an edit, an added or a deleted line) is kept.
# Every other line is the release's. A project line that is dropped is the base's own wording (with --base), or it is
# listed as LOOK and the command exits 2: never exit 0 with project text dropped.
doc_value_placeholders = ("NAME", "PREFIX", "FIRST", "PORT", "CLI_DIR", "REPO", "SCRATCH")
doc_value_pattern = re.compile(r"<(" + "|".join(doc_value_placeholders) + r")>")
doc_free_pattern = re.compile(r"<([A-Z][A-Z_]*)(?::[^<>]*)?>")
doc_marker = re.compile(r"^[ \t]*<!--[ \t]*(project|template):(begin|end)(?:[ \t]+([A-Za-z0-9_.-]+))?[ \t]*-->[ \t]*$")
# Older templates wrote these free-text places in words; a base doc of such a release still names them, so the text a
# project wrote there can be read off and moved to the placeholder's line (1.4.0 and earlier).
doc_legacy_free = [
	("NEIGHBOURS", "Say here what else on this PC it keeps clear of."),
	("DESIGN_DOC", "`<where design reasoning goes>`"),
	("ROLE_LIMITS", "`<Add any role limits your agent briefs set.>`"),
]
# A free placeholder (with the backticks around it, if any) as it appears in a line, or a legacy wording of one.
doc_free_token = re.compile(r"`?<(?P<free>[A-Z][A-Z_]*)(?::[^<>]*)?>`?|" + "|".join(
	"(?P<legacy{}>{})".format(index, re.escape(text)) for index, (_, text) in enumerate(doc_legacy_free)))
# A line is used to read a free value off only with this many characters of its own besides the placeholders, so a line
# that is nothing but a placeholder does not match every project line.
doc_context_chars = 8
# How alike (difflib ratio) two lines must be for a free-text line's counterpart to be picked by likeness.
doc_similar_ratio = 0.6
# config.json key per value placeholder.
doc_config_keys = {"NAME": "store_name", "PREFIX": "id_prefix", "FIRST": "first_ticket_number", "PORT": "viewer_port",
	"CLI_DIR": "tool_dir"}


def doc_ascii(text):
	return text.encode("ascii", "backslashreplace").decode("ascii")


def read_doc(path):
	"""(lines without line ends, the line end the file uses, whether it starts with a BOM). UTF-8."""
	try:
		with open(path, "r", encoding="utf-8", newline="") as handle:
			text = handle.read()
	except OSError as error:
		raise SystemExit("ERROR cannot read {} ({})".format(doc_ascii(path), doc_ascii(str(error.strerror or error))))
	except UnicodeDecodeError:
		raise SystemExit("ERROR {} is not UTF-8".format(doc_ascii(path)))
	bom = text.startswith("\ufeff")
	if bom:
		text = text[1:]
	newline = "\r\n" if "\r\n" in text else "\n"
	lines = text.replace("\r\n", "\n").split("\n")
	if lines and lines[-1] == "":
		lines.pop()
	return lines, newline, bom


def parse_doc_blocks(lines, label):
	"""(plain, numbers, blocks, template): the lines without marker lines and template content, each plain line's
	1-based line number in the file, the project blocks as [{"name", "start", "end", "line"}] (plain[start:end] is the
	content), and the template content as [(line number, line)]."""
	plain, numbers, blocks, template = [], [], [], []
	open_block = None
	seen = set()
	after_template = False
	for number, line in enumerate(lines, 1):
		# A template note between blank lines leaves one blank line, not two.
		if after_template and not line.strip() and plain and not plain[-1].strip():
			after_template = False
			continue
		found = doc_marker.match(line)
		if found:
			kind, edge, name = found.group(1), found.group(2), found.group(3) or ""
			if kind == "project" and not name:
				raise SystemExit("ERROR {} line {}: a project marker needs a name".format(label, number))
			if edge == "begin":
				if open_block is not None:
					raise SystemExit("ERROR {} line {}: {} marker inside the open block that line {} begins".format(
						label, number, kind, open_block["line"]))
				if kind == "project" and name in seen:
					raise SystemExit("ERROR {} line {}: project block '{}' given twice".format(label, number, name))
				if kind == "project":
					seen.add(name)
				open_block = {"kind": kind, "name": name, "start": len(plain), "line": number}
			else:
				if open_block is None or open_block["kind"] != kind or (name and name != open_block["name"]):
					raise SystemExit("ERROR {} line {}: {}:end does not close an open {} block".format(label, number, kind,
						kind))
				if kind == "project":
					blocks.append({"name": open_block["name"], "start": open_block["start"], "end": len(plain),
						"line": open_block["line"]})
				after_template = kind == "template"
				open_block = None
			continue
		if open_block is not None and open_block["kind"] == "template":
			template.append((number, line))
			continue
		after_template = False
		plain.append(line)
		numbers.append(number)
	if open_block is not None:
		raise SystemExit("ERROR {} line {}: {} block '{}' is never closed".format(label, open_block["line"],
			open_block["kind"], open_block["name"]))
	return plain, numbers, blocks, template


def free_placeholders(line):
	return [name for name in doc_free_pattern.findall(line) if name not in doc_value_placeholders]


def learned_doc_values(lines, project):
	"""{placeholder: {value: count}}, read off the project lines that match a line with value placeholders."""
	learned = {}
	project_set = set(project)
	for line in lines:
		if not doc_value_pattern.search(line) or free_placeholders(line):
			continue
		pattern, named = "", set()
		position = 0
		for found in doc_value_pattern.finditer(line):
			pattern += re.escape(line[position:found.start()])
			name = found.group(1)
			pattern += "(?P={})".format(name) if name in named else "(?P<{}>.+?)".format(name)
			named.add(name)
			position = found.end()
		pattern += re.escape(line[position:])
		compiled = re.compile(pattern)
		for candidate in project_set:
			matched = compiled.fullmatch(candidate)
			if matched:
				for name, value in matched.groupdict().items():
					counts = learned.setdefault(name, {})
					counts[value] = counts.get(value, 0) + 1
	return learned


def free_token_name(found):
	if found.group("free"):
		return found.group("free")
	for index, (name, _) in enumerate(doc_legacy_free):
		if found.group("legacy{}".format(index)):
			return name
	return None


def learned_free_values(lines, project):
	"""{free placeholder: {value: set of project line offsets}}, read off the project lines that match a line (value
	placeholders already filled) holding free placeholders or their legacy wording, with enough text of its own."""
	learned = {}
	for line in lines:
		tokens = [found for found in doc_free_token.finditer(line)
			if free_token_name(found) and free_token_name(found) not in doc_value_placeholders]
		if not tokens:
			continue
		pattern, named, own = "", set(), ""
		position = 0
		for found in tokens:
			own += line[position:found.start()]
			pattern += re.escape(line[position:found.start()])
			name = free_token_name(found)
			pattern += "(?P={})".format(name) if name in named else "(?P<{}>.+?)".format(name)
			named.add(name)
			position = found.end()
		own += line[position:]
		pattern += re.escape(line[position:])
		if len(own.strip()) < doc_context_chars:
			continue
		compiled = re.compile(pattern)
		for offset, candidate in enumerate(project):
			matched = compiled.fullmatch(candidate)
			if matched:
				for name, value in matched.groupdict().items():
					learned.setdefault(name, {}).setdefault(value, set()).add(offset)
	return learned


def filled_free(line, values):
	"""A release line with each free placeholder (and the backticks around it) replaced by its learned value."""
	return doc_free_token.sub(lambda found: values.get(free_token_name(found), found.group(0))
		if found.group("free") else found.group(0), line)


def doc_config(path):
	"""The config.json values for the placeholders, as text; {} with a note when it cannot be read."""
	try:
		with open(path, "r", encoding="utf-8-sig") as handle:
			config = json.load(handle)
	except (OSError, ValueError) as error:
		return {}, "config {} not read ({}); values come from --set and the project doc".format(doc_ascii(path),
			doc_ascii(str(getattr(error, "strerror", None) or error)))
	if not isinstance(config, dict):
		return {}, "config {} is not a JSON object; not used".format(doc_ascii(path))
	values = {}
	for name, key in doc_config_keys.items():
		value = config.get(key)
		if isinstance(value, bool) or value is None:
			continue
		if isinstance(value, (str, int)) and str(value).strip():
			values[name] = str(value).strip().rstrip("/\\") if name == "CLI_DIR" else str(value)
	if "FIRST" not in values:
		values["FIRST"] = "1"
	return values, None


def aligned_range(opcodes, start, end):
	"""The project lines that release lines [start, end) align with, as (low, high, spills): spills is True when a
	changed hunk it takes reaches release lines outside the range. None when nothing aligns."""
	spans, spills = [], False
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			low, high = max(start, i1), min(end, i2)
			if low < high:
				spans.append((j1 + low - i1, j1 + high - i1))
			continue
		if i1 == i2:
			touches = start <= i1 <= end
		else:
			touches = i1 < end and start < i2
		if touches and j2 > j1:
			spans.append((j1, j2))
			if i1 < start or i2 > end:
				spills = True
	if not spans:
		return None
	return min(low for low, _ in spans), max(high for _, high in spans), spills


def same_path(first, second):
	"""Whether two paths name one file: os.path.samefile when both exist, else the normalised absolute paths."""
	try:
		if os.path.exists(first) and os.path.exists(second):
			return os.path.samefile(first, second)
	except OSError:
		pass
	return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def write_doc_atomically(path, text):
	"""Write text (UTF-8, as given) to a temporary file beside path, then move it over path in one step."""
	temp = "{}.merge-doc-{}.tmp".format(path, os.getpid())
	try:
		with open(temp, "w", encoding="utf-8", newline="") as handle:
			handle.write(text)
		os.replace(temp, path)
	except OSError as error:
		try:
			if os.path.exists(temp):
				os.remove(temp)
		except OSError:
			pass
		raise SystemExit("ERROR cannot write {} ({})".format(doc_ascii(path), doc_ascii(str(error.strerror or error))))


def command_merge_doc(args):
	release_doc = os.path.abspath(args.release_doc)
	project_doc = os.path.abspath(args.project_doc)
	out_path = os.path.abspath(args.out)
	inputs = [("release_doc", release_doc), ("project_doc", project_doc)]
	if args.base:
		inputs.append(("--base", os.path.abspath(args.base)))
	for label, path in inputs:
		if same_path(out_path, path):
			raise SystemExit("ERROR --out is the {} ({}); write the merged doc elsewhere, review the diff, then copy it "
				"over".format(label, doc_ascii(path)))
	release_lines, _, _ = read_doc(release_doc)
	project_lines, newline, bom = read_doc(project_doc)
	release, _, release_blocks, release_template = parse_doc_blocks(release_lines, "release doc")
	project, project_numbers, project_blocks, project_template = parse_doc_blocks(project_lines, "project doc")
	base = None
	if args.base:
		base_lines, _, _ = read_doc(os.path.abspath(args.base))
		base, _, _, _ = parse_doc_blocks(base_lines, "base doc")
	notes, look = [], []

	# The values: --set, then config.json, then what the project doc shows, then where the doc sits.
	doc_repo = None
	parts = project_doc.replace("\\", "/").split("/")
	if len(parts) >= 4 and parts[-3] == ".claude" and parts[-2] == "docs":
		doc_repo = os.path.dirname(os.path.dirname(os.path.dirname(project_doc)))
	config_path = args.config or (os.path.join(doc_repo, config_rel) if doc_repo else None)
	config_values = {}
	if config_path:
		config_values, problem = doc_config(config_path)
		if problem:
			notes.append(problem)
	given = {}
	for item in args.set or []:
		name, sep, value = item.partition("=")
		if not sep or name not in doc_value_placeholders:
			raise SystemExit("ERROR --set takes NAME=value with NAME one of {}".format(", ".join(doc_value_placeholders)))
		given[name] = value
	learned = learned_doc_values(release + (base or []), project)
	values, sources = {}, {}
	for name in doc_value_placeholders:
		counts = learned.get(name, {})
		read_off = max(sorted(counts), key=lambda value: counts[value]) if counts else None
		if len(counts) > 1:
			notes.append("<{}> reads differently in the project doc: {}".format(name, "; ".join(
				"'{}' x{}".format(doc_ascii(value), counts[value]) for value in sorted(counts))))
		if name in given:
			values[name], sources[name] = given[name], "--set"
		elif name in config_values:
			values[name], sources[name] = config_values[name], "config.json"
		elif read_off is not None:
			values[name], sources[name] = read_off, "project doc"
		elif name == "REPO" and doc_repo:
			values[name], sources[name] = doc_repo, "the doc's location"
		if read_off is not None and name in values and values[name] != read_off and sources[name] != "project doc":
			notes.append("<{}> is '{}' from {}, but the project doc shows '{}'".format(name, doc_ascii(values[name]),
				sources[name], doc_ascii(read_off)))

	def fill(line):
		return doc_value_pattern.sub(lambda found: values.get(found.group(1), found.group(0)), line)

	filled = [fill(line) for line in release]
	unfilled = sorted({name for line in filled for name in doc_value_pattern.findall(line)})
	# Base wording is decided by position: a project (or release) line is the base's own text only inside an equal
	# block of the base aligned with it, never because the same text occurs somewhere else in the base (a lone fence, a
	# table rule, a repeated CLI line).
	base_project, base_release = set(), set()
	if base is not None:
		base_keys = [fill(line).rstrip() for line in base]
		for side, keys in ((base_project, [line.rstrip() for line in project]), (base_release,
				[line.rstrip() for line in filled])):
			aligner = difflib.SequenceMatcher(None, base_keys, keys, autojunk=False)
			for tag, _, _, j1, j2 in aligner.get_opcodes():
				if tag == "equal":
					side.update(range(j1, j2))

	# The project's template note: dropped like the release's, but reported where it is not the release's own text.
	release_note = [fill(line).rstrip() for _, line in release_template]
	changed_note = [(number, line) for number, line in project_template if fill(line).rstrip() not in release_note]
	if changed_note:
		look.append("{} line(s) between your template:begin/end markers differ from the release's porting note; that "
			"note is dropped, so these are NOT in the merged doc:".format(len(changed_note)))
		look.extend("    {:>4}: {}".format(number, doc_ascii(line)) for number, line in changed_note)

	# The text the project wrote in each free-text place, where a line with enough text of its own shows it.
	free_found = learned_free_values(filled + [fill(line) for line in (base or [])], project)
	free_values, free_offsets = {}, {}
	for name, found in free_found.items():
		if len(found) == 1:
			value = next(iter(found))
			free_values[name], free_offsets[name] = value, found[value]
		else:
			notes.append("<{}> reads differently in the project doc ({} versions); its line is matched instead".format(
				name, len(found)))

	# The project's parts of the release: its blocks, and runs of free-placeholder lines outside them.
	in_block = set()
	for block in release_blocks:
		in_block.update(range(block["start"], block["end"]))
	parts_list = [dict(block, kind="block") for block in release_blocks]
	index = 0
	while index < len(release):
		if index not in in_block and free_placeholders(release[index]):
			start = index
			while index < len(release) and index not in in_block and free_placeholders(release[index]):
				index += 1
			parts_list.append({"name": ", ".join(sorted({name for line in release[start:index]
				for name in free_placeholders(line)})), "start": start, "end": index, "kind": "free"})
			continue
		index += 1

	matcher = difflib.SequenceMatcher(None, [line.rstrip() for line in filled], [line.rstrip() for line in project],
		autojunk=False)
	opcodes = matcher.get_opcodes()
	used = set()
	by_name = {block["name"]: block for block in project_blocks}
	for block in project_blocks:
		used.update(range(block["start"], block["end"]))
	kept = {}
	for number, part in enumerate(parts_list):
		label = ("block '{}'" if part["kind"] == "block" else "<{}>").format(part["name"])
		if part["kind"] == "block" and part["name"] in by_name:
			block = by_name[part["name"]]
			kept[number] = project[block["start"]:block["end"]]
			continue
		names = {name for line in release[part["start"]:part["end"]] for name in free_placeholders(line)}
		if part["kind"] == "free" and names and all(name in free_values for name in names):
			# The release's line, with the project's text in its free places: release wording around it still merges.
			kept[number] = [filled_free(line, free_values) for line in filled[part["start"]:part["end"]]]
			for name in names:
				used.update(free_offsets[name])
			notes.append("filled {} from your doc (line(s) {})".format(label, ", ".join(
				str(project_numbers[offset]) for offset in sorted(set().union(*(free_offsets[name] for name in names))))))
			continue
		found = aligned_range(opcodes, part["start"], part["end"])
		if found is None or found[0] == found[1]:
			kept[number] = filled[part["start"]:part["end"]]
			if part["end"] > part["start"]:
				look.append("{}: no counterpart in the project doc; the release's text is kept - fill it in".format(label))
			continue
		low, high, spills = found
		offsets = [offset for offset in range(low, high) if offset not in used]
		if spills and part["kind"] == "free":
			offsets = picked_offsets(offsets, project, filled, part, opcodes, in_block, base_project)
		used.update(offsets)
		kept[number] = [project[offset] for offset in offsets]
		if part["kind"] == "free":
			notes.append("kept project line(s) {}: {}".format(", ".join(str(project_numbers[offset]) for offset in offsets)
				or "-", label))
			if spills:
				look.append("{}: the release also changed the text around it, so project line(s) {} were picked by "
					"likeness; check the diff there".format(label, ", ".join(str(project_numbers[offset])
					for offset in offsets) or "-"))

	# With --base, a three-way merge of every other changed hunk: where the release kept the base text, the project's
	# version is kept; where only the release changed it, the release's; where both did, the release's, and the
	# project's own lines are a LOOK.
	covered = set(in_block)
	for part in parts_list:
		covered.update(range(part["start"], part["end"]))
	conflicts = []
	if base is not None:
		for tag, i1, i2, j1, j2 in opcodes:
			if tag == "equal" or any(index in covered for index in range(i1, i2)):
				continue
			if i1 == i2 and any(part["start"] < i1 < part["end"] for part in parts_list):
				continue
			project_side = [offset for offset in range(j1, j2) if offset not in used]
			release_new = [index for index in range(i1, i2) if index not in base_release]
			project_new = [offset for offset in project_side if offset not in base_project]
			if not release_new and (project_new or i2 > i1):
				parts_list.append({"name": "edit", "start": i1, "end": i2, "kind": "edit"})
				kept[len(parts_list) - 1] = [project[offset] for offset in project_side]
				used.update(project_side)
				if project_side:
					notes.append("kept your edit, line(s) {} (the release left that text as it was)".format(
						shown_numbers(project_numbers, project_side[0], project_side[-1] + 1)))
				else:
					notes.append("left out {} release line(s) your doc deleted (the release did not change them), from "
						"'{}'".format(i2 - i1, doc_ascii(next((filled[index].strip() for index in range(i1, i2)
						if filled[index].strip()), "")[:60])))
			elif project_new:
				conflicts += project_new
				used.update(project_new)

	# Project lines in no kept part that differ from the release: the base's own wording (dropped, listed), or a LOOK.
	leftovers, replaced = list(conflicts), []
	for tag, i1, i2, j1, j2 in opcodes:
		if tag == "equal":
			continue
		for offset in range(j1, j2):
			if offset in used or not project[offset].strip():
				# A blank line the release does not have is layout, not content.
				continue
			(replaced if offset in base_project else leftovers).append(offset)
	leftovers.sort()

	# Blocks only the project has: kept after the release line the project line before them matches.
	release_names_set = {block["name"] for block in release_blocks}
	after = {}
	for block in project_blocks:
		if block["name"] in release_names_set:
			continue
		anchor = None
		if block["start"] == 0:
			anchor = -1
		else:
			for tag, i1, i2, j1, j2 in opcodes:
				if tag == "equal" and j1 <= block["start"] - 1 < j2:
					anchor = i1 + block["start"] - 1 - j1
					break
		if anchor is None:
			look.append("project block '{}' (line {}): the line before it is not in the release text, so it was not "
				"placed; its lines are NOT in the merged doc:".format(block["name"], block["line"]))
			look.extend("    " + doc_ascii(line) for line in project[block["start"]:block["end"]])
			continue
		after.setdefault(anchor, []).append(block)

	def emit_block(out, name, content):
		out.append("<!-- project:begin {} -->".format(name))
		out.extend(content)
		out.append("<!-- project:end {} -->".format(name))

	def emit_after(out, release_index):
		for block in after.get(release_index, []):
			emit_block(out, block["name"], project[block["start"]:block["end"]])

	def emit_part(out, number):
		part = parts_list[number]
		if part["kind"] == "block":
			emit_block(out, part["name"], kept[number])
		else:
			out.extend(kept[number])

	starting = {}
	for number, part in enumerate(parts_list):
		starting.setdefault(part["start"], []).append(number)
	merged = []
	emit_after(merged, -1)
	index = 0
	while True:
		here = starting.get(index, [])
		# An empty part (the release's rules pair, a line the project added) consumes no release line.
		for number in here:
			if parts_list[number]["end"] == index:
				emit_part(merged, number)
		if index >= len(filled):
			break
		spanning = [number for number in here if parts_list[number]["end"] > index]
		if spanning:
			emit_part(merged, spanning[0])
			for covered_index in range(index, parts_list[spanning[0]]["end"]):
				emit_after(merged, covered_index)
			index = parts_list[spanning[0]]["end"]
			continue
		merged.append(filled[index])
		emit_after(merged, index)
		index += 1

	write_doc_atomically(out_path, ("\ufeff" if bom else "") + newline.join(merged) + newline)

	print("merged {} lines into {}{}".format(len(merged), doc_ascii(out_path), "" if base is not None else
		"  (no --base: every project line the release text replaces is listed as LOOK)"))
	for name in doc_value_placeholders:
		if name in values:
			print("  <{}> = '{}'  ({})".format(name, doc_ascii(values[name]), sources[name]))
	if replaced:
		notes.append("{} project line(s) are the base release's wording of a line this release changed or removed; "
			"the release's text is taken:".format(len(replaced)))
		notes.extend("    {:>4}: {}".format(project_numbers[offset], doc_ascii(project[offset])) for offset in replaced)
	for note in notes:
		print(("NOTE " + note) if not note.startswith("    ") else note)
	for name in unfilled:
		look.append("<{}> has no value (give --set {}=...); the placeholder is left in the merged doc".format(name, name))
	if leftovers:
		look.append("{} project line(s) are NOT in the merged doc: the release text replaced them{}. Put each back where "
			"it belongs (inside a project:begin/end pair keeps it from then on), or let it go if the release says the "
			"same:".format(len(leftovers), ", and they are not the base release's wording" if base is not None else
			" (give --base to tell your edits from older release wording)"))
		for offset in leftovers:
			look.append("    {:>4}: {}".format(project_numbers[offset], doc_ascii(project[offset])))
	for line in look:
		print(("LOOK " + line) if not line.startswith("    ") else line)
	if look:
		print("exit 2: something to look at. Review the merged doc against your doc (a diff) before replacing it.")
		return 2
	print("exit 0: no project text was dropped. Review the merged doc against your doc (a diff) before replacing it.")
	return 0


def older_wording(line, candidates):
	"""Whether a project line is alike (difflib ratio) one of the candidate release lines."""
	return any(difflib.SequenceMatcher(None, line.strip(), other.strip(), autojunk=False).ratio() >= doc_similar_ratio
		for other in candidates)


def picked_offsets(offsets, project, filled, part, opcodes, in_block, base_project):
	"""For a free-text part whose changed hunk reaches past it: the project lines that are its counterpart, not the
	older wording of the release lines around it. The line most like each of the part's release lines, plus the
	adjacent lines that are neither base wording nor alike another release line of the hunk (more rows of a table the
	project filled, say)."""
	others = []
	for tag, i1, i2, j1, j2 in opcodes:
		if tag != "equal" and any(j1 <= offset < j2 for offset in offsets):
			others += [filled[index] for index in range(i1, i2)
				if not (part["start"] <= index < part["end"]) and index not in in_block]
	chosen = set()
	for index in range(part["start"], part["end"]):
		scored = [(difflib.SequenceMatcher(None, project[offset].strip(), filled[index].strip(), autojunk=False).ratio(),
			-offset) for offset in offsets if offset not in chosen and offset not in base_project]
		if scored:
			chosen.add(-max(scored)[1])
	if not chosen:
		return []
	position = {offset: place for place, offset in enumerate(offsets)}
	for step in (-1, 1):
		place = position[min(chosen)] if step < 0 else position[max(chosen)]
		while 0 <= place + step < len(offsets):
			offset = offsets[place + step]
			line = project[offset]
			if not line.strip() or offset in base_project or older_wording(line, others):
				break
			chosen.add(offset)
			place += step
	return sorted(chosen)


def shown_numbers(numbers, low, high):
	"""Plain lines [low, high) as the file's line numbers, 'N' or 'N-M'."""
	if high <= low:
		return "-"
	first, last = numbers[low], numbers[high - 1]
	return str(first) if first == last else "{}-{}".format(first, last)


def windows_name_problem(part):
	"""Why one path part would not land on Windows as itself (a device, a dropped trailing dot or space, a
	reserved character, an 8.3 short-name look-alike), or None."""
	if part.endswith((".", " ")):
		return "ends in a dot or space, which Windows drops"
	if any(char in windows_forbidden or ord(char) < 32 for char in part):
		return "a character Windows does not allow in a name"
	if part.split(".")[0].rstrip(" ").upper() in windows_devices:
		return "a Windows device name"
	if short_name_pattern.search(part):
		return "looks like a Windows 8.3 short name (~digit)"
	return None


def vet_member(member, seen=None, top=("ticket-system",)):
	"""The member's path inside the release folder `top` (its path parts in the archive: ticket-system/ in the
	maintainer's repository, () in a clone of the public repository, git_layout), or None for that folder itself. Exits
	on anything that is not a plain file or folder under it with a clean relative name that Windows keeps as itself.
	`seen` (case-folded path -> path), shared across one archive's members, catches two names that differ only in
	case, which a Windows folder would merge."""
	name = member.name
	problem = None
	depth = len(top)
	if not (member.isfile() or member.isdir()):
		problem = "not a regular file or folder"
	elif "\\" in name or ":" in name:
		problem = "backslash or colon in the name"
	elif name.startswith("/") or os.path.isabs(name):
		problem = "absolute path"
	else:
		parts = name.split("/")
		if tuple(parts[:depth]) != tuple(top):
			problem = "outside {}/".format("/".join(top))
		elif any(part in ("", ".", "..") for part in parts[depth:]):
			problem = "empty, '.' or '..' path part"
		else:
			for part in parts[depth:]:
				problem = windows_name_problem(part)
				if problem:
					problem = "{!r}: {}".format(part, problem)
					break
			if not problem and seen is not None:
				for end in range(depth + 1, len(parts) + 1):
					prefix = "/".join(parts[depth:end])
					other = seen.setdefault(prefix.casefold(), prefix)
					if other != prefix:
						problem = "differs only in case from {!r}".format(other)
						break
	if problem:
		raise SystemExit("ERROR unexpected archive entry {!r}: {}".format(name, problem))
	return "/".join(parts[depth:]) or None


def release_ref(args):
	"""The git ref export reads (and the maintainer's publish step): the release tag tickets-v<version>, or --ref. Exits
	on a bad version or ref."""
	version = args.version
	if version.startswith("-") or not version_pattern.match(version):
		raise SystemExit("ERROR not a version: " + version)
	# --ref reads an unreleased branch or commit instead, for pre-release testing only.
	if args.ref is not None and (not args.ref or args.ref.startswith("-")):
		raise SystemExit("ERROR --ref must name a branch, tag or commit, not an option: {!r}".format(args.ref))
	return args.ref or "tickets-v" + version


def open_release(tag):
	"""The ref's release folder from git archive (ticket-system/ in the maintainer's repository, the whole tree in a
	clone of the public repository: git_layout), every entry vetted before anything is written: (the open tarfile, its
	members, each renamed to its path inside the release folder). Exits on an entry vet_member refuses, a cut-off
	archive or a git failure. The caller closes the tarfile, and catches tarfile.TarError from reading it."""
	prefix = git_layout()[1].strip("/")
	top = tuple(prefix.split("/")) if prefix else ()
	# core.autocrlf off: the files come out as committed (LF here), whatever the user's git config says; only the repository's
	# own .gitattributes may change an ending (eol=crlf for *.bat).
	archive = git("-c", "core.autocrlf=false", "archive", "--format=tar", "--end-of-options", tag,
		*([prefix] if prefix else []))
	if archive is None:
		raise SystemExit("ERROR cannot run git")
	if archive.returncode != 0:
		detail = archive.stderr.decode("ascii", "replace").strip()
		raise SystemExit("ERROR cannot read {}: {}".format(tag, detail or "git archive failed"))
	bundle = tarfile.open(fileobj=io.BytesIO(archive.stdout))
	try:
		members = []
		seen = {}
		for member in bundle.getmembers():
			inner = vet_member(member, seen, top)
			if member.isfile() and member.offset_data + member.size > len(archive.stdout):
				raise SystemExit("ERROR archive is truncated at {!r}".format(member.name))
			if inner is None:
				continue
			member.name = inner
			members.append(member)
		# tarfile reads a header cut short as the end of the archive; a whole archive ends in two zero blocks.
		end = archive.stdout[bundle.offset:bundle.offset + 2 * tarfile.BLOCKSIZE]
		if len(end) < 2 * tarfile.BLOCKSIZE or end.strip(b"\0"):
			raise SystemExit("ERROR archive is truncated (no end-of-archive marker)")
	except BaseException:
		bundle.close()
		raise
	return bundle, members


def extract_members(bundle, members, destination):
	"""Write open_release's vetted members into destination, creating it."""
	os.makedirs(destination, exist_ok=True)
	if hasattr(tarfile, "data_filter"):
		bundle.extractall(destination, members=members, filter="data")
	else:
		# A Python without extraction filters (before 3.12 and the 3.8.17 / 3.9.17 / 3.10.12 / 3.11.4
		# backports). vet_member has still refused links, devices, absolute and '..' paths; what is lost
		# is the data filter's reset of odd permission bits.
		bundle.extractall(destination, members=members)


def command_export(args):
	"""Extract a tagged release's ticket-system/ folder from git, so a copy never comes from a work branch."""
	tag = release_ref(args)
	destination = os.path.abspath(args.destination)
	if os.path.exists(destination) and not os.path.isdir(destination):
		raise SystemExit("ERROR {} exists and is not a folder".format(destination))
	if os.path.isdir(destination) and os.listdir(destination):
		raise SystemExit("ERROR {} exists and is not empty".format(destination))
	try:
		bundle, members = open_release(tag)
		with bundle:
			extract_members(bundle, members, destination)
	except (tarfile.TarError, OSError) as error:
		partial = "; it may hold a partial copy, delete it" if os.path.isdir(destination) and os.listdir(destination) else ""
		raise SystemExit("ERROR cannot extract {} into {}: {}: {}{}".format(
			tag, destination, type(error).__name__, error, partial))
	print("exported {} to {}".format(tag, destination))
	return 0


def main():
	# A cp1252 console cannot print every path; replace what it cannot encode rather than crash.
	for stream in (sys.stdout, sys.stderr):
		try:
			stream.reconfigure(errors="replace")
		except Exception:
			pass
	parser = argparse.ArgumentParser(description="Ticket system release tooling.")
	commands = parser.add_subparsers(dest="command", required=True)
	manifest = commands.add_parser("manifest", help="record releases/<VERSION>.json from payload/")
	manifest.add_argument("--force", action="store_true", help="rewrite an existing manifest (untagged release only)")
	manifest.set_defaults(handler=command_manifest)
	check = commands.add_parser("check", help="payload, VERSION, CHANGELOG and manifest agree; the bump level fits")
	check.add_argument("--release", action="store_true",
		help="fail, not warn, while BACKLOG.md lists open items (the release checklist runs this)")
	check.set_defaults(handler=command_check)
	identify = commands.add_parser("identify", help="compare an installed copy with every recorded release")
	identify.add_argument("repo", help="the adopting repository's root")
	identify.add_argument("--cli-dir", help="the CLI's folder relative to the repo (default: tool_dir from the repo's "
		".claude/tickets/config.json when it is a relative folder inside the repo holding tickets.py, else the first of "
		"{} holding it)".format(" and ".join(cli_dir_candidates)))
	identify.add_argument("--verbose", action="store_true",
		help="list exact matches too, and every release's per-file lines (by default only the closest release's)")
	identify.set_defaults(handler=command_identify)
	export = commands.add_parser("export", help="extract a tagged release into a folder, for installing")
	export.add_argument("version", help="x.y.z; the release tag is tickets-v<version>")
	export.add_argument("destination", help="an empty or new folder (e.g. your scratch)")
	export.add_argument("--ref", help="export this git ref instead of the release tag (pre-release testing only)")
	export.set_defaults(handler=command_export)
	merge_doc = commands.add_parser("merge-doc",
		help="merge a release's rules doc into a project's ported copy, keeping the project's values and parts")
	merge_doc.add_argument("release_doc", help="the release's dot-claude/docs/tickets.md (e.g. from export)")
	merge_doc.add_argument("project_doc", help="the project's ported copy (e.g. <repo>/.claude/docs/tickets.md)")
	merge_doc.add_argument("--out", required=True,
		help="where to write the merged doc: a new file, never one of the inputs (review the diff, then copy it over)")
	merge_doc.add_argument("--base", help="the rules doc of the release your doc was ported from (export that release); "
		"enables the three-way merge that keeps your edits and tells them from older release wording")
	merge_doc.add_argument("--config", help="the project's config.json (default: <repo>/.claude/tickets/config.json when "
		"project_doc is <repo>/.claude/docs/<file>)")
	merge_doc.add_argument("--set", action="append", metavar="NAME=VALUE",
		help="a placeholder value, overriding config.json and the project doc ({}); repeatable".format(
			", ".join(doc_value_placeholders)))
	merge_doc.set_defaults(handler=command_merge_doc)
	args = parser.parse_args()
	return args.handler(args)


if __name__ == "__main__":
	sys.exit(main())
