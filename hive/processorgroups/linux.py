from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup
import multiprocessing
from subprocess import Popen

class ProcessorGroup(AbstractProcessorGroup):

	def __init__(self, name, processors=None):
		super().__init__(name)
		self.processes = []
		self.no_cores = 1
		if not processors:
			self.no_cores = multiprocessing.cpu_count()
	
	def shell(self, command):
		"""
		Launch the command on the shell.
		"""
		self.processes.append(Popen([command]))

	def __call__(self, command):
		self.shell(command)