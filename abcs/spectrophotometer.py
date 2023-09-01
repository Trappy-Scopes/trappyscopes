from abcs import abstractmethod

class AbstractSpectrophotometer:


	def __init__(self):
		pass

	@abstractmethod
	def measure_and_read(self):
		pass

	@abstractmethod
	def state(self):
		return measure_and_read()

	@abstractmethod
	def set_dark_state(self):
		pass
		# Read dark state

	@abstractmethod
	def set_gain(self):
		pass

	def 