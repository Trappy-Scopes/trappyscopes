from abcs.camera import AbstractCamera
from pprint import pprint

class Camera(AbstractCamera):

	# 1
	def __init__(self, *args, **kwargs):
		return

	# 2
	def open(self):
		return

	# 3
	def close(self):
		return

	def is_open(self):
		return True

	# 4
	def configure(self, config_file=None):
		return

	# 5
	def capture(self, action, filepath, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0):
		# Write a dummy file
		with open(filepath, "w"):
			pass 

	# 6
	def preview(self, tsec=30):
		return

	# 7
	def state(self):
		return

	#8
	def help(self):
		return

	# 9
	def __repr__(self):
		return "NullCamera - It does nothing!"

	
	