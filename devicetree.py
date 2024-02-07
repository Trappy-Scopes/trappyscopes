#from device_state import device_perma_state
from pprint import pprint
import yaml
import json

class RPi():
	"""
	Placeholder object for RPi 4B.
	"""
	def __repr__(self):
		#return device_perma_state()
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
				|- cluster

	"""

	def __init__(self):
		print("DevNotes: ScopeAssembly TODO: Construct class")
		self.tree = {"rpi": None, 
					 "cam": "camera", 
					 "pico": {"lit": "light", "beacon" : "beacon", 
					 "tandh": "t&h sensor" }}
		self.descs = {}
		self.draw_tree()
		#pprint({"assembly": self.tree}, indent=4)

	def add_device(self, name, deviceobj, description=None):
		self.tree[name] = deviceobj
		self.descs[name] = description

		if description == None:
			self.descs[name] = "Mystery device does magical things!"

	def draw_tree(self):
		tree_str = json.dumps({"assembly": self.tree}, indent=4)
		tree_str = tree_str.replace("\n    ", "\n")
		tree_str = tree_str.replace('"', "")
		tree_str = tree_str.replace(',', "")
		tree_str = tree_str.replace("{", "")
		tree_str = tree_str.replace("}", "")
		tree_str = tree_str.replace("    ", " | ")
		tree_str = tree_str.replace("  ", " ")
		tree_str = tree_str[:-1] + " *" 

		print(tree_str)

	

