#from device_state import device_perma_state
from rich import print
import yaml
import json
import logging as log

from sharing import Share
from yamlprotocol import YamlProtocol

#import abcs #Abstract Base Classses

import threading
import rpyc

class TSDeviceNotRegistered(Exception):
	pass

#class MyService(rpyc.Service):
	

class RPYCServer:
	def __start_server__(self):
		from rpyc.utils.server import ThreadedServer
		#self.server = ThreadedServer(ScopeAssembly, port=18812, protocol_config={"allow_public_attrs": True})
		from rpyc.cli.rpyc_classic import ClassicServer
		self.server = ClassicServer.run()
		#self.server.start()

	def start_rpyc_server(self):
		server_thread = threading.Thread(target=self.__start_server__)
		server_thread.daemon = True  # Daemonize thread
		server_thread.start()

class ScopeAssembly():
	current = None
	"""
	Its the collection of devices or
	independent peripherals with operational access.

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

	def on_connect(self, conn):
		print("Client connected")

	def on_disconnect(self, conn):
		print("Client disconnected")

	def exposed_echo(self, text):
		print(text)
		return text

	def __init__(self):
		self.tree = {}
		self.descs = {}
		self.actuators = {}
		self.sensors = {}
		self.basedevices = {}

		self.network = None
		net = YamlProtocol.load(Share.networkinfo_path)
		if net != None:
			self.network = net["network"]
			self.iptable = {dev["name"] : dev["ip"] for dev in self.network}
		
		#self.add_device("rpi", RPi("localhost", ip="localhost"))
		#self.draw_tree()
		#pprint({"assembly": self.tree}, indent=4)


		self.exec = exec



		log.debug("Constructing scope assembly.")
		ScopeAssembly.current = self

	## transfered
	def __getattr__(self, device):
		if device in self.tree:
			return self.tree[device]
		else:
			raise TSDeviceNotRegistered(f"Device not found: {device}")
	# 		raise Exception("what device")

	# transfered
	def __getitem__(self, device):
		if device in self.tree:
			return self.tree[device]
		else:
			raise KeyError(device)

	# transfered
	def __contains__(self, device):
		return device in self.tree
		

	# Ok -> transfered
	def add_device(self, name, deviceobj, description=None):
		#type_ = self.device_type(deviceobj)
		
		self.tree[name] = deviceobj
		#self.descs[name] = type_

		#if type_ == None:
		#	self.descs[name] = "Mystery device does magical things!"
		#log.info(f"Added device to devicetree: {name} : {self.descs[name]}")

	# Check
	def add_mp_device(self, name, device):
		if device.is_connected():
			scope.add_device("name", device, description="Micropython device on serial connection.")
			scope.add_device(f"{name}prox", device.emit_proxy(""), description= "Proxy for micropython device on derial connection.") 
			
			try:
				all_pico_devs = device.exec_cleanup("print(Handshake.obj_list(globals_=globals()))")
				for d in all_pico_devs:
					proxdevice = device.emit_proxy(d)
					scope.add_device(d, proxdevice)
			except:
				log.error(f"{device}: handshake failed!")


	# NOK -> transfered
	def net_connect(self, devicename):
		"""
		Connect to a devicename over network
		"""
		if "." in devicename: ## To check if it is an ip address
			ip = devicename
		else:
			ip = self.network[devicename]["ip"]
		print(f"Attempting connections to device:: {devicename} at {ip}.")

		if self.network[devicename]["os"] == "micropython":
			self.tree[devicename] = MicropythonDevice(ip=ip)


	# Check --> transfered
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


	# Ok
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
	

	# Ok -> transfered
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

	# Check
	def mount_all_mp_devices(self):
		"""
		This method mounts all available micropython serial ports to
		the device tree.
		"""
		from hive.micropythondevice import SerialMPDevice
		all_ports = SerialMPDevice.potential_ports()
		for port in all_ports:
			device = SerialMPDevice(connect=True, port=port)
			if device.is_connected():
				name = device.name
				if name == None:
					name = port
				self.add_mp_device(name, device)


	def changestatus(s1, s2):
		def decorator(func):
			def wrapper(*args, **kwargs):
				if ScopeAssembly.current.__contains__("beacon"):
					ScopeAssembly.current.beacon.devicestatus(s1)
				
				ret = func(*args, **kwargs)
				
				if ScopeAssembly.current.__contains__("beacon"):
					ScopeAssembly.current.beacon.devicestatus(s2)
				return ret
			return wrapper
		return decorator

	def reconnections(self, device="cam", check_fn="is_open", reconnect_fn="reinit"):
		pass


class Exchange:

	def __init__(self, devices):
		pass



