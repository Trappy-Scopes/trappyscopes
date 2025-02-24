from rich.table import Table
from rich.console import Console

class ExpNotebook:
	"""
	Note: Will only work when inherited by an `Experiment` object.
	A collection of facts from the events list - mostly the tag "user_note".
	"""

	def __init__(self):
		
		self.logs = {}     ## Inherited object
		self._notebook = None
	
	def _get_notebook(self):
		import pandas as pd
		notes = pd.DataFrame(self.logs["events"])
		notes = notes[notes.type == "user_note"]

		table = Table(title="Experiment notebook. All user notes:")

		table.add_column("Event number", justify="left", style="white", no_wrap=True)
		table.add_column("Exp time (s)", justify="left", style="cyan", no_wrap=True)
		table.add_column("User notes", style="green", justify="left", no_wrap=True)

		for index, row in notes.iterrows():
			table.add_row(str(index), f'{row["exptime"]:.3f}', str(row["note"]))

		console = Console()
		console.print(table)


	## The notebook property.
	notebook = property(
		fget=_get_notebook,
		doc="The notebook property."
	)

