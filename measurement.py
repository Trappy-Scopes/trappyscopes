from pprint import pformat
from config.common import Common
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print

class Measurement(dict):
	
	#####################
	idx = 0
	modalities = {}
	#####################


	def Mode(name, *args, **kwargs):
		kwargs["modality"] = name
		Measurement.modalities[name] = Measurement(*args, **kwargs)

	def Stream(key):
		mmt = Measurement.modalities[key].copy()
		return mmt

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