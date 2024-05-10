from numpy import nan as Nan
import datetime
import time
from copy import deepcopy

from sharing import Share
from experiment import Experiment, ExpEvent
from config.common import Common
from bookeeping.session import Session
from uid import uid
import logging as log
from terminalplot import *

from pandas import DataFrame, concat

from pprint import pformat
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print
from rich import pretty
from rich.table import Table

class Measurement(ExpEvent):
	"""

	Every time you look at the system, you perturb it.
	--------------------------------------------------

	A measurment is a type of dictionary that is compatible with the
	dataframe (pandas) data-structure and gives all the necessary in-
	-formation necessary for every entry. This allows the user to com-
	-bine arbitrary number of experiments for analysis, **without any
	data filtering**.

	Measurement <modality>
		.
		|- type           (type="Experiment.Measurement")
		|- scopeid        (M1, M2, ...)
		|- mid            (Microscope uid)
		|- scriptid       (Defined for an experiment that is repeated multiple times)
		|- eid            (experiment id)
		|- sid            (session id; for SingleSession experiments, it is the same as eid)
		|- df             (datetime)
		|- sessiontime    (time elapsed in seconds since experiment)
		|- exptime        (total time of the experiment - sum of all sessions)
		|- machinetime    (nanosecond tick - since epoch time)
		|- measureid      (epochtime/ measurement mode id - assigned by a MeasurementStream object)
		|- measureidx     (measurement index - deafults to -1 : arbitrary sequence order)
		|- success        (flag that must be set after measurement to indicate its completion)
		|- <statevar 1>   (duration_s, setup, exptype are common fields)
		|- <statevar 2>
		:       :::
		|- <statevar n>
		|- <measurand 1>
		|- <measurand 2>
		:       :::
		|- <measurand n>
		|- <list-of-measurands>
		|- <list-of-statevars>
		+
	"""



	def __init__(self, **kwargs):

		super().__init__()
		self.update({
					"type"         : "measurement",
			  		"measureid"    : Experiment.current.eid,
			   		"measureidx"   : 0,
			   		"success"      : None,
		   			})

		# Initial keys
		if len(kwargs) != 0:
			for key in kwargs:
				self[key] = kwargs[key]



	def panel(self):
		print((Panel(Pretty(self.copy()), title=f"Measurement: {self['mid']} #{self['measureidx']}")))
	    
	def get(self):
		return self
	


class MeasurementStream:
	"""
	Returns time adjusted copies of a measurement.
	"""
	def __init__(self, measurement={}, name=None):
		self.name = name
		self.datapoint = Measurement(**measurement)
		self.uid = uid()
		self.datapoint["measureid"] = self.uid
		self.datapoint["measureidx"] = -1

		self.df = DataFrame(columns=self.datapoint.keys())
		self.df.set_index("measureidx")
		self.readings = []

		self.detections = []
		self.measurements = []
		self.monitors = []

		self.auto_update_tables = False
		self.auto_update_explogs = False
		self.auto_update_df = False
		self.tables = {}


	def add_detection(self, key):
		self.detections.append(key)
		self.datapoint[key] = Nan
	
	def add_measurement(self, key):
		self.measurements.append(key)
		self.datapoint[key] = Nan
	
	def add_monitor(self, key):
		self.monitors.append(key)
		self.datapoint[key] = Nan


	def tabulate(self, *args, title=None):
		"""
		Create a tabulated view of the measurement stream with the provided keys.
		"""
		filtered_args = [arg for arg in args if arg in self.datapoint.keys()]
		if args != filtered_args:
			log.error("Missing keys passed to MeasurementStream.tabulate. Ignoring those keys.")

		table = Table(*filtered_args, title=f"Table {len(self.tables)}{f' : {title}'*bool(title)}")
		self.tables[tuple(args)] = table
		for i, key in enumerate(args):
			table.columns[i].style = f"color({i})"
		return table


	def plot(self, *args, title=None):
		Plotter.show()
	
	def __call__(self, **kwargs):
		self.readings.append(deepcopy(self.advance()))
		for k, v in dict(kwargs).items():
			self.readings[-1][k] = v
		
		## Tables ----------------------------------------
		if self.auto_update_tables:
			for tab in self.tables:
				row = []
				for key in tab:
					row.append(str(self.readings[-1][key]))
				self.tables[tab].add_row(*row)

		## Exp logs ---------------------------------------
		if self.auto_update_explogs and Experiment.current != None:
			Experiment.current.logs["results"].append(self.readings[-1])
			Experiment.current.__save__()

		## Dataframe update -------------------------------
		if self.auto_update_df:
			#self.df = pd.concat([pd.DataFrame([[1,2]], columns=df.columns), df], ignore_index=True)
			#self.df = concat([self.df, DataFrame(self.readings[-1].values())], ignore_index=True)
			self.df.loc[len(self.df)] = self.readings[-1]

	def measure(self, **kwargs):
		self.__call__(**kwargs)

	def advance(self, **kwargs):
		self.datapoint["sessiontime"] = Session.current.timer_elapsed()
		self.datapoint["exptime"]     = Experiment.current.timer_elapsed()
		self.datapoint["machinetime"] = time.time_ns()
		self.datapoint["measureidx"] = self.datapoint["measureidx"] + 1
		return self.datapoint
	
	def __repr__(self):
		return pretty.pretty_repr({"detections" : self.detections,
								   "measuremnts": self.measurements,
								   "monitoes"   : self.monitors,
								   "readings"   :self.readings})

	def panel(self):
		print((Panel(Pretty({"detections" : self.detections,
								   "measuremnts": self.measurements,
								   "monitoes"   : self.monitors,
								   "readings"   :self.readings}),
			title=f"Measurement Stream {f':: {self.name}'*(self.name!=None)}")))

	def screen(self, table):
		from rich.live import Live
		with Live(table, refresh_per_second=4, screen=True) as live:
			for _ in range(40):
				time.sleep(0.4)
				live.update(table)

	def plot(self, x, y, label=""):
		plt.cld()
		plt.plot(self.df[x], self.df[y], label=label)
		plt.xlabel(x)
		plt.ylabel(y)
		plt.title(f"Measurement Stream Plot{f':: {self.name}'*(self.name!=None)} :: {x}-{y}")
		plt.show()
