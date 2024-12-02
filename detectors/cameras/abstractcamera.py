from abc import abstractmethod
import sys
import gc
from importlib import __import__

import logging as log
from rich.console import Console


# TS imports
#from hive.assembly import ScopeAssembly
from experiment import Experiment

from hive.detector import Detector
# Used to print exceptions properly.


class Camera:
	console = Console()

	def Selector():
		"""
		Mecahnism for camera selection.
		"""
		from core.idioms.generic_selector import Selector as GSelector
		return GSelector(name, "/detectors/cameras", "Camera")

	@abstractmethod
	def pre_action_callback(self, *args, **kwargs):
		"""
		Perform before capture is complete.
		"""
		pass
	
	@abstractmethod
	def post_action_callback(self, *args, **kwargs):
		"""
		Perform after capture is complete.
		"""
		pass
	
	@abstractmethod
	def __init__(self):
		## A c
		self.actions = {}
		self.config = {}
	
	@abstractmethod
	def open(self):
		pass

	
	@abstractmethod
	def close(self):
		pass

	
	@abstractmethod
	def configure(self, config):
		pass

	@abstractmethod
	def preview(self, tsec=30):
		pass


	@abstractmethod
	def state(self):
		pass


	def read(self, action, filename, tsec=1,
				no_iterations=1, itr_delay_s=0, init_delay_s=0, ts_frames=False, **kwargs):
		"""
		Common capture protocol for cameras.

		Optional kwargs: 
		1. ts_frames [bool] : timestamp each frame.
		"""
		
		## Pack all passed arguments
		kwargs = {**locals()}
		kwargs.pop("self")
		kwargs.pop("kwargs")
		kwargs.pop("filename")

		## ----- Sanity checks ------------
		action = action.lower().strip()
		if not action in self.actions:
			log.error(f"Invalid camera action: {action}")
			return False

		

		## ----- Indicate operation ----------
		#ScopeAssembly.current.set_status("waiting")		


		## ------ Init delays ----------------
		if init_delay_s:
			Experiment.current.delay("cam_acq_init_delay", init_delay_s)


		for it in range(no_iterations):

			## Begin iteration
			local_filename = self.__process_filename__(filename=filename, iteration=it, **kwargs)
			#ScopeAssembly.current.set_status("acq")
			

			try:
				self.pre_action_callback(local_filename, iteration=it, **kwargs)
				self.actions[action](local_filename, iteration=it, **kwargs)
				Experiment.current.log(f"cam_acq_{action}", attribs={**kwargs, "iteration": it, "filename":filename})
				self.post_action_callback(local_filename, iteration=it, **kwargs)
			except Exception as e:
				Camera.console.print_exception(e)
				log.error("[green] EXCEPTION HANDLED [default] Exception caught in Camera.capture method.")
				


			## End of iteration ----------------------------
			if itr_delay_s:
				Experiment.current.delay("cam_acq_itr_delay", itr_delay_s)
			#ScopeAssembly.current.set_status("waiting")
			gc.collect()
			## End of iteration -----------------------------
		
		## End of Acquisition -------------------------------
		#ScopeAssembly.current.set_status("standby")
		gc.collect()		

	def __process_filename__(self, *args, **kwargs):
		"""
		Processes the given filename for specific modes of operation.
		TODO: Add mechanisms for EID insertion.
		"""
		filename = kwargs["filename"]
		if kwargs["no_iterations"] != 1:
			filename_stubs = filename.split(".")
			filename= f'{filename_stubs[0]}_itr{kwargs["iteration"]}.{filename_stubs[1]}'
			return filename
		else:
			return kwargs["filename"]
	
	