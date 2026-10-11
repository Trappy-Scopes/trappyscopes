import ast
import os
import shelve

from core.idioms.formdialog import Field, form_dialog

from rich.console import Console
from rich.panel import Panel


class PhysicalObject(object):
	"""
	Metadata structure representing a physical object.
	"""

	def __init__(self, name, persistent=False, **kwargs):
		self.attribs = kwargs
		self.attribs["name"] = name
		self.persistent = persistent
		self.params = self.attribs  ## Aliased

		if persistent:
			## Lives under trappyverse/ (not directly in the home directory) so
			## that syncing the trappyverse folder to the config server (see
			## docs/notes/restructuring.md §7.2) actually backs this up. Moved
			## 2026-09-05 -- a shelve from before this change, sitting at
			## ~/<name>, is not picked up automatically; move it by hand under
			## trappyverse/state/ if it needs to survive.
			statedir = os.path.join(os.path.expanduser("~"), "trappyverse", "state")
			os.makedirs(statedir, exist_ok=True)
			state = shelve.open(os.path.join(statedir, name))

			## Current should override state
			for key, value in self.attribs.items():
				state[key] = value

			self.attribs = state
			self.params = self.attribs  ## Re-alias to the shelve-backed store

		if not "kind" in self.attribs:
			self.attribs["kind"] = "hive.PhysicalObject"

	def __getstate__(self):
		return {key: value for key, value in self.attribs.items()}

	def __close__(self):
		if self.persistent:
			self.attribs.sync()
			self.attribs.close()

	def __repr__(self):
		n = 3
		preview = list(self.attribs.items())[:n]
		preview_repr = ", ".join(f"{k!r}: {v!r}" for k, v in preview)
		suffix = "..." if len(self.attribs) > n else ""
		return f"< PhysicalObject{'-persistent' * self.persistent} :: {preview_repr}{suffix} >"

	def show(self):
		"""
		Pretty-print every field of this object as a rich.Panel.
		"""
		body = "\n".join(
			f"[bold cyan]{key}[/bold cyan] = [white]{value!r}[/white]"
			for key, value in self.attribs.items()
		)

		title = f"PhysicalObject{' · persistent' if self.persistent else ''}"
		panel = Panel(
			body,
			title=title,
			title_align="left",
			border_style="green" if self.persistent else "cyan",
			expand=False,
		)

		Console().print(panel)

	def __getitem__(self, key):
		return self.attribs[key]

	def __setitem__(self, key, value):
		self.attribs[key] = value

	@staticmethod
	def _parse_value(raw):
		"""
		Try to interpret user input as a Python literal (int, float, bool,
		list, dict, ...). Falls back to the raw string if that fails, so
		plain text like a motor's name still works.
		"""
		try:
			return ast.literal_eval(raw)
		except (ValueError, SyntaxError):
			return raw

	def update(self, new_field_slots=3):
		"""
		Edit this object's fields in a bordered dialog box -- the same
		`Dialog` widget that backs prompt_toolkit's built-in
		input_dialog / message_dialog / etc. (see
		https://python-prompt-toolkit.readthedocs.io/en/stable/pages/dialogs.html),
		rather than a bare full-screen form.

		Every field shows up at once, pre-filled and directly editable.
		Tab / Shift+Tab (or click, thanks to mouse support) move between
		fields. Clear a value entirely and press Save to delete that
		field. A few blank rows at the bottom let you add new fields
		(fill in both the name and the value). 'kind' is shown for
		reference but is immutable -- it has no input box here.

		Press Save to apply changes, or Cancel to discard them.

		If this object is persistent, changes are synced to disk
		automatically after a successful save.

		AI Generated -- the dialog machinery moved to
		core.idioms.formdialog when MeasurementStream.input() needed the
		same widget; this method keeps its own semantics (free-form keys,
		blank deletes) and only the rendering is shared. Behaviour here is
		unchanged.
		"""
		fields = []
		if "kind" in self.attribs:
			fields.append(Field("kind", value=self.attribs["kind"], editable=False))
		for key in self.attribs:
			if key != "kind":
				fields.append(Field(key, value=self.attribs[key]))

		raw = form_dialog(
			f"Update {self.attribs.get('name', 'PhysicalObject')}",
			fields, free_rows=new_field_slots)

		if raw is None:
			return

		for key, text in raw.items():
			if text.strip() == "":
				## A blank clears the field -- but only one that already
				## existed; a blank free row was never a field at all.
				if key in self.attribs:
					del self.attribs[key]
			else:
				self.attribs[key] = self._parse_value(text)

		if self.persistent:
			self.attribs.sync()
