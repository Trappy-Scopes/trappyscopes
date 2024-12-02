import logging as log
import yaml
import atexit
from copy import deepcopy

from rich.tree import Tree
from rich import print

from core.exceptions import TSDeviceNotRegistered
# API v1.0

from core.idioms.dicttools import absent_key_false

## Directory local imports
from .rpycserver import RpycServer
from .physical import PhysicalObject
from .processorgroups.linux import ProcessorGroup as LinuxProcessorGroup
from .actuator import Actuator
from .detector import Detector

class ScopeAssembly(RpycServer):
	"""
	A ScopeAssembly is a collection of peripheral objects, which are shared
	between different `abstracts`, that create virtual devices.

	Open questions
	--------------

	Does the assembly inherit a basedevice object?
	"""
	current = None
	def __init__(self, name, scopeconfig=None):
		"""
		Create a ScopAssembly object with a given name.
		"""
		self.name = name
		self.abs_name = "Undefined-mystery-detector"
		self.processors = []
		self.actuators = []
		self.detectors = []
		self.devices = {}

		self.all_rep = {"processors": self.processors, 
						"actuators" : self.actuators,
						"detectors" : self.detectors,
						"devices": self.devices}
		self.tree = {}

		self.main_pg = LinuxProcessorGroup("*")
		self.add_device("*", self.main_pg)
		self.processors.append("*")


		
		## Rewired configuration of the current machine
		if not scopeconfig:
			self.abstractions= {}
		else:
			self.abstractions = scopeconfig["abstractions"]
		ScopeAssembly.current = self

	@atexit.register
	def close():
		"""
		Call the close function on all attached devices.
		"""
		for device in ScopeAssembly.current.devices:
			if hasattr(ScopeAssembly.current.devices[device], "close"):
				try:
					ScopeAssembly.current.devices[device].close()
					log.info(f"Device closed by ScopeAssembly: {device}")
				except Exception as e:
					print(e)
					log.error(f"Device closure failed by ScopeAssembly: {device}")
		log.info(f"ScopeAssmebly {ScopeAssembly.current.name}` dissolved.")

	def __del__(self):
		ScopeAssembly.close()


	def start_server(self):
		"""
		Start the rpyc server.
		"""
		self.start_rpycserver()

	def open(self, scopeconfig, abstraction=None):
		"""
		Open the ScopeAssembly with a given scope configuration.
		The scopeconfig provides "expectations" for the attached
		peripherals.
		"""
		print("Scanning scope configuration...")
		print("[red] TODO: generalize this code.")


		camera = "cam"
		if "camera" in  scopeconfig["devices"].keys():
			camera = "camera"
		if camera in scopeconfig["devices"].keys():
			try:
				from detectors import cameras
				cam = cameras.Selector(scopeconfig["devices"][camera])
				self.add_device("cam", cam)
				print(cam)
			
			except Exception as e:
				log.error(f"Camera creation failed: {scopeconfig['camera']}")
				print(e)

		if "pico" in scopeconfig["devices"].keys():
			try:
				from .processorgroups.micropython import SerialMPDevice
				pico = SerialMPDevice(name="pico", connect=False)
				pico.auto_connect()
				log.info("Executing main.py on MICROPYTHON device.")
				try:
					pico.exec_main()
				except Exception as e:
					log.error("Main execution on pico failed!")
					print(e)
				log.info(pico)

			except Exception as e:
				print(e)
				log.error(f"Could not find a pico device. Creating a null object.")
				pico = None
				log.info(pico)
			self.add_device("pico", pico, description="Main microcontroller on Serial.")

			try:
				all_pico_devs = pico.exec_cleanup("print(Handshake.obj_list(globals_=globals()))")
				for d in all_pico_devs:
					self.add_device(d, pico.emit_proxy(d, pico), description="Pico peripheral.")
			except:
				print("pico: handshake failed!")

		self.abstractions = absent_key_false("abstraction", scopeconfig)
		if abstraction:
			return self.__abstraction__(abstraction)

	def __abstraction__(self, abstract):
		if abstract in self.abstractions:
			log.info(f"Selected abstraction: {abstract}. Asserting device list:")
			self.abs_name = abstract

			tree = deepcopy(self.abstractions[abstract])
			abstraction = self.abstractions[abstract]
			
			for device in abstraction:
				if not device in self.devices:
					if str(abstraction[device]).lower() == "physical":
						tree[device] = self.add_device(device, PhysicalObject(device))
					elif str(abstraction[device]).lower() == "physical-persistent":
						tree[device] = self.add_device(device, PhysicalObject(device, persistent=True))
					else:
						log.warning("Device creation not formalised yet into abstraction.")
			return tree
		else:
			log.error(f"Abstraction recipie `{abstract}` not found.")


	def __repr__(self):
		print(f"< Scope Assembly :: {len(self.devices)} devices :: {self.abs_name}>")

	def __call__(self, command):
		self.main_pg.shell(command)

	def __getitem__(self, device):
		if device in self.devices:
			return self.devices[device]
		else:
			raise KeyError(device)

	def __contains__(self, device):
		return device in self.devices

	def get_config(self):

		def read_config(device):
			if hasattr(device, "config"):
				return device.config
			elif hasattr(device, "__getstate__"):
				return device.__getstate__()
			else:
				log.warning(f"Device does not contain any configuration: {device}")
				return {}
		return {"processors": list(self.processors), 
				"actuators" : list(self.actuators),
				"detectors" : list(self.detectors),
				"devices": {key: read_config(device) for key, device 
							   in self.devices.items()}}


	#def __getattr__(self, device):
	#	if device in self.tree:
	#		return self.tree[device]
	#	else:
	#		raise TSDeviceNotRegistered(f"Device not found: {device}")


	def assert_device(self, device):
		"""
		Check whether the device is present, if not, raise an exception.
		"""
		if not device in self.tree:
			### ----- well something went wrong. Dealing with hardware
			raise TSDeviceNotRegistered(f"{device} :: assertion failed. Not registered to the machine.")
			## ------ sucks. Be a big boy and deal with it.
		else:
			return True

	def draw_tree(self):
		"""
		Draws the current tree.
		"""
		tree = Tree(f"{self.name} :: [blue bold]{self.abs_name}[default] running on [yellow]{self.main_pg.name}[default]")
		
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
		self.devices[name] = deviceobj
		setattr(self, name, deviceobj)
		return self.devices[name]
		#if type_ == None:
		#	self.descs[name] = "Mystery device does magical things!"
		#log.info(f"Added device to devicetree: {name} : {self.descs[name]}")




	def __device_type__(self, device):
		"""
		Autoscans and appends the device type to its respectie list.
		Assumes that the devices have an attribute called "name" and the name is unique.
		"""
		devmap = {"actuator": BaseActuator, "sensor": BaseSensor, "device": BaseDevice}
		desmap = {"actuator": self.actuators, "sensor": self.sensors, "basedevice": self.devices}

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
