"""AI Generated -- a bordered, field-per-row form dialog.

Extracted from PhysicalObject.update() (hive/physical.py), which was the only
caller until MeasurementStream.input() needed the same widget. Rather than copy
sixty lines of prompt_toolkit a second time, the machinery lives here once and
both call it.

It wraps prompt_toolkit's `Dialog` -- the same widget behind its built-in
input_dialog / message_dialog -- rather than a bare full-screen form, so every
field is visible and editable at once. Tab / Shift+Tab (or the mouse) move
between fields.

This module knows nothing about PhysicalObjects, measurement streams or the
experiment framework. It takes rows in and gives text back.
"""

import ast
import shutil

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit
from prompt_toolkit.widgets import Button, Dialog, Label, TextArea


def parse_value(raw):
	"""Interpret user input as a Python literal, falling back to the raw string.

	Tuples are converted to lists. `ast.literal_eval("54, 49, 36")` gives a
	tuple, and yaml.dump writes a tuple as !!python/tuple, which yaml.safe_load
	cannot construct -- so the value reads back as None (or raises) on any
	plain read of the experiment file. A list round-trips as a plain YAML
	sequence. This is not hypothetical: `cell_counts` records `counts` as a
	tuple today and that column is documented as unreadable without extended
	parsing.
	"""
	try:
		value = ast.literal_eval(raw)
	except (ValueError, SyntaxError):
		return raw
	return list(value) if isinstance(value, tuple) else value


class Field:
	"""One editable row.

	key      -- identifier returned in the result dict
	label    -- what the operator sees (defaults to key)
	value    -- pre-filled text
	suffix   -- shown after the input box, e.g. a unit
	editable -- False renders the value as a label with no input box
	"""

	def __init__(self, key, label=None, value="", suffix=None, editable=True):
		self.key = key
		self.label = label or key
		self.value = "" if value is None else str(value)
		self.suffix = suffix
		self.editable = editable


def form_dialog(title, fields, sections=None, ok_text="Save",
				cancel_text="Cancel", free_rows=0):
	"""Show the dialog and return {key: text} for the editable fields, or None
	if the operator cancelled.

	fields    -- [Field], in display order
	sections  -- optional {key: section_heading}; a heading is printed above
	             the first field carrying it
	free_rows -- number of blank `name = value` rows for ad-hoc fields. Only
	             for callers whose schema is genuinely open (PhysicalObject);
	             a declared schema should pass 0 so an ad-hoc key cannot break
	             the shape of everything already recorded.

	Returns raw strings. Interpreting them -- including deciding what a blank
	field means, which differs per caller -- is the caller's job.
	"""
	sections = sections or {}
	label_width = max([len(f.label) for f in fields] + [8]) + 2

	rows = []
	areas = {}
	seen_sections = set()

	for field in fields:
		heading = sections.get(field.key)
		if heading and heading not in seen_sections:
			seen_sections.add(heading)
			if rows:
				rows.append(Label(text=""))
			rows.append(Label(text=heading))

		if not field.editable:
			rows.append(VSplit([
				Label(text=f"{field.label:<{label_width}}", width=label_width),
				Label(text=f"{field.value}  (immutable)"),
			]))
			continue

		area = TextArea(text=field.value, multiline=False)
		areas[field.key] = area
		row = [Label(text=f"{field.label:<{label_width}}", width=label_width), area]
		if field.suffix:
			row.append(Label(text=f" {field.suffix}", width=len(field.suffix) + 1))
		rows.append(VSplit(row))

	free = []
	if free_rows:
		rows.append(Label(text=""))
		rows.append(Label(text="Add new fields:"))
		for _ in range(free_rows):
			key_area = TextArea(text="", multiline=False)
			val_area = TextArea(text="", multiline=False)
			free.append((key_area, val_area))
			rows.append(VSplit([key_area, Label(text=" = ", width=3), val_area]))

	result = {"saved": False}

	def save_handler():
		result["saved"] = True
		get_app().exit()

	def cancel_handler():
		result["saved"] = False
		get_app().exit()

	dialog = Dialog(
		title=title,
		body=HSplit(rows, padding=0),
		buttons=[Button(text=ok_text, handler=save_handler),
				 Button(text=cancel_text, handler=cancel_handler)],
		with_background=True,
	)

	bindings = KeyBindings()
	bindings.add("tab")(focus_next)
	bindings.add("s-tab")(focus_previous)
	## A form is a grid one column wide, so Up/Down walk the fields. The
	## "add new field" rows are two wide (name, value), so Left/Right step
	## between them there.
	ordered = [[areas[f.key]] for f in fields if f.editable and f.key in areas]
	ordered += [[key_area, val_area] for key_area, val_area in free]

	Application(
		layout=Layout(dialog),
		key_bindings=merge_key_bindings([load_key_bindings(), bindings,
										 _navigation_bindings(ordered)]),
		mouse_support=True,
		full_screen=True,
		cursor=CursorShape.BLINKING_BLOCK,
	).run()

	if not result["saved"]:
		return None

	values = {key: area.text for key, area in areas.items()}
	for key_area, val_area in free:
		new_key = key_area.text.strip()
		if new_key:
			values[new_key] = val_area.text
	return values


def _navigation_bindings(grid):
	"""Arrow-key movement over a grid of TextAreas.

	`grid` is a list of rows, each a list of TextArea (ragged rows are fine);
	a single-column form is just a grid one wide.

	  Up / Down      move a row, same column
	  Enter          same as Down -- the fields are single-line, so Enter has
	                 nothing else to do, and it is what a spreadsheet does
	  Left / Right   move the CURSOR inside the field, and only step to the
	                 neighbouring column once it is already at the edge

	Left/Right are conditional because binding them outright would break
	typing: you could no longer move within a value to fix one character.
	Edge-stepping is both what a spreadsheet does and the only version that
	leaves editing intact. Tab/Shift-Tab still walk every widget including
	the buttons, so the arrows never trap focus.
	"""
	position = {}
	for r, row in enumerate(grid):
		for c, area in enumerate(row):
			position[id(area.buffer)] = (r, c)

	bindings = KeyBindings()

	def focus(r, c):
		if not (0 <= r < len(grid)) or not grid[r]:
			return
		c = min(c, len(grid[r]) - 1)
		get_app().layout.focus(grid[r][c])

	def here():
		return position.get(id(get_app().current_buffer))

	@bindings.add("up")
	def _(event):
		at = here()
		if at:
			focus(at[0] - 1, at[1])

	@bindings.add("down")
	@bindings.add("enter")
	def _(event):
		at = here()
		if at:
			focus(at[0] + 1, at[1])

	@bindings.add("left")
	def _(event):
		buf = event.app.current_buffer
		at = here()
		if at and buf.cursor_position == 0 and at[1] > 0:
			focus(at[0], at[1] - 1)
		else:
			buf.cursor_left()

	@bindings.add("right")
	def _(event):
		buf = event.app.current_buffer
		at = here()
		if at and buf.cursor_position == len(buf.text) and at[1] + 1 < len(grid[at[0]]):
			focus(at[0], at[1] + 1)
		else:
			buf.cursor_right()

	return bindings


def page_size(chrome=12, minimum=5):
	"""How many grid rows fit the terminal, leaving room for the dialog's own
	furniture: borders, title, the header and unit rows, the rule, the footer
	and the button bar. Falls back to a sane number when the size is unknown
	(a pipe, a dumb terminal)."""
	try:
		lines = shutil.get_terminal_size().lines
	except Exception:
		return 20
	return max(minimum, lines - chrome)


def grid_dialog(title, columns, rows, row_labels=None, footer=None,
				has_prev=False, has_next=False,
				ok_text="Done", cancel_text="Cancel"):
	"""A spreadsheet-shaped dialog: one editable cell per row per column.

	columns    -- [(key, header, suffix)] -- suffix is a unit or dtype shown
	              under the header, or None
	rows       -- [{key: value}] -- one dict per row, missing keys render blank
	row_labels -- optional [str], the immutable left-hand label per row
	footer     -- optional line under the grid

	has_prev / has_next add paging buttons. Returns
	(action, [{key: text}]) where action is "done", "prev", "next" or
	"cancel"; the cell text is returned for every action except "cancel", so
	a caller can harvest the page before moving to the next one.

	Column widths are fixed from the widest value so the columns line up; a
	Dialog does not scroll horizontally, so the caller narrows `columns`
	rather than relying on a scrollbar.
	"""
	row_labels = row_labels or [str(i) for i in range(len(rows))]
	label_width = max([len(l) for l in row_labels] + [3]) + 2

	widths = {}
	for key, header, suffix in columns:
		longest = max([len(str(r.get(key, ""))) for r in rows] + [len(header)]
					  + [len(suffix or "")])
		widths[key] = min(max(longest + 2, 8), 24)

	head = [Label(text=" " * label_width, width=label_width)]
	sub = [Label(text=" " * label_width, width=label_width)]
	for key, header, suffix in columns:
		head.append(Label(text=f"{header:<{widths[key]}}", width=widths[key] + 2))
		sub.append(Label(text=f"{(suffix or ''):<{widths[key]}}", width=widths[key] + 2))

	body = [VSplit(head), VSplit(sub),
			Label(text="-" * (label_width + sum(widths[k] + 2 for k, _, _ in columns)))]

	areas = []
	for label, row in zip(row_labels, rows):
		cells = {}
		line = [Label(text=f"{label:<{label_width}}", width=label_width)]
		for key, _, _ in columns:
			value = row.get(key)
			area = TextArea(text="" if value is None else str(value),
							multiline=False, width=widths[key])
			cells[key] = area
			line.append(VSplit([area, Label(text="  ", width=2)]))
		areas.append(cells)
		body.append(VSplit(line))

	if footer:
		body.append(Label(text=""))
		body.append(Label(text=footer))

	result = {"action": "cancel"}

	def make(action):
		def handler():
			result["action"] = action
			get_app().exit()
		return handler

	buttons = []
	if has_prev:
		buttons.append(Button(text="< Prev", handler=make("prev")))
	if has_next:
		buttons.append(Button(text="Next >", handler=make("next")))
	buttons.append(Button(text=ok_text, handler=make("done")))
	buttons.append(Button(text=cancel_text, handler=make("cancel")))

	dialog = Dialog(
		title=title,
		body=HSplit(body, padding=0),
		buttons=buttons,
		with_background=True,
	)

	bindings = KeyBindings()
	bindings.add("tab")(focus_next)
	bindings.add("s-tab")(focus_previous)
	grid = [[cells[key] for key, _, _ in columns] for cells in areas]

	Application(
		layout=Layout(dialog),
		key_bindings=merge_key_bindings([load_key_bindings(), bindings,
										 _navigation_bindings(grid)]),
		mouse_support=True,
		full_screen=True,
		cursor=CursorShape.BLINKING_BLOCK,
	).run()

	if result["action"] == "cancel":
		return "cancel", None
	return result["action"], [{key: cells[key].text for key in cells}
							  for cells in areas]
