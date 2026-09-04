"""
Portable keyboard shortcuts for the interactive REPL.

Two prefixes, both under Esc (see git history / commit notes for why Esc and
not a Ctrl-chord -- keeps Ctrl+S free, works identically on Mac Terminal,
Linux, and a headless Raspberry Pi console with zero configuration):

  Esc, s            -> scope.draw_tree()      (device tree)
  Esc, s, Space     -> scope                  (the bare assembly object)
  Esc, s, <letter>  -> scope.<device>.        (trailing dot, NOT executed --
                                                Tab from here to see/complete
                                                whatever that device actually
                                                exposes, then finish the line
                                                and hit Enter yourself)

  Esc, e            -> exp                    (the current Experiment)
  Esc, e, s         -> exp.__save__()         (flush experiment.yaml)
  Esc, e, w         -> exp.write()            (open the user-note prompt)
  Esc, e, n         -> exp.note(              (left open -- type the note
                                                text and close it yourself)
  Esc, e, m         -> exp.mstreams           (measurement streams dict)
  Esc, e, o         -> exp = findexp()        (Experiment has no .open() --
                                                this is the closest real
                                                equivalent, see useractions.py)
  Esc, e, c         -> exp.close()            (close the current experiment)
  Esc, e, h         -> exp.schedule           (the ExpScheduler instance)

Why the scope devices insert-and-stop instead of executing immediately:
CPython's `site` module already wires real Tab-completion for any
interactive session (`rlcompleter`, driven by `readline`), and it completes
on the object's *actual* live attributes -- `ScopeAssembly.add_device` does
`setattr(self, name, device)`, so every mounted device really is an
attribute of `scope`. Landing on "scope.<device>." and letting Tab reveal
what's really there means new device methods show up for free, with no
hand-maintained action table to keep in sync. (Sanity-check this once: type
`scope.` then Tab at the live prompt and confirm real completions show up
before relying on it.)

`exp`'s four members don't need that: they're a small, stable, curated set
on the `Experiment` class itself (expframework/experiment.py), and one of
them (`note`) needs an argument, so it's left open with an unclosed paren
rather than auto-executed with nothing to log.

Usage (called from core/startup/__init__.py once `scope` is open):

	from utilities.keyboard_shortcuts import bind_shortcuts
	bind_shortcuts(scope)
"""

try:
	import readline
except ImportError:
	readline = None

from rich import print
from rich.table import Table


LEADER = r"\e"      # Esc, pressed and released.
SCOPE_KEY = "s"     # Esc, s -> "talking about scope"
EXP_KEY = "e"       # Esc, e -> "talking about the experiment"
BARE_KEY = " "      # ..., Space -> the bare object (scope prefix only)

SCOPE_TREE_CODE = "scope.draw_tree()"

# letter -> (code, newline). newline=True auto-executes; False leaves the
# chord open for you to keep typing (e.g. an argument) and hit Enter yourself.
EXP_MEMBERS = {
	"s": ("exp.__save__()", True),
	"w": ("exp.write()", True),
	"n": ("exp.note(", False),
	"m": ("exp.mstreams", True),
	"o": ("exp = findexp()", True),  # no exp.open() exists; closest real equivalent
	"c": ("exp.close()", True),
	"h": ("exp.schedule", True),
}

# Force a specific letter for a scope device, bypassing the automatic
# assignment below, e.g. {"trappyframe": "f"}.
CUSTOM_KEYS = {}

BOUND = {}  # populated by bind_shortcuts(): {(leader_key, ...subkeys): code}


def _assign_letters(device_names):
	"""
	Deterministically map each device to an unused letter, preferring the
	device's own initials so bindings stay mnemonic. Falls back to later
	letters in the name, then a-z/0-9, when initials collide.
	"""
	used = set(CUSTOM_KEYS.values())
	mapping = dict(CUSTOM_KEYS)

	for name in device_names:
		if name in mapping:
			continue
		letter = next((c for c in name.lower() if c.isalnum() and c not in used), None)
		if letter is None:
			letter = next((c for c in "abcdefghijklmnopqrstuvwxyz0123456789" if c not in used), None)
		if letter is None:
			print(f"[yellow]keyboard_shortcuts: ran out of letters, skipping device '{name}'[/yellow]")
			continue
		used.add(letter)
		mapping[name] = letter
	return mapping


def _bind(keyseq, code, newline):
	suffix = "\\n" if newline else ""
	readline.parse_and_bind(f'"{keyseq}": "{code}{suffix}"')
	return code


def bind_shortcuts(scope=None):
	"""
	Bind the scope and experiment prefixes described in the module
	docstring. Call this once the scope has been opened and its devices are
	mounted; safe to call again later to refresh the scope device list.
	"""
	if readline is None:
		print("[red]keyboard_shortcuts: readline is unavailable, skipping shortcut binding.[/red]")
		return

	if scope is None:
		from hive.assembly import ScopeAssembly
		scope = ScopeAssembly.current
	if scope is None:
		print("[red]keyboard_shortcuts: no ScopeAssembly to bind shortcuts for.[/red]")
		return

	BOUND.clear()
	scope_prefix = LEADER + SCOPE_KEY
	exp_prefix = LEADER + EXP_KEY

	## Scope prefix ------------------------------------------------------
	try:
		BOUND[(SCOPE_KEY,)] = _bind(scope_prefix, SCOPE_TREE_CODE, True)
		BOUND[(SCOPE_KEY, BARE_KEY)] = _bind(scope_prefix + BARE_KEY, "scope", True)
	except Exception as e:
		print(f"[red]keyboard_shortcuts: failed to bind scope prefix: {e}[/red]")

	device_names = list(scope.devices.keys())
	letter_of = _assign_letters(device_names)
	for name, letter in letter_of.items():
		if name not in device_names:
			continue  # a stale CUSTOM_KEYS entry for a device that isn't mounted
		try:
			BOUND[(SCOPE_KEY, letter)] = _bind(scope_prefix + letter, f"scope.{name}.", False)
		except Exception as e:
			print(f"[red]keyboard_shortcuts: failed to bind '{letter}' -> {name}: {e}[/red]")

	## Experiment prefix ---------------------------------------------------
	try:
		BOUND[(EXP_KEY,)] = _bind(exp_prefix, "exp", True)
	except Exception as e:
		print(f"[red]keyboard_shortcuts: failed to bind exp prefix: {e}[/red]")

	for letter, (code, newline) in EXP_MEMBERS.items():
		try:
			BOUND[(EXP_KEY, letter)] = _bind(exp_prefix + letter, code, newline)
		except Exception as e:
			print(f"[red]keyboard_shortcuts: failed to bind exp '{letter}': {e}[/red]")

	show_shortcuts()


def show_shortcuts():
	"""Print the currently bound shortcuts as a table."""
	table = Table(title="Keyboard shortcuts (Esc, ...)")
	table.add_column("Chord", style="cyan", no_wrap=True)
	table.add_column("Runs", style="green")

	def chord_label(keys):
		return "Esc, " + ", ".join("Space" if c == " " else c.upper() for c in keys)

	for keys, code in BOUND.items():
		table.add_row(chord_label(keys), code)

	print(table)
