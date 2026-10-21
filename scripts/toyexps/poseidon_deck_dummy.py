"""
Dummy Poseidon control deck -- the layout of the planned PoseidonController.deck(),
with no hardware behind it. Every tap, hold, toggle and field value is recorded
and printed when you exit, so the layout and the touch handling can be checked
on the Pi's 7" screen before the real controller exists.

AI Generated -- written by Claude (Anthropic), 2026-10, as a mock-up for the
poseidon_pumps integration. Nothing here talks to a serial port; positions move
in a toy simulation only so the readouts have something to show.

Run it from the trappyscopes CLI (or plain `python` on this file):

	dummy_deck()          # opens the deck; Exit / q / Ctrl-C returns here
	deck_events           # the list of recorded (t, what, detail) tuples

The JOG pads are the part worth testing on the touchscreen: a short tap is one
step, a press held longer than 0.25 s repeats until release. The status line
shows every raw pointer DOWN / UP, so you can see whether your terminal and
touch driver actually report the release. If they never do, the hold stops by
itself after HOLD_LIMIT_S.

author: Yatharth Bhasin
date: 13-October-2026
licence: MIT Licence
"""

import asyncio
import time

from rich import print as rprint
from rich.table import Table

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


## Poseidon's own tables (SOFTWARE/poseidon_main.py), BD plastic syringes only.
SYRINGES = {"BD 1 mL": 17.34206347, "BD 3 mL": 57.88559215, "BD 5 mL": 112.9089185,
			"BD 10 mL": 163.539454, "BD 20 mL": 285.022957, "BD 30 mL": 366.0961536,
			"BD 60 mL": 554.0462538}
UNITS = ["mm/s", "mL/s", "mL/hr", "µL/hr"]
STEPS = ["0.01", "0.1", "1.0", "10.0"]
MODES = ["Incr.", "Abs."]

HOLD_DELAY_S = 0.25		## press shorter than this is a tap
HOLD_TICK_S = 0.1		## one jog increment per tick while held
HOLD_MM_PER_TICK = 0.05
HOLD_LIMIT_S = 15.0		## safety stop if the release is never reported

deck_events = []


class Recorder:
	"""Timestamped log of everything the deck does."""

	def __init__(self, sink):
		self.t0 = time.time()
		self.events = sink
		self.events.clear()
		self.pointer = "no pointer events yet"

	def __call__(self, event, **detail):
		self.events.append((round(time.time() - self.t0, 2), event, detail))

	def tail(self, n=4):
		lines = []
		for t, what, detail in self.events[-n:][::-1]:
			bits = " ".join(f"{k}={v}" for k, v in detail.items())
			lines.append(f" {t:7.2f}s  {what:<16} {bits}")
		return "\n".join(lines) or " (nothing yet)"


class _PadControl(FormattedTextControl):
	"""Takes the raw mouse DOWN/UP anywhere in the pad, not just on its text."""

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


class Pad:
	"""A big touch target: tap fires on_tap, a long press repeats on_tick."""

	active = None

	def __init__(self, rec, label, hint="", on_tap=None, on_tick=None, height=3):
		self.rec, self.label, self.hint = rec, label, hint
		self.on_tap, self.on_tick = on_tap, on_tick
		self.pressed = False
		self.ticks = 0
		self.t_down = 0.0
		self.window = Window(_PadControl(self), height=height, align=WindowAlign.CENTER,
							 style=self._style)

	def _style(self):
		if self.pressed:
			return "class:pad.down"
		if get_app().layout.current_window is self.window:
			return "class:pad.focused"
		return "class:pad"

	def _text(self):
		return [("", f"\n{self.label}\n{self.hint}")]

	def key_press(self):
		"""Enter/Space on a focused pad: always a single tap, never a hold."""
		self.rec("tap", pad=self.label.strip(), via="key")
		if self.on_tap:
			self.on_tap()

	def _down(self):
		if Pad.active is not None and Pad.active is not self:
			Pad.active.release("another pad pressed")
		Pad.active = self
		self.pressed, self.ticks, self.t_down = True, 0, time.time()
		self.rec.pointer = f"DOWN on {self.label.strip()}"
		if self.on_tick:
			get_app().create_background_task(self._repeat())

	def _up(self):
		self.rec.pointer = f"UP   on {self.label.strip()}"
		if not self.pressed:
			return
		held = time.time() - self.t_down
		self.pressed = False
		Pad.active = None
		if self.ticks == 0:
			self.rec("tap", pad=self.label.strip(), held_s=round(held, 2))
			if self.on_tap:
				self.on_tap()
		else:
			self.rec("hold-release", pad=self.label.strip(), held_s=round(held, 2),
					 ticks=self.ticks)

	def release(self, why):
		if self.pressed:
			self.pressed = False
			Pad.active = None
			self.rec("hold-stopped", pad=self.label.strip(), why=why, ticks=self.ticks)

	async def _repeat(self):
		await asyncio.sleep(HOLD_DELAY_S)
		while self.pressed:
			if time.time() - self.t_down > HOLD_LIMIT_S:
				self.release(f"no release after {HOLD_LIMIT_S:.0f}s")
				break
			self.ticks += 1
			self.on_tick()
			get_app().invalidate()
			await asyncio.sleep(HOLD_TICK_S)


class Choice:
	"""A row of buttons, one selected -- touch-friendlier than a RadioList."""

	def __init__(self, rec, name, options, current):
		self.rec, self.name, self.options = rec, name, options
		self.value = current
		self.buttons = [Button(self._label(o), handler=self._picker(o), width=len(o) + 6)
						for o in options]

	def _label(self, o):
		return ("● " if o == self.value else "  ") + o

	def _picker(self, o):
		def pick():
			if Pad.active:
				Pad.active.release("button pressed")
			self.value = o
			for b, opt in zip(self.buttons, self.options):
				b.text = self._label(opt)
			self.rec("select", what=self.name, value=o)
		return pick


class Cycle:
	"""One button that steps through its options -- stands in for a dropdown."""

	def __init__(self, rec, name, options, current, width=16):
		self.rec, self.name, self.options = rec, name, list(options)
		self.value = current
		self.button = Button(self._label(), handler=self._next, width=width)

	def _label(self):
		return f"{self.value} ▾"

	def _next(self):
		i = (self.options.index(self.value) + 1) % len(self.options)
		self.value = self.options[i]
		self.button.text = self._label()
		self.rec("select", what=self.name, value=self.value)


class DummyPump:
	"""One card: the settings the real SyringePump will take, and toy state."""

	def __init__(self, rec, n, syringe, units, rate, accel, amount, enabled=False):
		self.rec, self.n = rec, n
		self.enabled = enabled
		self.syringe = Cycle(rec, f"p{n}.syringe", SYRINGES, syringe)
		self.units = Cycle(rec, f"p{n}.units", UNITS, units)
		self.rate = TextArea(text=rate, multiline=False, width=10)
		self.accel = TextArea(text=accel, multiline=False, width=10)
		self.amount = TextArea(text=amount, multiline=False, width=10)
		self.toggle = Button(self._toggle_label(), handler=self._toggle, width=11)
		self.pos_mm = 0.0
		self.lo = self.hi = None
		self.state = "idle"

	## -- settings ---------------------------------------------------------
	def _toggle_label(self):
		return "■ on" if self.enabled else "□ off"

	def _toggle(self):
		self.enabled = not self.enabled
		self.toggle.text = self._toggle_label()
		self.rec("toggle", pump=self.n, enabled=self.enabled)

	def settings(self):
		return {"enabled": self.enabled, "syringe": self.syringe.value,
				"units": self.units.value, "rate": self.rate.text,
				"accel": self.accel.text, "amount": self.amount.text}

	## -- toy motion --------------------------------------------------------
	def area(self):
		return SYRINGES[self.syringe.value]

	def to_mm(self, amount):
		length = self.units.value.split("/")[0]
		if length == "mm":
			return amount
		if length == "mL":
			return amount * 1000.0 / self.area()
		return amount / self.area()		## µL == mm^3

	def move(self, delta_mm):
		target = self.pos_mm + delta_mm
		clamped = target
		if self.lo is not None:
			clamped = max(clamped, self.lo)
		if self.hi is not None:
			clamped = min(clamped, self.hi)
		if clamped != target:
			self.rec("limit-hit", pump=self.n, wanted=round(target, 3))
		self.pos_mm = clamped

	## -- readouts ----------------------------------------------------------
	def _lim(self):
		if self.lo is None and self.hi is None:
			return "unset"
		f = lambda v: "—" if v is None else f"{v:.2f}"
		return f"{f(self.lo)} ◂─▸ {f(self.hi)} mm"

	def card(self):
		row = lambda name, widget: VSplit([Label(name, width=9), widget])
		body = HSplit([
			VSplit([Label("Select", width=9), self.toggle]),
			row("Syringe", self.syringe.button),
			row("Units", self.units.button),
			row("Rate", self.rate),
			row("Accel", self.accel),
			row("Amount", self.amount),
			Window(height=1, char="─", style="class:rule"),
			Label(lambda: f"Pos    {self.pos_mm:8.3f} mm"),
			Label(lambda: f"Vol    {self.pos_mm * self.area():8.1f} µL"),
			Label(lambda: f"Limits {self._lim()}"),
			Label(lambda: f"State  {self.state}"),
		])
		return Frame(body, title=f"Pump {self.n}")


def dummy_deck():
	"""Open the dummy deck. Returns the recorded events after you exit."""
	rec = Recorder(deck_events)
	pumps = [DummyPump(rec, 1, "BD 10 mL", "µL/hr", "900.0", "50.0", "250.0", enabled=True),
			 DummyPump(rec, 2, "BD 1 mL", "mL/hr", "1.2", "5.0", "0.1"),
			 DummyPump(rec, 3, "BD 3 mL", "mm/s", "0.5", "5.0", "2.0")]
	step = Choice(rec, "step_mm", STEPS, "1.0")
	mode = Choice(rec, "mode", MODES, "Incr.")

	def selected():
		return [p for p in pumps if p.enabled]

	## -- actions (stand-ins for PoseidonController calls) -----------------
	def jog(sign):
		def tap():
			for p in selected():
				p.move(sign * float(step.value))
			rec("jog", dir="+" if sign > 0 else "-", step_mm=step.value,
				pumps=[p.n for p in selected()])

		def tick():
			for p in selected():
				p.move(sign * HOLD_MM_PER_TICK)
		return tap, tick

	def run():
		ps = selected()
		rec("run", mode=mode.value, pumps={p.n: p.settings() for p in ps})
		for p in ps:
			try:
				mm = p.to_mm(float(p.amount.text))
			except ValueError:
				rec("bad-value", pump=p.n, amount=p.amount.text)
				continue
			p.state = "▶ moving (dummy)"
			p.move(mm if mode.value == "Incr." else mm - p.pos_mm)

		async def settle():
			await asyncio.sleep(1.5)
			for p in ps:
				p.state = "idle"
			get_app().invalidate()
		get_app().create_background_task(settle())

	def stop():
		if Pad.active:
			Pad.active.release("STOP")
		for p in pumps:
			p.state = "idle"
		rec("stop")

	def send_settings():
		rec("send-settings", pumps={p.n: p.settings() for p in pumps})

	def per_pump(name, fn):
		def act():
			for p in selected():
				fn(p)
			rec(name, pumps={p.n: round(p.pos_mm, 3) for p in selected()})
		return act

	def set_lo(p): p.lo = p.pos_mm
	def set_hi(p): p.hi = p.pos_mm
	def zero(p):
		p.pos_mm = 0.0
		p.state = "idle"
	def goto_lo(p):
		if p.lo is not None:
			p.pos_mm = p.lo
	def goto_hi(p):
		if p.hi is not None:
			p.pos_mm = p.hi

	def exit_():
		rec("exit")
		get_app().exit()

	jm_tap, jm_tick = jog(-1)
	jp_tap, jp_tick = jog(+1)
	pad_list = [
		Pad(rec, "◀◀  JOG −", "(hold)", on_tap=jm_tap, on_tick=jm_tick),
		Pad(rec, "JOG +  ▶▶", "(hold)", on_tap=jp_tap, on_tick=jp_tick),
		Pad(rec, "RUN", "", on_tap=run),
		Pad(rec, "STOP", "", on_tap=stop),
		Pad(rec, "Send settings", "to board", on_tap=send_settings),
	]
	pads = VSplit([p.window for p in pad_list], padding=1)

	small_list = [
		Button("Zero here", handler=per_pump("zero", zero), width=13),
		Button("Limit ◂", handler=per_pump("set-limit-lo", set_lo), width=11),
		Button("Limit ▸", handler=per_pump("set-limit-hi", set_hi), width=11),
		Button("Go to ◂", handler=per_pump("goto-lo", goto_lo), width=11),
		Button("Go to ▸", handler=per_pump("goto-hi", goto_hi), width=11),
		Button("Exit", handler=exit_, width=8),
	]
	small = VSplit(small_list, padding=1)

	## The arrow-key grid, in screen order. Rows have different widths; moving
	## up/down keeps the same relative horizontal position.
	grid = [[p.toggle for p in pumps],
			[p.syringe.button for p in pumps],
			[p.units.button for p in pumps],
			[p.rate for p in pumps],
			[p.accel for p in pumps],
			[p.amount for p in pumps],
			step.buttons + mode.buttons,
			[p.window for p in pad_list],
			small_list]

	header = Label(lambda: " Poseidon Deck · DUMMY (no hardware) · 1/32 µstep"
						   f"      pointer: {rec.pointer}", style="class:header")
	root = HSplit([
		header,
		VSplit([p.card() for p in pumps], padding=1),
		VSplit([Label("Step mm", width=9)] + step.buttons
			   + [Label("   Mode", width=9)] + mode.buttons),
		Window(height=1),
		pads,
		Window(height=1),
		small,
		Window(height=1, char="─", style="class:rule"),
		Label(lambda: rec.tail(4)),
		Label(" arrows move · enter/space press · j/k jog · r run · s stop · q/Esc exit",
			  style="class:footer"),
	])

	kb = KeyBindings()
	kb.add("tab")(focus_next)
	kb.add("s-tab")(focus_previous)
	## The fields only take numbers, so the letter shortcuts are global: they
	## work even with the cursor inside a field, and q / s / Esc are never
	## swallowed by whatever has focus.
	kb.add("j", eager=True)(lambda e: jm_tap())
	kb.add("k", eager=True)(lambda e: jp_tap())
	kb.add("r", eager=True)(lambda e: run())
	kb.add("s", eager=True)(lambda e: stop())
	kb.add("q", eager=True)(lambda e: exit_())
	kb.add("escape", eager=True)(lambda e: exit_())
	kb.add("c-c")(lambda e: exit_())
	nav = _grid_navigation(grid, pad_list)

	style = Style.from_dict({
		"header": "bg:#1f5f8b #ffffff bold",
		"footer": "#888888",
		"rule": "#555555",
		"pad": "bg:#2d3a45 #ffffff bold",
		"pad.down": "bg:#e0a020 #000000 bold",
		"pad.focused": "bg:#1f5f8b #ffffff bold",
		"button.focused": "bg:#1f5f8b #ffffff",
	})

	app = Application(layout=Layout(root, focused_element=step.buttons[0]),
					  key_bindings=merge_key_bindings([load_key_bindings(), nav, kb]),
					  style=style, mouse_support=True, full_screen=True,
					  refresh_interval=0.2)
	app.ttimeoutlen = 0.05		## Esc exits promptly instead of waiting for a sequence
	app.run()

	_report(rec, pumps)
	return deck_events


def _grid_navigation(grid, pad_list):
	"""Arrow keys over the deck, the same rules as core.idioms.formdialog.

	  Up / Down      move a row; the column keeps its relative position, so
	                 moving from the 6-wide selector row lands on the nearest pad
	  Left / Right   move a column -- inside a text field they move the cursor
	                 first and only step out once it is at the edge
	  Enter          on a field: down a row; on a pad: tap it (buttons handle
	                 their own Enter)
	"""
	windows = [[getattr(cell, "window", cell) for cell in row] for row in grid]
	where = {id(w): (r, c) for r, row in enumerate(windows) for c, w in enumerate(row)}
	pads = {id(p.window): p for p in pad_list}
	kb = KeyBindings()

	def here():
		return where.get(id(get_app().layout.current_window))

	def go(r, c, from_width):
		if not 0 <= r < len(windows):
			return
		width = len(windows[r])
		if from_width > 1 and width > 1:
			c = round(c * (width - 1) / (from_width - 1))
		target = windows[r][min(c, width - 1)]
		get_app().layout.focus(target)
		if isinstance(target.content, BufferControl):
			buf = target.content.buffer
			buf.cursor_position = len(buf.text)		## append, don't prepend

	def typing():
		return isinstance(get_app().layout.current_control, BufferControl)

	@kb.add("up")
	def _(event):
		at = here()
		if at:
			go(at[0] - 1, at[1], len(windows[at[0]]))

	@kb.add("down")
	def _(event):
		at = here()
		if at:
			go(at[0] + 1, at[1], len(windows[at[0]]))

	@kb.add("left")
	def _(event):
		at = here()
		buf = event.app.current_buffer
		if typing() and buf.cursor_position > 0:
			buf.cursor_left()
		elif at and at[1] > 0:
			go(at[0], at[1] - 1, 1)

	@kb.add("right")
	def _(event):
		at = here()
		buf = event.app.current_buffer
		if typing() and buf.cursor_position < len(buf.text):
			buf.cursor_right()
		elif at and at[1] + 1 < len(windows[at[0]]):
			go(at[0], at[1] + 1, 1)

	on_pad = Condition(lambda: id(get_app().layout.current_window) in pads)

	@kb.add("enter", filter=on_pad)
	@kb.add(" ", filter=on_pad)
	def _(event):
		pads[id(event.app.layout.current_window)].key_press()

	@kb.add("enter", filter=Condition(typing))
	def _(event):
		at = here()
		if at:
			go(at[0] + 1, at[1], len(windows[at[0]]))

	return kb


def _report(rec, pumps):
	table = Table(title="Dummy deck — recorded selections", show_lines=False)
	table.add_column("t (s)", justify="right")
	table.add_column("event")
	table.add_column("detail")
	for t, what, detail in rec.events:
		table.add_row(f"{t:.2f}", what, ", ".join(f"{k}={v}" for k, v in detail.items()))
	rprint(table)

	final = Table(title="Final state")
	for col in ["pump", "enabled", "syringe", "units", "rate", "accel", "amount",
				"pos mm", "limits"]:
		final.add_column(col)
	for p in pumps:
		s = p.settings()
		final.add_row(str(p.n), str(s["enabled"]), s["syringe"], s["units"], s["rate"],
					  s["accel"], s["amount"], f"{p.pos_mm:.3f}", p._lim())
	rprint(final)


dummy_deck()
