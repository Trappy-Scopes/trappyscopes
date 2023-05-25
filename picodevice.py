from utilities import pyboard


class RPiPicoDevice:

	def all_ports():
		print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		for port in all_ports:
			print(port)
		print("-"*10)

	def potential_port(): #TODO
		print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		potential_ports = [port for port in all_ports \
						   if port.__contains__("/dev/cu.") \
						   or port.__contains__("/dev/ttyACM")]

	# -- Object defination
	def __init__(self, port='/dev/ttyACM0', name="pico", verbose=True):
		self.pico = pyboard.Pyboard(port, 115200)
		self.pico.enter_raw_repl()

		self.port = port
		self.name = name
		self.print_ = lambda string: print(string) if verbose else None

	def __del__(self):
		self.pico.exit_raw_repl()


	def __call__(self, command)
		self.print_(f"{self.name}! do >> {command}")
		ret = self.pico.exec(command)
		self.print_(f"{self.name} said >> {ret.decode()}")
		return ret.decode()

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.__call__('exec(open("main.py").read())')

return
class PicoProxyDevice:
	"""
	A proxy device that acts as a virtual device on 
	top of an `RPiPicoDevice` object.
	"""

	def __init__(self, picodevice, object, name=None):
		self.pico = picodevice
		self.name = name

		# Revolve around the object class and emit methods
		# Problem: ImportErrors - solution - Abstract classes


		def expand_args(*args, **kwargs):
			expanded = ""
			for arg in args:
				expanded += f" {arg},"
			if len(kwargs) == 0:
				expanded.rstrip(",")
			for karg in kwargs:
				expanded += f" {karg}={kwargs[karg]},"
			expanded = expanded[:-1]
			return expanded

		methods = [fn for fn in dir(object) \
		           if not fn.startswith("__") and fn.endswith("__") ]
		for method in methods:
			
			fn = lambda *args, **kwargs: \
						self.__call__(f"{method}({expand_args(args, kwargs)})") 
			
			
			bound_fn = types.MethodType(fn, PicoProxyDevice)
			setattr(self, colors[i], deepcopy(cdl.lambda_list[i]))



	def __call__(self, command):
		"""
		Execute command on the pico device
		"""

		if self.name == None or command.startswith(f"{self.name}."):
			self.picodevice(command)
		else:
			self.picodevice(f"{self.name}.{command}")

