#!/usr/bin/env python
"""
"""
from pygments.lexers.python import PythonLexer
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.layout.containers import Float, HSplit, VSplit
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import (
	Box,
	Button,
	Checkbox,
	Dialog,
	Frame,
	Label,
	MenuContainer,
	MenuItem,
	ProgressBar,
	RadioList,
	TextArea,
)

from rich import print


class TermApp:
	def ret_true():
		get_app().exit(result=True)
	def ret_false():
		get_app().exit(result=False)
	def do_exit():
		get_app().exit(result=True)
	def save_button():
		return Button(text="Save", handler=TermApp.ret_true)
	def discard_button():
		return Button(text="Discard", handler=TermApp.ret_false)
	def pyfield(title):
		return TextArea(lexer=PygmentsLexer(PythonLexer))
	def checkbox(title):
		return Checkbox(text=title)
	

	### Results
	results = {}

	def __init__(self, name):

		### results
		self.results = {}
		self.storage = {}

		## Style
		self.style = Style.from_dict(
			{
				"window.border": "#888888",
				"shadow": "bg:#222222",
				"menu-bar": "bg:#aaaaaa #888888",
				"menu-bar.selected-item": "bg:#ffffff #000000",
				"menu": "bg:#888888 #ffffff",
				"menu.border": "#aaaaaa",
				"window.border shadow": "#444444",
				"focused  button": "bg:#880000 #ffffff noinherit",
				# Styling for Dialog widgets.
				"button-bar": "bg:#aaaaff",
			}
		)

		###
		self.elements = \
		[
			VSplit(
				[
					Frame(body=Label(text="Left frame\ncontent")),
					Dialog(title="The custom window", body=Label("hello\ntest")),
					TermApp.pyfield("python"),
				],
				height=D(),
			),
			VSplit(
				[
					Frame(body=ProgressBar(), title="Progress bar"),
					Frame(
						title="Checkbox list",
						body=HSplit([TermApp.checkbox("hello"), TermApp.checkbox("hello")]),
					),
					Frame(title="Radio list", body=[]),
				],
				padding=1,
			),
			Box(
				body=VSplit([TermApp.save_button(), TermApp.discard_button()], align="CENTER", padding=3),
				style="class:button-bar",
				height=3,
			),
		]

		self.container = []

		# Global key bindings.
		self.bindings = KeyBindings()
		self.bindings.add("tab")(focus_next)
		self.bindings.add("s-tab")(focus_previous)




	def render(self):
		print(self.elements)
		self.container = HSplit(self.elements)
		print(self.container)
		self.app = Application(
			layout=Layout(self.container
			focused_element=TermApp.discard_button()
			),

			key_bindings=self.bindings,
			style=self.style,
			mouse_support=True,
			full_screen=True,
		)

	def run(self):
		result = self.app.run()
		print("You said: %r" % result)


if __name__ == "__main__":
	m = TermApp("Hello")
	m.render()
	x = m.run()
	print(x)