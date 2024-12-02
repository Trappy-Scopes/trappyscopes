from rich import print
from .basedevice import BaseDevice


class Actuator(BaseDevice):
	
	def __init__(self, actuator):
		"""
		Credits: https://stackoverflow.com/a/1445289
		"""

		# Actuator specific functions
		self.read = lambda: print(f"{self.__repr__()} :: read: operation undefined.")
		self.write = lambda: print(f"{self.__repr__()} :: write: operation undefined.")
		self.configure = lambda: print(f"{self.__repr__()} :: configure: operation undefined.")


		## Wrap the base object
		self.__class__ = type(actuator.__class__.__name__,
								  (self.__class__, actuator.__class__),
								  {})
		self.__dict__.update(actuator.__dict__)
		

		