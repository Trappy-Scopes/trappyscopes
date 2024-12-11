from abc import abstractmethod
import logging as log
class ProcessorGroup:

	def __init__(self, name):
		self.name = name
		self.config = {}

	@abstractmethod
	def exec(self, command):
		pass

	@abstractmethod
	def close(self):
		pass

	@abstractmethod
	def shell(self, command):
		pass

	@abstractmethod
	def __call__(self, command):
		pass

	def emit_proxy(self, object_, *args, **kwargs):
		return ProcessorGroup.Proxy(object_, self)

	def __getattr__(self, fn):
		return self.emit_proxy(fn)

	class Proxy:
		def __init__(self, object_, device):
			self.obj = object_
			self.device = device
			self.config = {}

			log.debug(f"Created ProcessorGroup.Proxy: {self.obj}")

		def close(self):
			log.debug(f"Closed proxy object: {self.obj}")

		def __getattr__(self, fn, *args, **kwargs):
			if fn != "print":
				return ProcessorGroup.Proxy(f"{self.obj}{'.'*bool(self.obj)}{fn}", self.device)
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
			return f"< {self.device} :: ProcessorGroup.Proxy on {self.device} >"

		def close(self):
			log.debug(f"Proxy device closed: {self}.")