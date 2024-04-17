from pprint import pformat
from config.common import Common
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print

class Measurement(dict):
	"""
	A measurment is a type of dictionary that is compatible with the
	dataframe (pandas) data-structure and gives all the necessary in-
	-formation necessary at every entry. This allows the user to com-
	-bine arbitrary number of experiments for analysis, **without any
	data filtering**.

	Measurement <modality>
		.
		|- type (type="Experiment.Measurement")
		|- scopeid (M1, M2, ...)
		|- mid (Microscope uid)
		|- eid (experiment id)
		|- expname (experiment name)
		|- sid (session id)
		|- df (datetime)
		|- sessiontime (time elapsed in seconds since experiment)
		|- exptime     (total time of the experiment - sum of all sessions)
		|- machinetime (nanosecond tick - since epoch time)
		|- measureid  (epochtime/ measurement mode id - assigned by a MeasurementStream object)
		|- measureidx (measurement index - deafults to -1 : arbitrary sequence order)
		|- < statevar 1 > (duration_s, setup)
		|- < statevar 2 >
		:       :::
		|- < statevar n >
		|- < measurand 1 >
		|- < measurand 2 >
		:       :::
		|- < measurand n >
		|- <list-of-measurands>
		|- <list-of-statevars>
		+




	"""
	
	#####################
	idx = 0
	modalities = {}
	#####################


	def Mode(name, *args, **kwargs):
		kwargs["modality"] = name
		Measurement.modalities[name] = Measurement(*args, **kwargs)



	def __init__(self, *args, **kwargs):
		

		### Pre-defined keys
		self["mid"] = Measurement.idx
		Measurement.idx += 1
		self.idx = Measurement.idx

		self["experiment"] = None
		self["scope"] = Common.scopeid

		# Initial keys
		if len(args) != 0:
			init_dict = args[0]
			for key in init_dict:
				self[key] = init_dict[key]

		if len(kwargs) != 0:
			for key in kwargs:
				self[key] = kwargs[key]


	def panel(self):
		print(Panel(Pretty(self.copy()), title=f"Measurement: {self['mid']}"))

	def get(self):
		return self
	

if __name__ == "__main__":
	from measurement import Measurement
	m = Measurement(q=2, qq=123, m=234, o=1.123)