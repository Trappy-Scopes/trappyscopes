from abc import abstractmethod

class Camera:

	# 1
	@abstractmethod
	def __init__(self):
		pass

	# 2
	@abstractmethod
	def init_cam(self):
		pass

	# 3
	@abstractmethod
	def deinit_cam(self):
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

	@abstractmethod
	def __repr__(self):
		pass
	