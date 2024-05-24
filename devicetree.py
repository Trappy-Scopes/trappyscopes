#from device_state import device_perma_state
from pprint import pprint
from rich import print
import yaml
import json
import logging as log


from sharing import Share
from yamlprotocol import YamlProtocol

import abcs #Abstract Base Classses

class RPi():
	"""
	Placeholder object for RPi 4B.
	"""
	description = "Placeholder RPi 4B object."
	def __init__(self, name, ip="localhost"):
		pass
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
		self.tree = {}
		self.descs = {}
		self.actuators = {}
		self.sensors = {}
		self.basedevices = {}

		self.network = YamlProtocol.load(Share.networkinfo_path)["network"]
		self.iptable = {dev["name"] : dev["ip"] for dev in self.network}
		
		self.add_device("rpi", RPi("localhost", ip="localhost"))
		#self.draw_tree()
		#pprint({"assembly": self.tree}, indent=4)
		log.debug("Constructing scope assembly.")
	
	def __getattr__(self, device):
		if device in self.tree:
			return self.tree[device]
		else:
			raise TSDeviceNotRegistered(f"Device not found: {device}")

	def __getitem__(self, device):
		if device in self.tree:
			return self.tree[device]
		else:
			raise KeyError("device")

	def add_device(self, name, deviceobj, description=None):
		self.tree[name] = deviceobj
		self.descs[name] = description

		if description == None:
			self.descs[name] = "Mystery device does magical things!"


	def connect(self, devicename):
		if "." in devicename: ## To check if it is an ip address
			ip = devicename
		else:
			ip = self.network[devicename]["ip"]
		print(f"Attempting connections to device:: {devicename} at {ip}.")

		if self.network[devicename]["os"] == "micropython":
			self.tree[devicename] = MicropythonDevice(ip=ip)



	def device_type(self, device):
		"""
		Autoscans and appends the device type to its respectie list.
		Assumes that the devices have an attribute called "name" and the name is unique.
		"""
		devmap = {"actuator": abcs.Actuator, "sensor": abcs.Sensor, "basedevice": abcs.BaseDevice}
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


	def netscan(self):
		"""
		Ping each device on the network and set value in the network dict - reachable.
		Takes long and is a blocking function.
		"""

		def ping(ip_address):
			import subprocess

			# Run ping command and capture the output
			print("pinging -> ", ip_address, end=" : ")
			result = subprocess.run(['ping', '-c', '1', ip_address], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			    
			reachable = result.returncode == 0
			if not reachable: 
				print(f"The device at {ip_address} is [red]not reachable.[default]")
			else:
				print(f"The device at {ip_address} is [green]reachable.[default]")
			return reachable
			
			    
		for device in self.network:
			device["reachable"] = ping(device["ip"])
	
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

	def reconnections(self, device="cam", check_fn="is_open", reconnect_fn="reinit"):
		pass

