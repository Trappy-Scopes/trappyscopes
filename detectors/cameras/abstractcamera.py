from abc import abstractmethod
import sys
import gc
from importlib import __import__

import logging as log
from rich.console import Console


# TS imports
#from hive.assembly import ScopeAssembly
from expframework.experiment import Experiment

from hive.detector import Detector
# Used to print exceptions properly.


class Camera(Detector):
	"""
	Abstract specialisation for TrappyScope Cameras.
	"""
	console = Console()


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
	def open(self):
		"""Open  the camera object."""
		pass

	
	@abstractmethod
	def close(self):
		"""Close the camera object"""
		pass


	@abstractmethod
	def preview(self, tsec=30):
		"""Create preview without writing to file."""
		pass

	def read(self, action, filename, tsec=1,
				no_iterations=1, itr_delay_s=0, **kwargs):
		"""
		Common capture protocol for cameras.
		"""
		
		## Pack all passed arguments
		if not kwargs:
			kwargs = {}
		locals_ = {**locals()}
		locals_.pop("self")
		locals_.pop("kwargs")
		locals_.pop("filename")
		kwargs.update(locals_)

		## ----- Sanity checks ------------
		action = action.lower().strip()
		if not action in self.actions:
			log.error(f"Invalid camera action: {action}")
			return False

		
		## ----- Indicate operation ----------
		#ScopeAssembly.current.set_status("waiting")		

		for it in range(no_iterations):

			## Begin iteration
			try: ## Only used for iteration.
				local_filename = self.__process_filename__(filename=filename, iteration=it, **kwargs)
			except:
				local_filename = filename

			try:
				self.pre_action_callback(local_filename, iteration=it, **kwargs)
				self.actions[action](local_filename, iteration=it, **kwargs)
				Experiment.current.log(f"cam_acq_{action}", attribs={**kwargs, "iteration": it, "filename":local_filename})
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
		gc.collect()
		Experiment.current.log("cam_acq_finish", attribs={"filename": local_filename})

	def __process_filename__(self, *args, **kwargs):
		"""
		Processes the given filename for specific modes of operation.
		"""
		filename = kwargs["filename"]
		if kwargs["no_iterations"] != 1:
			filename_stubs = filename.split(".")
			filename= f'{filename_stubs[0]}_itr{kwargs["iteration"]}.{filename_stubs[1]}'
			return filename
		else:
			return kwargs["filename"]
	
	