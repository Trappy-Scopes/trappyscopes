from rich import print
from rich.table import Table
from rich.console import Console

from core.idioms.clock import Clock

class ClockGroup:
	"""
	The set of all clocks in a given experiment.

	Note: Does not function if not inherited by an `Experiment` instance.
	Property wrapper around the clocks/timers of the Experiment Group.

	"""

	def __init__(self):
		self.expclock = None
		self.all_clocks = {}
		self.new_clock = lambda name: self._new_clock
	def _get_clocks(self):

		table = Table(title="All experiment clocks/timers")
		table.add_column("Clock name", justify="left", style="white", no_wrap=True)
		table.add_column("Elapsed (s)", justify="left", style="cyan", no_wrap=True)
		table.add_column("Offset (s)", style="dim", justify="left", no_wrap=True)

		## Main clock
		table.add_row("expclock", f"{self.expclock.time_elapsed():.5f}", 
								  f"{self.expclock.offset:.5f}", style="bold")
		
		for key, value in self.all_clocks.items():
			table.add_row(str(key), f"{value.time_elapsed():.5f}", f"{value.offset:.5f}")

		console = Console()
		console.print(table)

	def _new_clock(self, name):
		print(f"Initiating new clock/timer : {name}")
		self.all_clocks[name] = Clock()
		print(self.all_clocks[name])

	## The notebook property.
	clocks = property(
		fget = _get_clocks,
		fset = _new_clock,
		doc = "The group of clocks for this experiment."
	)