from rich import print
from .basedevice import BaseDevice


class Detector():
	
	def __init__(self, detector):
		"""
		Credits: https://stackoverflow.com/a/1445289
		"""

		# Detector specific functions
		self.config = {}  ## Configuration for the detector system.
		self.actions = {} ## Different read actions that the detector can perform.
		                  ## i.e. the functional map of the different detector read modes.
		
		## Wrap the base object
		self.__class__ = type(detector.__class__.__name__,
							 (self.__class__, detector.__class__),
							  {})

		self.__dict__.update(detector.__dict__)

		if "read" not in self.__dict__.keys():
			self.read = lambda: print(f"{self.__repr__()} :: read: operation undefined.")
		if "configure" not in self.__dict__.keys():
			self.configure = lambda: print(f"{self.__repr__()} :: configure: operation undefined.")
		