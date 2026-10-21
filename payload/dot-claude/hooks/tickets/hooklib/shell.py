"""Where a shell command writes: a conservative, static extractor of write and delete TARGETS from a Bash or
PowerShell command line. It parses text only and never runs anything.

	write_targets(command, powershell) -> [(verb, raw target, kind)]   kind: "write" | "delete"
	parse(command, powershell)         -> (the same list, complete)   complete: False when the command was
																	   longer than the parse bounds

Covered: output redirects (> >> >| &> *> and N>, plus the read-write <>; &N, /dev/null, $null and NUL are
skipped); copy/move (cp mv install ln xcopy robocopy Copy-Item Move-Item Rename-Item copy move ren; a move
also changes its source); create/overwrite (touch mkdir tee truncate Set-Content Add-Content Out-File New-Item
Clear-Content); delete (rm rmdir del erase rd unlink Remove-Item); in-place edit (sed -i, perl -i); and git
rm/mv/checkout/restore. PowerShell -Path/-LiteralPath/-FilePath/-Destination/-NewName values are read by
name, and comma lists are split. Input redirects (< << <<< and their operand) are reads: removed before the
arguments are read, never a target. A target is returned raw; paths.resolve() decides whether it resolves.

Cost: linear in the command's length, and bounded. Only the first RAW_MAX characters are read at all, and
after heredoc and here-string bodies are dropped only the first PARSE_MAX characters are parsed; a cut
command loses its last, possibly cut, segment and reports complete=False, so a cut never invents a target.

NOT covered (returns nothing for it): writes made inside an interpreter (python -c, node -e, a script
file), variables and substitutions as targets, and aliases beyond the table below. Callers that need to
know can count commands that mention a path but yield no target."""
import re
import shlex

RAW_MAX = 1024 * 1024   # characters read at all (heredoc bodies included)
PARSE_MAX = 64 * 1024   # characters parsed after heredoc and here-string bodies are dropped
SEPARATOR_RE = re.compile(r"&&|\|\||;|\||\n|&")
# one redirection: an optional fd (N, & or *), the operator, then its operand. Process substitution <( >( is not
# a redirection. The lookbehind keeps `2>&1`'s `&1` and the middle of `>>`/`<<` from matching twice.
REDIRECT_RE = re.compile(r"(?<![<>&])(?:[0-9]+|\*|&)?(<<<|<<-|<<|<>|<|>>|>\||>)(?!\()\s*"
						 r"(&?[0-9]+-?|\"[^\"]*\"|'[^']*'|[^\s;&|<>()]+)?")
WRITE_OPS = (">", ">>", ">|", "<>")
NULL_SINKS = {"/dev/null", "$null", "nul", "nul:"}
LEADING_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
LEADING_WORDS = ("&", ".", "sudo", "env", "command", "builtin")

DELETE_ALL = {"rm", "rmdir", "del", "erase", "rd", "unlink", "remove-item", "ri"}
WRITE_ALL = {"touch", "mkdir", "md", "tee", "truncate", "set-content", "sc", "add-content", "ac",
			 "out-file", "new-item", "ni", "clear-content", "clc"}
MOVE = {"mv", "move", "move-item", "mi", "rename-item", "rni", "ren", "rename"}
COPY = {"cp", "copy", "install", "ln", "xcopy", "copy-item", "cpi"}
IN_PLACE = {"sed", "perl"}
PS_PATH_PARAMS = {"-path", "-literalpath", "-lp", "-filepath", "-destination", "-newname", "-target"}
PS_VALUE_PARAMS = PS_PATH_PARAMS | {"-value", "-encoding", "-filter", "-include", "-exclude", "-itemtype",
									"-type", "-name", "-delimiter", "-inputobject", "-credential", "-stream",
									"-width", "-depth"}
BASH_VALUE_OPTS = {"-m", "--mode", "-o", "--owner", "-g", "--group", "-S", "--suffix", "-e", "--expression",
				   "-f", "--file"}


def mask_quotes(text):
	"""`text` with every character inside quotes replaced by 'x' (same length), so operators are found
	only where the shell sees them. An unclosed quote masks to the end."""
	out = []
	quote = None
	for ch in text:
		if quote:
			out.append(ch if ch == quote else "x")
			if ch == quote:
				quote = None
		elif ch in ("'", '"'):
			quote = ch
			out.append(ch)
		else:
			out.append(ch)
	return "".join(out)


def segments(command):
	"""The command split at unquoted ; && || | & and newlines (one regex pass)."""
	masked = mask_quotes(command)
	parts, start = [], 0
	for m in SEPARATOR_RE.finditer(masked):
		i = m.start()
		# `2>&1`, `<&3` and `&>` are redirections, not separators
		if m.group(0) == "&" and ((i > 0 and masked[i - 1] in "<>") or masked[i + 1:i + 2] == ">"):
			continue
		parts.append(command[start:i])
		start = m.end()
	parts.append(command[start:])
	return [p.strip() for p in parts if p.strip()]


def redirects(segment):
	"""([(operator, raw target), ...] written to, segment with every redirection removed). Input redirections
	(< << <<<) are reads: removed with their operand, never returned."""
	masked = mask_quotes(segment)
	targets, pieces, last = [], [], 0
	for m in REDIRECT_RE.finditer(masked):
		pieces.append(segment[last:m.start()])
		pieces.append(" ")
		last = m.end()
		op = m.group(1)
		if op not in WRITE_OPS or m.group(2) is None:
			continue
		raw = segment[m.start(2):m.end(2)].strip().strip('"').strip("'")
		if raw.startswith("&") or raw.lower() in NULL_SINKS:
			continue
		targets.append((op, raw))
	pieces.append(segment[last:])
	return targets, "".join(pieces)


def tokens(segment, powershell):
	"""shlex tokens (quotes removed; backslash is an escape in Bash only), or None if unbalanced."""
	try:
		lex = shlex.shlex(segment, posix=True)
		lex.whitespace_split = True
		lex.commenters = ""
		if powershell:
			lex.escape = ""
		return list(lex)
	except ValueError:
		return None


def verb_of(word):
	word = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
	return word[:-4] if word.endswith(".exe") else word


def split_commas(values):
	out = []
	for v in values:
		out.extend(x for x in v.split(",") if x.strip())
	return out


def ps_args(args):
	"""(named path values, positionals) for a PowerShell cmdlet's arguments."""
	named, positional, i = [], [], 0
	while i < len(args):
		a = args[i]
		low = a.lower().split(":", 1)[0] if a.startswith("-") else ""
		if low and not re.match(r"^-[0-9.]+$", a):
			if ":" in a:  # -Path:value
				if low in PS_PATH_PARAMS:
					named.append(a.split(":", 1)[1])
			elif low in PS_VALUE_PARAMS and i + 1 < len(args):
				if low in PS_PATH_PARAMS:
					named.append(args[i + 1])
				i += 1
		else:
			positional.append(a)
		i += 1
	return split_commas(named), split_commas(positional)


def bash_args(args):
	"""(positionals, value of -t/--target-directory) for a Bash command's arguments."""
	positional, target_dir, i = [], None, 0
	after_dashdash = False
	while i < len(args):
		a = args[i]
		if after_dashdash or not a.startswith("-") or a == "-":
			positional.append(a)
		elif a == "--":
			after_dashdash = True
		elif a in ("-t", "--target-directory") and i + 1 < len(args):
			target_dir = args[i + 1]
			i += 1
		elif a.startswith("--target-directory="):
			target_dir = a.split("=", 1)[1]
		elif a in BASH_VALUE_OPTS and i + 1 < len(args):
			i += 1
		i += 1
	return positional, target_dir


def segment_targets(segment, powershell):
	written, rest = redirects(segment)
	found = [(">", t, "write") if op != "<>" else ("<>", t, "write") for op, t in written]
	words = tokens(rest, powershell)
	if not words:
		return found
	first = 0  # skip VAR=x prefixes and wrappers by index: slicing the list each time is quadratic
	while first < len(words) and (LEADING_RE.match(words[first]) or words[first] in LEADING_WORDS):
		first += 1
	if first >= len(words):
		return found
	verb, args = verb_of(words[first]), words[first + 1:]
	is_ps = powershell or "-" in verb  # a Verb-Noun cmdlet is PowerShell syntax wherever it appears
	if is_ps:
		named, positional = ps_args(args)
	else:
		positional, target_dir = bash_args(args)
		named = [target_dir] if target_dir else []
	if verb in DELETE_ALL:
		found += [(verb, t, "delete") for t in named + positional]
	elif verb in WRITE_ALL:
		if verb in ("set-content", "sc", "add-content", "ac", "out-file") and not named:
			positional = positional[:1]  # positional 1 is -Value / -InputObject, not a path
		found += [(verb, t, "write") for t in (named or positional)]
	elif verb in MOVE:
		found += [(verb, t, "write") for t in named + positional]
	elif verb in COPY:
		if named:
			found += [(verb, t, "write") for t in named[-1:]]
		elif verb == "robocopy" and len(positional) >= 2:
			found.append((verb, positional[1], "write"))
		elif len(positional) >= 2:
			found.append((verb, positional[-1], "write"))
	elif verb == "robocopy" and len(positional) >= 2:
		found.append((verb, positional[1], "write"))
	elif verb in IN_PLACE and any(a == "-i" or a.startswith("-i") and not a.startswith("--") for a in args):
		rest_args = [a for a in args if not a.startswith("-")]
		scripted = any(a in ("-e", "--expression", "-f", "--file") for a in args)
		files = rest_args if scripted else rest_args[1:]
		found += [(verb + " -i", t, "write") for t in files]
	elif verb == "git" and positional and positional[0] in ("rm", "mv", "checkout", "restore"):
		kind = "delete" if positional[0] == "rm" else "write"
		found += [("git " + positional[0], t, kind) for t in positional[1:]]
	return found


HEREDOC_RE = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
HERESTRING_OPEN_RE = re.compile(r"@(['\"])\r?\n")


def strip_herestrings(command):
	"""The command with every PowerShell here-string (@'...'@, @"..."@) replaced by '' - one forward pass. An
	opener with no closer is left as it is, and so is every later opener of that quote (none can close)."""
	out, last, pos, dead = [], 0, 0, set()
	while len(dead) < 2:
		m = HERESTRING_OPEN_RE.search(command, pos)
		if not m:
			break
		quote = m.group(1)
		pos = m.end()
		if quote in dead:
			continue
		close = command.find("\n" + quote + "@", m.end() - 1)
		if close < 0:
			dead.add(quote)
			continue
		out.append(command[last:m.start()])
		out.append("''")
		last = pos = close + 3
	out.append(command[last:])
	return "".join(out)


def strip_heredocs(command):
	"""The command with Bash heredoc bodies and PowerShell here-string bodies removed: they are data fed to a
	program (often Python), and a '>' inside them is a comparison, not a redirect."""
	command = strip_herestrings(command)
	lines = command.split("\n")
	out, i = [], 0
	while i < len(lines):
		line = lines[i]
		out.append(line)
		m = HEREDOC_RE.search(line)
		i += 1
		if m:
			delim = m.group(2)
			while i < len(lines) and lines[i].strip() != delim:
				i += 1
			i += 1  # the delimiter line itself
	return "\n".join(out)


def parse(command, powershell=False):
	"""([(verb, raw target, kind)], complete) for every write and delete this command line makes that the table
	covers. complete is False when the command exceeded RAW_MAX or PARSE_MAX and only its head was parsed."""
	text = str(command or "")
	complete = len(text) <= RAW_MAX
	text = strip_heredocs(text[:RAW_MAX])
	if len(text) > PARSE_MAX:
		text, complete = text[:PARSE_MAX], False
	segs = segments(text)
	if not complete:
		segs = segs[:-1]  # the last segment may be cut mid-word: never judge a fragment
	out = []
	for seg in segs:
		out.extend(segment_targets(seg, powershell))
	return out, complete


def write_targets(command, powershell=False):
	"""[(verb, raw target, kind)] for every write and delete this command line makes that the table covers."""
	return parse(command, powershell)[0]
