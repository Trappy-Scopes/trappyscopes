#from abcs.camera import AbstractCamera
from pprint import pprint

class Camera():

	# 1
	def __init__(self, *args, **kwargs):
		print("NullCamera initialised.")
		self.cam = None

	# 2
	def open(self):
		return

	# 3
	def close(self):
		return

	def is_open(self):
		return True

	# 4
	def configure(self, config_file=None, res=None, fps=None):
		return

	# 5
	def read(self, action, filepath, tsec=1,
				it=1, it_delay_s=0, init_delay_s=0):
		# Write a dummy file
		for i in range(it):
			if it == 1:
				with open(filepath, "w"):
					pass
			else:
				with open(f"{i}_{filepath}", "w"):
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


	def en_pre_timestamps(self, filename):
		return

	
	