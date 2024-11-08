from rich import print
from basedevice import BaseDevice


class Detector(BaseDevice):
	
	def __init__(self, detector):
		"""
		Credits: https://stackoverflow.com/a/1445289
		"""

		# Detector specific functions
		self.read = lambda: print(f"{self.__repr__()} :: read: operation undefined.")
		self.configure = lambda: print(f"{self.__repr__()} :: configure: operation undefined.")


		## Wrap the base object
		self.__class__ = type(detector.__class__.__name__,
								  (self.__class__, detector.__class__),
								  {})
		self.__dict__.update(detector.__dict__)
		

		