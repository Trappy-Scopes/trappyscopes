from abc import abstractmethod

class AbstractCamera:

	# 1
	@abstractmethod
	def __init__(self):
		pass

	# 2
	@abstractmethod
	def open(self):
		pass

	# 3
	@abstractmethod
	def close(self):
		pass

	# 4
	@abstractmethod
	def configure(self, config_file):
		pass

	# 5
	@abstractmethod
	def capture(self, action, filepath, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0):
		pass

	# 6
	@abstractmethod
	def preview(self, tsec=30):
		pass

	# 7
	@abstractmethod
	def state(self):
		pass

	#8
	@abstractmethod
	def help(self):
		pass

	# 9
	@abstractmethod
	def __repr__(self):
		pass
	
	