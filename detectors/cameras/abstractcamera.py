from abc import abstractmethod


import sys
import gc
from importlib import __import__
from rich.console import Console


# TS imports
from hive.assembly import ScopeAssembly
from experiment import Experiment


# Used to print exceptions properly.


class Camera:
	console = Console()

	def Selector(device, *args, **kwargs):
		device = device.strip().lower().replace(".py", "")

		try:
			module = __import__(f".{device}")
			return module.Camera(*args, **kwargs)
		except ImportError:
			log.error(f"Invalid camera device: {device}")
			return False

		### --- obsolete

		if device == "rpi_hq_picam2":
			from  rpi_hq_picam2 import Camera
			return Camera(*args, **kwargs)
		
		if device == "rpi_hq_picam1":
			from rpi_hq_picam1 import Camera
			return Camera(*args, **kwargs)
		
		if device == "alliedvision":
			from alliedvision import Camera
			return Camera(*args, **kwargs)

		if "null" in device:
			from nullcamera import Camera
			return Camera(*args, **kwargs)

		if device == "libcamera":
			from libcameraint import Camera
			return Camera(*args, **kwargs)

	@abstractmethod
	def pre_action_callbacks(self, *args, **kwargs):
		pass
	
	@abstractmethod
	def post_action_callbacks(self, *args, **kwargs):
		pass
	
	@abstractmethod
	def __init__(self):
		self.actions = {}
	
	@abstractmethod
	def open(self):
		pass

	
	@abstractmethod
	def close(self):
		pass

	
	@abstractmethod
	def configure(self, config_file):
		pass

	@abstractmethod
	def preview(self, tsec=30):
		pass


	@abstractmethod
	def state(self):
		pass


	def capture(self, action, filepath, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0, ts_frames=False, **kwargs):
		"""
		Common capture protocol for cameras.

		Optional kwargs: 
		1. ts_frames [bool] : timestamp each frame.
		"""
		
		## Pack all passed arguments
		kwargs = {**locals()}

		## ----- Sanity checks ------------
		action = action.lower().strip()
		if not action in self.actions:
			log.error(f"Invalid camera action: {action}")
			return False

		

		## ----- Indicate operation ----------
		ScopeAssembly.current.set_status("waiting")		


		## ------ Init delays ----------------
		if init_delay_s:
			Experiment.current.delay("cam_acq_init_delay", init_delay_s)


		for it in iterations:

			## Begin iteration
			local_filename = self.__process_filename__(iteration=it, **kwargs)
			ScopeAssembly.current.set_status("acq")
			

			try:
				self.pre_action_callbacks(local_filename, iteration=it, **kwargs)
				self.actions[action](local_filename, iteration=it, **kwargs)
				Experiment.current.log(f"cam_acq_{action}", attribs={**kwargs, "iteration": it})
				self.post_action_callbacks(local_filename, iteration=it, **kwargs)
			except Exception as e:
				Camera.console.print_exception(e)
				log.error("[green] EXCEPTION HANDLED [default] Exception caught in Camera.capture method.")
				


			## End of iteration ----------------------------
			if itr_delay_s:
				Experiment.current.delay("cam_acq_itr_delay", itr_delay_s)
			ScopeAssembly.current.set_status("waiting")
			gc.collect()
			## End of iteration -----------------------------
		
		## End of Acquisition -------------------------------
		ScopeAssembly.current.set_status("standby")
		gc.collect()		

	def __process_filename__(self, *args, **kwargs):
		"""
		Processes the given filename for specific modes of operation.
		TODO: Add mechanisms for EID insertion.
		"""
		if kwargs["iterations"] != 1:
			filename_stubs = filename.split(".")
			filename= f'{filename_stubs[0]}_itr{kwargs["iteration"]}.{filename_stubs[1]}'
			return filename
		else:
			return kwargs["filename"]
	
	