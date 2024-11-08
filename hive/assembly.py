import logging as log
import yaml

from rich.tree import Tree
from rich import print

from core.exceptions import TSDeviceNotRegistered
# API v1.0

from .rpycserver import RpycServer

class ScopeAssembly(RpycServer):
	"""
	A ScopeAssembly is a collection of peripheral objects, which are shared
	between different `abstracts`, that create virtual devices.

	Open questions
	--------------

	Does the assembly inherit a basedevice object?
	"""

	def __init__(self, name):

		self.name = name
		self.processors = []
		self.actuators = []
		self.detectors = []
		self.basedevices = {}

		self.all_rep = {"processors": self.processors, 
						"actuators" : self.actuators,
						"detectors" : self.detectors,
						"basedevice": self.basedevices}
		self.tree = {}
		self.network = None

		## Rewired configuration of the current machine
		self.abstracts= {}

	def startup(self):
		"""
		Start the rpyc server.
		"""
		self.start_rpycserver()

	def mount_all(self, scopeid):
		print("Scanning scope configuration...")

	
	def __getitem__(self, device):
		if device in self.devices:
			return self.basedevices[device]
		else:
			raise KeyError(device)

	def __contains__(self, device):
		return device in self.basedevices


	def assert_device(self, device):
		"""
		Check whether the device is present, if not, raise an exception.
		"""
		if not device in self.tree:
			### ----- well something went wrong. Dealing with hardware
			raise TSDeviceNotRegistered(f"{device} :: assertion failed. Not registered to the machine.")
			## ------ sucks. Be a big boy and deal with it.
	def draw_tree(self):
		"""
		Draws the current tree.
		"""
		tree = Tree(self.name)
		
		def add_dict_to_tree(tree, dictionary):
			for key, value in dictionary.items():
				if isinstance(value, dict):
					subtree = tree.add(f"[bold]{key}[/bold]")
					add_dict_to_tree(subtree, value)
				else:
					type_ = [list_name for list_name, lst in self.all_rep.items() if key in lst]
					tree.add(f"[yellow]{key}[default]: {value} :: [green] [[ {type_[0]} ]] [default]")

		## Start recursion
		add_dict_to_tree(tree, self.tree)

		print(tree)

	def add_device(self, name, deviceobj, description=None):
		"""
		Add device to the tree Machine tree.
		"""
		#type_ = self.device_type(deviceobj)
		
		self.tree[name] = deviceobj
		#self.descs[name] = type_
		self.basedevices[name] = deviceobj
		#if type_ == None:
		#	self.descs[name] = "Mystery device does magical things!"
		#log.info(f"Added device to devicetree: {name} : {self.descs[name]}")




	def __device_type__(self, device):
		"""
		Autoscans and appends the device type to its respectie list.
		Assumes that the devices have an attribute called "name" and the name is unique.
		"""
		devmap = {"actuator": BaseActuator, "sensor": BaseSensor, "basedevice": BaseDevice}
		desmap = {"actuator": self.actuators, "sensor": self.sensors, "basedevice": self.basedevices}

		for id_, devtype in devmap.items():
			if isinstance(device, devtype) or ("proxy" in device.__repr__().lower() 
												and
												id_     in device.__repr__().lower()):
				desmap[id_][device.name] = device
				log.info(f"{device.name} : is identified as a(n) {id_}.")
				return True
		log.error(f"{device.name} : could not be identified. Ignoring it.")
		return False


	#### -------------- #####
