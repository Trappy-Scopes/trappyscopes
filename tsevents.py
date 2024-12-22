import datetime
import time
from copy import deepcopy

from sharing import Share
from core.bookkeeping.session import Session




class TSEvent(dict):
	"""
	A dictionary with a specialised constructor that represents an event
	across the Trappy-Scopes system. 
	"""
	def __init__(self, kind="event", attribs={}):
		self.update({
					"type"       : kind, 
					"scopeid"    : Share.scopeid,
					"mid"        : Share.mid,
			 		"sid"        : Session.current.name,
			 		"dt"         : datetime.datetime.now(),
			 		"sessiontime": Session.current.timer_elapsed(),
			  		"machinetime": time.time_ns(),
			  		"attribs"    : attribs
		   			})


	def sqlize(self):
		"""
		Process the dictionary for transmission, into a fixed attribute set.
		Does not return a TSEvent instance.
		"""
		tsevent_standard_keys = list(TSEvent().keys())

		all_ = deepcopy(self)
		processed = {k:v for k,v in all_.items() if k in tsevent_standard_keys}
		processed["attribs"].update({k:v for k,v in all_.items() 
									 if k not in tsevent_standard_keys})
		return processed

	def expand(self, data=None):
		"""
		Expand all attributes and give a single dictionary, instead of a nested one.
		This is the "inverse" operation of the the `sqlize` method.
		Does not return a TSEvent instance.
		"""
		if data == None:
			all_ = deepcopy(self)
		else:
			all_ = data

		all_.update(all_["attribs"])
		all_["attribs"] = {}
		return all_

		