"""AI Generated -- a touch-friendly terminal control deck for any device.

Written by Claude (Anthropic), 2026-10. Grown out of
scripts/toyexps/poseidon_deck_dummy.py; see docs/notes/poseidon_deck.pdf for
what the Poseidon deck built on it looks like.

A device gets a deck by inheriting Deckable and describing its controls:

	class Pump(Deckable):
		def deck_spec(self, d):
			d.panel("Pump 1", [
				d.toggle("Select", get=lambda: self.on, set=self.set_on),
				d.field("Rate", get=lambda: self.rate, set=self.set_rate, min=0),
				d.readout("Pos", lambda: f"{self.pos:.3f} mm")])
			d.choice("Step", ["0.1", "1.0"], get=..., set=...)
			d.pad("JOG +", tap=self.jog, hold=self.jog_tick)
			d.button("Zero", self.zero)
			d.key("s", self.stop)

	pump.deck()        # full screen; q / Esc / Ctrl-C return to the REPL

The deck holds no state of its own. Every widget reads through `get` and
writes through `set` on the device, so what is on screen is the device's
state, and whatever the device persists stays persisted.

Rules for the callables a spec hands in: they run on the UI thread, so they
must return quickly -- start a move, do not wait for it. Anything they raise
is caught, shown in the log strip, and never closes the deck.

Placement: consecutive calls of the same kind share a row (panels side by
side, choices on one line, pads in a row, buttons in a row); row_break()
starts a new one. Arrow keys walk the controls in that same screen order.

Validation of a field happens in three places: while typing (numeric fields
drop characters that cannot be part of a number), on commit (leaving the
field or Enter: type, min, max and check()), and in the device (whatever set()
raises is shown, and the field is restored from get()).
"""

import asyncio
import logging as log
import time

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, Frame, Label, TextArea


RESERVED_KEYS = {"q", "escape", "c-c", "up", "down", "left", "right", "tab", "s-tab",
				 "enter", " "}

STYLE = {
	"header": "bg:#1f5f8b #ffffff bold",
	"footer": "#888888",
	"rule": "#555555",
	"pad": "bg:#2d3a45 #ffffff bold",
	"pad.focused": "bg:#1f5f8b #ffffff bold",
	"pad.down": "bg:#e0a020 #000000 bold",
	"button.focused": "bg:#1f5f8b #ffffff",
	"field": "",
	"field.error": "bg:#8b1f1f #ffffff",
	"log.error": "#ff6060",
	"log.info": "",
}

NUMERIC_CHARS = set("0123456789.-+eE")


## ----------------------------------------------------------------- widgets
class _Widget:
	focusables = ()		## windows the arrow keys can land on, left to right

	def sync(self):
		"""Refresh what is shown from the device; called before every render."""


class Toggle(_Widget):
	def __init__(self, deck, label, get, set):
		self.deck, self.label, self.get, self.set = deck, label, get, set
		self.button = Button(self._text(), handler=self._flip, width=11)
		self.container = VSplit([Label(label, width=9), self.button])
		self.focusables = (self.button.window,)

	def _value(self):
		return bool(self.deck.safe(self.get, default=False))

	def _text(self):
		return "■ on" if self._value() else "□ off"

	def _flip(self):
		self.deck.call(f"{self.label} -> {not self._value()}", self.set, not self._value())

	def sync(self):
		self.button.text = self._text()


class Cycle(_Widget):
	"""One button stepping through its options -- stands in for a dropdown."""

	def __init__(self, deck, label, options, get, set, width=16):
		self.deck, self.label, self.options, self.get, self.set = deck, label, list(options), get, set
		self.button = Button(self._text(), handler=self._next, width=width)
		self.container = VSplit([Label(label, width=9), self.button])
		self.focusables = (self.button.window,)

	def _text(self):
		return f"{self.deck.safe(self.get, default='?')} ▾"

	def _next(self):
		current = self.deck.safe(self.get)
		i = self.options.index(current) + 1 if current in self.options else 0
		value = self.options[i % len(self.options)]
		self.deck.call(f"{self.label} = {value}", self.set, value)

	def sync(self):
		self.button.text = self._text()


class Choice(_Widget):
	"""A row of options with one selected; placed on its own line."""

	def __init__(self, deck, label, options, get, set):
		self.deck, self.label, self.options, self.get, self.set = deck, label, list(options), get, set
		self.buttons = [Button(self._text(o), handler=self._picker(o), width=len(str(o)) + 6)
						for o in self.options]
		self.focusables = tuple(b.window for b in self.buttons)
		self.container = VSplit([Label(f" {label}", width=len(label) + 2)] + self.buttons)

	def _text(self, option):
		return ("● " if option == self.deck.safe(self.get) else "  ") + str(option)

	def _picker(self, option):
		return lambda: self.deck.call(f"{self.label} = {option}", self.set, option)

	def sync(self):
		for button, option in zip(self.buttons, self.options):
			button.text = self._text(option)


class Field(_Widget):
	"""A single-line input, validated on typing, on commit and by the device."""

	def __init__(self, deck, label, get, set, type=float, min=None, max=None,
				 check=None, width=10, fmt=None):
		self.deck, self.label, self.get, self.set = deck, label, get, set
		self.type, self.min, self.max, self.check = type, min, max, check
		self.fmt = fmt or (lambda v: f"{v:g}" if isinstance(v, float) else str(v))
		self.error = None
		self._filtering = False
		self.area = TextArea(text=self._shown(), multiline=False, width=width)
		self.area.window.style = lambda: "class:field.error" if self.error else "class:field"
		self.area.buffer.on_text_changed += self._filter
		self.container = VSplit([Label(label, width=9), self.area])
		self.focusables = (self.area.window,)

	def _shown(self):
		value = self.deck.safe(self.get, default=None)
		return "?" if value is None else self.fmt(value)

	def _filter(self, buf):
		if self._filtering or self.type not in (int, float):
			return
		allowed = NUMERIC_CHARS if self.type is float else NUMERIC_CHARS - set(".eE")
		clean = "".join(c for c in buf.text if c in allowed)
		if clean != buf.text:
			self._filtering = True
			pos = buf.cursor_position - (len(buf.text) - len(clean))
			buf.text = clean
			buf.cursor_position = max(0, min(pos, len(clean)))
			self._filtering = False

	def sync(self):
		focused = get_app().layout.current_window is self.area.window
		if not focused and self.error is None:
			text = self._shown()
			if text != self.area.text:
				self._filtering = True
				self.area.text = text
				self._filtering = False

	def validate(self, text):
		"""The parsed value, or raise ValueError with a reason."""
		try:
			value = self.type(text.strip())
		except (TypeError, ValueError):
			raise ValueError(f"not a valid {self.type.__name__}: {text!r}")
		if self.min is not None and value < self.min:
			raise ValueError(f"{value} is below the minimum {self.min}")
		if self.max is not None and value > self.max:
			raise ValueError(f"{value} is above the maximum {self.max}")
		if self.check is not None:
			verdict = self.check(value)
			if isinstance(verdict, tuple):
				ok, why = verdict
			else:
				ok, why = bool(verdict), "rejected by check()"
			if not ok:
				raise ValueError(why)
		return value

	def commit(self):
		text = self.area.text
		if text == self._shown() and self.error is None:
			return True
		try:
			value = self.validate(text)
		except ValueError as err:
			self.error = str(err)
			self.deck.log(f"{self.label}: {err}", "error")
			return False
		if self.deck.call(f"{self.label} = {value}", self.set, value):
			self.error = None
			self._filtering = True
			self.area.text = self._shown()		## the device's own formatting
			self._filtering = False
			return True
		## the device refused it: show the device's value again
		self.error = None
		self.sync()
		return False


class Readout(_Widget):
	def __init__(self, deck, label, fn):
		self.container = Label(lambda: f"{label:<7}{deck.safe(fn, default='?')}")


class Rule(_Widget):
	def __init__(self):
		self.container = Window(height=1, char="─", style="class:rule")


class _PadControl(FormattedTextControl):
	"""Takes the raw mouse DOWN / UP anywhere in the pad, not only on its text."""

	def __init__(self, pad):
		super().__init__(pad._text, focusable=True)
		self.pad = pad

	def mouse_handler(self, ev):
		if ev.event_type == MouseEventType.MOUSE_DOWN:
			self.pad._down()
			return None
		if ev.event_type == MouseEventType.MOUSE_UP:
			self.pad._up()
			return None
		return NotImplemented


class Pad(_Widget):
	"""A big touch target. A tap calls tap(); a press held longer than
	deck.hold_delay calls hold() every deck.tick until release (or until
	deck.hold_limit, if the terminal never reports the release)."""

	def __init__(self, deck, label, tap=None, hold=None, hint="", height=3):
		self.deck, self.label, self.tap_fn, self.hold_fn, self.hint = deck, label, tap, hold, hint
		self.pressed = False
		self.ticks = 0
		self.t_down = 0.0
		self.window = Window(_PadControl(self), height=height, align=WindowAlign.CENTER,
							 style=self._style)
		self.container = self.window
		self.focusables = (self.window,)

	def _style(self):
		if self.pressed:
			return "class:pad.down"
		if get_app().layout.current_window is self.window:
			return "class:pad.focused"
		return "class:pad"

	def _text(self):
		return [("", f"\n{self.label}\n{self.hint}")]

	def press(self):
		"""Enter / Space on a focused pad: one tap."""
		if self.tap_fn:
			self.deck.call(self.label, self.tap_fn)

	def _down(self):
		if self.deck.held is not None and self.deck.held is not self:
			self.deck.held.release("another pad pressed")
		self.deck.held = self
		self.pressed, self.ticks, self.t_down = True, 0, time.time()
		self.deck.pointer = f"DOWN on {self.label}"
		if self.hold_fn:
			get_app().create_background_task(self._repeat())

	def _up(self):
		self.deck.pointer = f"UP on {self.label}"
		if not self.pressed:
			return
		held = time.time() - self.t_down
		self.pressed = False
		self.deck.held = None
		if self.ticks == 0:
			self.press()
		else:
			self.deck.log(f"{self.label}: held {held:.1f}s ({self.ticks} ticks)")

	def release(self, why):
		if self.pressed:
			self.pressed = False
			self.deck.held = None
			self.deck.log(f"{self.label}: hold stopped ({why})")

	async def _repeat(self):
		await asyncio.sleep(self.deck.hold_delay)
		while self.pressed:
			if time.time() - self.t_down > self.deck.hold_limit:
				self.release(f"no release reported after {self.deck.hold_limit:.0f}s")
				break
			self.ticks += 1
			if not self.deck.call(None, self.hold_fn):
				self.release("hold action failed")
				break
			get_app().invalidate()
			await asyncio.sleep(self.deck.tick)


## -------------------------------------------------------------------- deck
class Deck:
	"""Builder and runner for one control deck. See the module docstring."""

	def __init__(self, title="Deck", status=None, hold_delay=0.25, tick=0.1,
				 hold_limit=15.0, refresh=0.2, log_lines=4):
		self.title = title
		self.status = status
		self.hold_delay, self.tick, self.hold_limit = hold_delay, tick, hold_limit
		self.refresh = refresh
		self.log_lines = log_lines
		self.history = []
		self.pointer = "no pointer events yet"
		self.held = None
		self._rows = []				## [kind, [items]]
		self._break = False
		self._widgets = []
		self._keys = []
		self._t0 = time.time()

	## -- error-safe calls --------------------------------------------------
	def safe(self, fn, default=None):
		"""fn() for display; a failure shows as `default`, never as a crash."""
		try:
			return fn()
		except Exception:
			return default

	def call(self, what, fn, *args):
		"""Run a device action; log it, or log its error. True on success."""
		try:
			fn(*args)
		except Exception as err:
			self.log(f"{what or getattr(fn, '__name__', 'action')}: {err}", "error")
			return False
		if what:
			self.log(what)
		return True

	def log(self, text, level="info"):
		entry = {"t": round(time.time() - self._t0, 2), "level": level, "text": text}
		self.history.append(entry)
		(log.warning if level == "error" else log.debug)(f"deck {self.title}: {text}")

	## -- widget factories (not placed) -------------------------------------
	def toggle(self, label, get, set):
		return self._keep(Toggle(self, label, get, set))

	def cycle(self, label, options, get, set, width=16):
		return self._keep(Cycle(self, label, options, get, set, width))

	def field(self, label, get, set, type=float, min=None, max=None, check=None,
			  width=10, fmt=None):
		return self._keep(Field(self, label, get, set, type, min, max, check, width, fmt))

	def readout(self, label, fn):
		return self._keep(Readout(self, label, fn))

	def rule(self):
		return self._keep(Rule())

	## -- placement -----------------------------------------------------------
	def panel(self, title, rows):
		self._place("panel", (title, list(rows)))

	def choice(self, label, options, get, set):
		return self._place("choice", self._keep(Choice(self, label, options, get, set)))

	def pad(self, label, tap=None, hold=None, hint=""):
		return self._place("pad", self._keep(Pad(self, label, tap, hold, hint)))

	def button(self, label, fn):
		b = Button(label, handler=lambda: self.call(label, fn), width=len(label) + 4)
		self._place("button", b)
		return b

	def key(self, key, fn, help=None):
		if key in RESERVED_KEYS:
			raise ValueError(f"{key!r} is reserved by the deck (navigation or exit).")
		self._keys.append((key, fn, help or key))

	def row_break(self):
		self._break = True

	def _keep(self, widget):
		self._widgets.append(widget)
		return widget

	def _place(self, kind, item):
		if self._rows and self._rows[-1][0] == kind and not self._break:
			self._rows[-1][1].append(item)
		else:
			self._rows.append([kind, [item]])
		self._break = False
		return item

	## -- building --------------------------------------------------------------
	def _build(self):
		body, grid = [], []
		exit_button = Button("Exit", handler=lambda: self._exit(), width=8)
		if not any(kind == "button" for kind, _ in self._rows):
			self._rows.append(["button", []])
		last_buttons = max(i for i, (kind, _) in enumerate(self._rows) if kind == "button")
		self._rows[last_buttons][1].append(exit_button)

		for kind, items in self._rows:
			if kind == "panel":
				frames, columns = [], []
				for title, widgets in items:
					frames.append(Frame(HSplit([w.container for w in widgets]), title=title))
					columns.append([win for w in widgets for win in w.focusables])
				body.append(VSplit(frames, padding=1))
				for i in range(max((len(c) for c in columns), default=0)):
					grid.append([c[i] for c in columns if i < len(c)])
			elif kind == "choice":
				body.append(VSplit([w.container for w in items], padding=3))
				grid.append([win for w in items for win in w.focusables])
			elif kind == "pad":
				body.append(Window(height=1))
				body.append(VSplit([w.container for w in items], padding=1))
				grid.append([w.window for w in items])
			elif kind == "button":
				body.append(Window(height=1))
				body.append(VSplit(items, padding=1))
				grid.append([b.window for b in items])

		header = Label(self._header_text, style="class:header")
		keys = " · ".join(f"{h}" for _, _, h in self._keys)
		footer = Label(" arrows move · enter/space press" + (f" · {keys}" if keys else "")
					   + " · q/Esc exit", style="class:footer")
		root = HSplit([header] + body + [
			Window(height=1, char="─", style="class:rule"),
			Window(FormattedTextControl(self._log_text), height=self.log_lines),
			footer])
		return root, [row for row in grid if row]

	def _header_text(self):
		status = self.safe(self.status, default="") if self.status else ""
		return f" {self.title}" + (f" · {status}" if status else "") + f"      pointer: {self.pointer}"

	def _log_text(self):
		out = []
		for entry in self.history[-self.log_lines:][::-1]:
			out.append((f"class:log.{entry['level']}", f" {entry['t']:8.2f}s  {entry['text']}\n"))
		return out or [("", " (nothing yet)")]

	## -- running -----------------------------------------------------------------
	def run(self):
		"""Take over the terminal until exit; returns the action history."""
		root, grid = self._build()
		fields = {id(w.area.window): w for w in self._widgets if isinstance(w, Field)}
		pads = {id(w.window): w for w in self._widgets if isinstance(w, Pad)}

		kb = KeyBindings()
		kb.add("tab")(focus_next)
		kb.add("s-tab")(focus_previous)
		for k in ("q", "escape", "c-c"):
			kb.add(k, eager=True)(lambda e: self._exit())
		for key, fn, help_ in self._keys:
			kb.add(key, eager=True)(lambda e, fn=fn, help_=help_: self.call(help_, fn))

		self._last_window = None

		def before_render(app):
			for w in self._widgets:
				try:
					w.sync()
				except Exception as err:		## a display bug must not kill the deck
					log.debug(f"deck sync failed: {err}")

		def after_render(app):
			## Commit a field the moment focus leaves it -- by keys or by mouse.
			current = app.layout.current_window
			last = self._last_window
			self._last_window = current
			if last is not None and last is not current and id(last) in fields:
				fields[id(last)].commit()

		focus = grid[0][0] if grid else None
		app = Application(layout=Layout(root, focused_element=focus),
						  key_bindings=merge_key_bindings([load_key_bindings(),
														   _grid_navigation(grid, fields, pads),
														   kb]),
						  style=Style.from_dict(STYLE), mouse_support=True, full_screen=True,
						  refresh_interval=self.refresh)
		app.ttimeoutlen = 0.05		## Esc exits promptly instead of waiting for a sequence
		app.before_render += before_render
		app.after_render += after_render
		self._fields = fields
		app.run()
		return self.history

	def _exit(self):
		app = get_app()
		current = app.layout.current_window
		field = getattr(self, "_fields", {}).get(id(current))
		if field is not None:
			field.commit()
		if self.held is not None:
			self.held.release("deck closed")
		self.log("exit")
		app.exit()


def _grid_navigation(grid, fields, pads):
	"""Arrow keys over the deck, same rules as core.idioms.formdialog:

	  Up / Down      move a row; the column keeps its relative position
	  Left / Right   move a column -- inside a field they move the cursor first
	                 and only step out at the edge
	  Enter          in a field: commit and move down; on a pad: tap it
	                 (buttons handle their own Enter)
	"""
	where = {id(w): (r, c) for r, row in enumerate(grid) for c, w in enumerate(row)}
	kb = KeyBindings()

	def here():
		return where.get(id(get_app().layout.current_window))

	def typing():
		return isinstance(get_app().layout.current_control, BufferControl)

	def go(r, c, from_width):
		if not 0 <= r < len(grid):
			return
		width = len(grid[r])
		if from_width > 1 and width > 1:
			c = round(c * (width - 1) / (from_width - 1))
		target = grid[r][min(c, width - 1)]
		get_app().layout.focus(target)
		if isinstance(target.content, BufferControl):
			buf = target.content.buffer
			buf.cursor_position = len(buf.text)

	def vertical(step):
		def handler(event):
			at = here()
			if at:
				go(at[0] + step, at[1], len(grid[at[0]]))
		return handler

	kb.add("up")(vertical(-1))
	kb.add("down")(vertical(+1))

	@kb.add("left")
	def _(event):
		at, buf = here(), event.app.current_buffer
		if typing() and buf.cursor_position > 0:
			buf.cursor_left()
		elif at and at[1] > 0:
			go(at[0], at[1] - 1, 1)

	@kb.add("right")
	def _(event):
		at, buf = here(), event.app.current_buffer
		if typing() and buf.cursor_position < len(buf.text):
			buf.cursor_right()
		elif at and at[1] + 1 < len(grid[at[0]]):
			go(at[0], at[1] + 1, 1)

	on_pad = Condition(lambda: id(get_app().layout.current_window) in pads)

	@kb.add("enter", filter=on_pad)
	@kb.add(" ", filter=on_pad)
	def _(event):
		pads[id(event.app.layout.current_window)].press()

	@kb.add("enter", filter=Condition(typing))
	def _(event):
		field = fields.get(id(event.app.layout.current_window))
		if field is not None and not field.commit():
			return			## stay put on an invalid value
		at = here()
		if at:
			go(at[0] + 1, at[1], len(grid[at[0]]))

	return kb


class Deckable:
	"""Mixin: implement deck_spec(self, d) and the device gets .deck()."""

	def deck_spec(self, d):
		raise NotImplementedError(f"{type(self).__name__} has no deck_spec().")

	def deck_title(self):
		return getattr(self, "name", None) or type(self).__name__

	def deck_status(self):
		return ""

	def deck(self, **options):
		"""Open the control deck; q / Esc / Ctrl-C return to the REPL."""
		d = Deck(title=options.pop("title", None) or self.deck_title(),
				 status=options.pop("status", self.deck_status), **options)
		self.deck_spec(d)
		return d.run()
