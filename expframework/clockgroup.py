from rich import print
from rich.table import Table
from rich.console import Console

from core.idioms.clock import Clock

class ClockGroup:
	"""
	Note: Does not function if not inherited by an `Experiment` instance.
	Property wrapper around the clocks/timers of the Experiment Group.
	"""

	def __init__(self):
		self.expclock = None
		self.timers = {}

	def _get_clocks(self):

		table = Table(title="All experiment clocks/timers")
		table.add_column("Clock name", justify="left", style="white", no_wrap=True)
		table.add_column("Elapsed (s)", justify="left", style="cyan", no_wrap=True)
		table.add_column("Offset (s)", style="dim", justify="left", no_wrap=True)

		## Main clock
		table.add_row("expclock", f"{self.expclock.time_elapsed():.5f}", f"{self.expclock.offset:.5f}", style="bold")
		
		for key, value in self.timers.items():
			table.add_row(key, f"{value.time_elapsed():.5f}", f"{value.offset:.5f}")

		console = Console()
		console.print(table)

	def _new_clock(self, name):
		print(f"Initiating new clock/timer : {name}")
		self.timers[name] = Clock()
		print(self.timers[name])

	## The notebook property.
	clocks = property(
		fget = _get_clocks,
		fset = _new_clock,
		doc = "The group of clocks for this experiment."
	)