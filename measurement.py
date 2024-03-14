from pprint import pformat
from config.common import Common
from rich.pretty import Pretty
from rich.panel import Panel

class Measurement(dict):
	
	idx = 0

	def __init__(self, *args, **kwargs):
		

		### Pre-defined keys
		self["mid"] = Measurement.idx
		Measurement.idx += 1

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

		self.idx = 1




	#def __str__(self):

	def __repr__(self):

		print(Panel(Pretty(super().__repr__()), title=f"Measurement: {self['mid']}"))


	#def __rich_repr__(self):
	#	prefix = f"Measuremnt: {self.idx}, "
	#	s = pformat(super().__repr__(), width=80-len(prefix))
	#	s.replace("\n", " "*len(prefix))
	#	s = s[1:-1]
	#	s = f"< {prefix} \n {' '*len(prefix)} {s} >"
	#	return s
	#	
	#	return Panel(super().__repr__())

	def get(self):
		return self

if __name__ == "__main__":
	from measurement import Measurement
	m = Measurement(q=2, qq=123, m=234, o=1.123)