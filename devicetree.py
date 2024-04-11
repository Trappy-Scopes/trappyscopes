#from device_state import device_perma_state
from pprint import pprint
from rich import print
import yaml
import json

class RPi():
	"""
	Placeholder object for RPi 4B.
	"""
	description = "Placeholder RPi 4B object."
	#def __repr__(self):
		#return device_perma_state()
	#	pass

class TSDeviceNotRegistered(Exception):
	pass

class ScopeAssembly:
	"""
	Its the collection of devices / independent peripherals with operational access.

	* cluster	
		|- trappy_scope
			|- rpi
				|- cam (camera)
			|- pico
				|- lit (lights)
				|- beacon
				|- sensors.tandh
				|- sensors.spectrometer
			|- remote-pico
				|- pump (peristatic pump)
			|- remote-pico
				|- alignment_device
			|- remote-pico
				|- cluster *

	"""

	def __init__(self):
		print("DevNotes: ScopeAssembly TODO: Construct class")
		self.tree = {"rpi": RPi()}
		self.descs = {}
		#self.draw_tree()
		#pprint({"assembly": self.tree}, indent=4)

	def __getattr__(self, device):
		if device in self.tree:
			return self.tree[device]
		else:
			raise TSDeviceNotRegistered(f"Device not found: {device}")

	def add_device(self, name, deviceobj, description=None):
		self.tree[name] = deviceobj
		self.descs[name] = description

		if description == None:
			self.descs[name] = "Mystery device does magical things!"

	def draw_tree(self):
		print({"assembly": self.tree})
		return
		tree_str = yaml.dump({"assembly": self.tree}, indent=4)
		tree_str = tree_str.replace("\n    ", "\n")
		tree_str = tree_str.replace('"', "")
		tree_str = tree_str.replace(',', "")
		tree_str = tree_str.replace("{", "")
		tree_str = tree_str.replace("}", "")
		tree_str = tree_str.replace("    ", " | ")
		tree_str = tree_str.replace("  ", " ")
		tree_str = tree_str[:-1] + " *" 

		print(tree_str)

	def reconnections(self, device="cam", callback_fn="is_open"):
		pass

