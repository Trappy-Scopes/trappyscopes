from abc import abstractmethod
import logging as log

from dataclasses import dataclass


class BaseDevice(): #ProcessorGroup
	"""
	A BaseDevice is a virtual device that can emit other proxy objects.
	A BaseDevice is also group of processors that are controlled by the
	same operating system or firmware.
		|- LinuxDevice       : e.g. RPi 4B -> 4 processors.
		|- MicropythonDevice : e.g. RPi pico -> 2 processors + 8 PIO cores.

	Abstract base class for interfacing with any generic device. All devices are capable of emitting Proxy objects, which can reconstruct python 
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

	def __init__(self, processors=1):
		"""
		A device is generically defined by identifiers and actions.
		"""
		self.name = ""
		self.desc =  ""
		self.actions = {} ## What is this really?

		self.compute_processors = processors
		self.processor_map = {}

	def __getattr__(self, key):
		return self.emit_proxy(key)

	def emit_proxy(self, object_):
		BaseDevice.Proxy(object_, self)

	@abstractmethod
	def connect(self, port):
		pass

	@abstractmethod
	def disconnect(self):
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
