from textual.app import App, ComposeResult
from textual.widgets import Header, Footer



class TrappyApp(App[dict]):

	BINDINGS = [("d", "toggle_dark", "Toggle dark mode"), 
				("q", "quit", "Quit")]

