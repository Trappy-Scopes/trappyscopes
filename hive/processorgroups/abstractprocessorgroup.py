from abc import abstractmethod

class ProcessorGroup:

	def __init__(self, name):
		self.name = name

	@abstractmethod
	def exec(self, command):
		pass

	@abstractmethod
	def shell(self, command):
		pass

	@abstractmethod
	def __call__(self, command):
		pass