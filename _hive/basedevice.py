from abc import abstractmethod
import logging as log

from dataclasses import dataclass


@dataclass
class BaseDevice:

	def __init__(self):
		"""
		A device is generically defined by identifiers and actions.
		"""
		name: str
		desc: str
		actions: dict




class DeviceTree(BaseDevice):
	"""
	Is a tree of devices that has atleast one processor group.
	It may contain another DeviceTree object.
	
	Contains the following Resource managers:

	1. PyVISA resource manager
	2. RPI GPIO (make into a seperate library).

	"""
	
	def __init__():
		self.pyvisa_rm = pyvisa.ResourceManager()


class BaseDevice:
	"""
	A BaseDevice is a group of processors that are controlled by the same operating
	system or firmware.
		|- LinuxDevice       : RPi 4B -> 4 processors
		|- MicropythonDevice : RPi pico -> 2 processors + 8 PIO cores

	Abstract base class for interfacing with any generic device.
	Specialisations planned: MicropythonDevice and LinuxDevice.

	All devices are capable of emitting Proxy objects, which can reconstruct python 
	object call semantics.
	"""

	class Proxy:
		def __init__(self, object_, device):
			self.obj = object_
			self.device = device

			log.debug(f"Created BaseDevice.Proxy: {self.obj}")

		def __getattr__(self, fn, *args, **kwargs):
			if fn != "print":
				return BaseDevice.Proxy(f"{self.obj}{'.'*bool(self.obj)}{fn}", self.device)
			else:
				def __print_implementer__(*args, **kwargs): ## maybe return a recursive
					return self.device(f"print{self.__getattr__(*args,  **kwargs)}")
				return __print_implementer__

		def __call__(self, *args, **kwargs):
			return self.device(self.__exec_str__("", *args, **kwargs))
			
		def __exec_str__(self, fn, *args, **kwargs):
			args_str = ""
			kwargs_str = ""

			if len(args) != 0:
				args_str = str(list(args)).strip('[').strip(']')
			optional_comma = ', '*(len(args)!=0 and len(kwargs) != 0)
			if len(kwargs) != 0:
				for i, key in enumerate(kwargs):
					if isinstance(kwargs[key], str):
						obj = f"'{str(kwargs[key])}'"
					else:
						obj = str(kwargs[key])
					kwargs_str += (str(key) + "=" + obj)
					if i != len(kwargs)-1:
						kwargs_str += ", "

			construction = f"{self.obj}{fn}({args_str}{optional_comma}{kwargs_str})"
			log.debug(f"Construction: {construction}")
			return construction

		def __repr__(self):
			return f"< {self.device} :: BaseDevice.Proxy on {self.device} >"


	@abstractmethod
	def __init__(self, name):
		self.name = name
		self.compute_processors = 0
		self.processor_map = {}


	@abstractmethod
	def emit_proxy(self, object_):
		pass

	@abstractmethod
	def connect(self, port):
		pass

	@abstractmethod
	def disconnect(self):
		pass

	@abstractmethod
	def auto_connect(self, port=None):
		pass

	@abstractmethod
	def exec(self, command):
		pass

	@abstractmethod
	def exec_main(self):
		pass

	@abstractmethod
	def dir_scan(self, root="."):
		pass
