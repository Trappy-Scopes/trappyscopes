
from sharing import Share
from experiment import Experiment
from config.common import Common
from bookeeping.session import Session
import datetime
import time

from pprint import pformat
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print

class Measurement(dict):
	"""

	Every time you look at the system, you perturb it.
	--------------------------------------------------

	A measurment is a type of dictionary that is compatible with the
	dataframe (pandas) data-structure and gives all the necessary in-
	-formation necessary at every entry. This allows the user to com-
	-bine arbitrary number of experiments for analysis, **without any
	data filtering**.

	Measurement <modality>
		.
		|- type           (type="Experiment.Measurement")
		|- scopeid        (M1, M2, ...)
		|- mid            (Microscope uid)
		|- scriptid       (Defined for an experiment that is repeated multiple times)
		|- eid            (experiment id)
		|- expname        (experiment name)
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
	
	#####################
	idx = 0
	#####################


	def __init__(self, *args, **kwargs):


		self.update({
					"type"       : "measurement", 
					"scopeid"    : Share.scopeid,
					"mid"        : Share.mid, 
			 		"eid"        : Experiment.current.eid,
			 		"expname"    : Experiment.current.name,
					"scriptid"   : Experiment.current.scriptid,
			 		"sid"        : Session.current.name,
			 		"dt"         : datetime.datetime.now(),
			 		"sessiontime": Session.current.timer_elapsed(),
			  		"exptime"    : Experiment.current.timer_elapsed(),
			  		"machinetime": time.time_ns(),
			  		"measureid"  : Experiment.current.eid,
			   		"measureidx" : -1,
			   		"success"    : False
		   		})

		# Initial keys
		if len(args) != 0:
			init_dict = args[0]
			for key in init_dict:
				self[key] = init_dict[key]

		if len(kwargs) != 0:
			for key in kwargs:
				self[key] = kwargs[key]


	#def __repr__(self):
	def panel(self):
		print((Panel(Pretty(self.copy()), title=f"Measurement: {self['mid']} #{self['measureidx']}")))
	    
	def get(self):
		return self
	

if __name__ == "__main__":
	from measurement import Measurement
	m = Measurement(q=2, qq=123, m=234, o=1.123)