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


## kwargs that hold live objects rather than parameters. read() writes its
## kwargs into the experiment event log, and exp.logs is dumped to YAML on every
## __save__(), so an object carrying a thread lock (any picamera2 encoder) raises
## `TypeError: cannot pickle '_thread.lock' object` -- on that save and on every
## save afterwards, long after the call that introduced it. Excluded from the log
## only; the action still receives the real object.
## See docs/notes/picamera2.md -- the proper fix belongs in Experiment.log().
NOLOG_KWARGS = ("encoder",)


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

		## False if any iteration failed. read() deliberately does not raise --
		## it is called from scheduled jobs, and ExpScheduler.loop has no
		## try/except, so an escaping exception kills the scheduler thread and
		## with it the rest of an overnight run. Callers check the return value
		## (and that the file exists) instead.
		ok = True

		for it in range(no_iterations):

			## Begin iteration
			try: ## Only used for iteration.
				local_filename = self.__process_filename__(filename=filename, iteration=it, **kwargs)
			except:
				local_filename = filename

			try:
				self.pre_action_callback(local_filename, iteration=it, **kwargs)
				self.actions[action](local_filename, iteration=it, **kwargs)
				Experiment.current.log(f"cam_acq_{action}",
					attribs={**{k: v for k, v in kwargs.items() if k not in NOLOG_KWARGS},
							 "iteration": it, "filename": local_filename})
				self.post_action_callback(local_filename, iteration=it, **kwargs)
			except Exception as e:
				## print_exception() takes no positional arguments -- it reads
				## the current exception from sys.exc_info(). Passing one raised
				## a TypeError from inside the handler, which replaced the real
				## error with "Console.print_exception() takes 1 positional
				## argument but 2 were given" and escaped read() entirely. Every
				## camera failure was masked that way.
				ok = False
				Camera.console.print_exception()
				log.error(f"Camera action '{action}' failed: {type(e).__name__}: {e}")
				Experiment.current.log("cam_acq_failed",
					attribs={"action": action, "filename": local_filename,
							 "iteration": it, "error": f"{type(e).__name__}: {e}"})
				


			## End of iteration ----------------------------
			if itr_delay_s:
				Experiment.current.delay("cam_acq_itr_delay", itr_delay_s)
			#ScopeAssembly.current.set_status("waiting")
			
			gc.collect()
			## End of iteration -----------------------------
		gc.collect()
		Experiment.current.log("cam_acq_finish", attribs={"filename": local_filename,
														  "ok": ok})
		return ok

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
	
	