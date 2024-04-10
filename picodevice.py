import platform
from logging import log
from pprint import pprint
from utilities import pyboard


"""
TODO: 

+ Connectin protocol
+ Auto Connect Framework, Auto detect framework
+ Webrepl, Handshake
"""
class PicoProxyObject:

	def __init__(self, pico):
		self.obj = object_
		self.pico = pico
		self.unsafe = True

	def __getattr__(self, fn, *args, **kwargs):
		if self.unsafe:
			execstr = self.__exec_str__(fn, args, kwargs)
			print(execstr)
			return self.pico(execstr)
		else:

			if fn in dir(self.obj):
				return self.pico(self.__exec_str__(fn, args, kwargs))
				
			else:
				# Handle other attributes or raise an AttributeError
				raise AttributeError(f"'{type(self.obj).__name__}' object has no attribute '{fn}'")

	def __exec_str__(fn, *args, **kwargs):
		args_str = str(list(args)).strip('[').strip(']')
		optional_comma = ', '*(len(args)!=0 and len(kwargs) != 0)
		kwargs_str = ""
		for i, key in enumerate(kwargs):
			if isinstance(kwargs[key], str):
				obj = f"'{str(kwargs[key])}'"
			else:
				obj = str(kwargs[key])
			kwargs_str += (str(key) + "=" + obj)
			if i != len(kwargs)-1:
				kwargs_str += ", "
		
		return f"{fn}({args_str}{optional_comma}{kwargs_str})"

	def __repr__(self):
		return f"< PicoProxyObject on {self.pico} >"


class RPiPicoDevice:

	def Emit(object_, pico):
		return PicoProxyObject(object_, pico)

	def Select(mode, *args, **kwargs):
		"""
		Object selector factory function
		"""
		if mode == "null":
			return NullRPiPicoDevice(*args, **kwargs)
		else:
			return RPiPicoDevice(*args, **kwargs)

	def all_ports():
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		return [str(port) for port in all_ports]

	def print_all_ports():
		print("All availbale ports:")
		all_ports = RPiPicoDevice.all_ports()
		for port in all_ports:
			print(port)
		print("-"*10)

	def potential_ports(): #TODO
		#print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		all_ports = [str(port) for port in all_ports]
		potential_ports = [port for port in all_ports \
						   if str(port).__contains__("/dev/cu.") \
						   or str(port).__contains__("/dev/ttyACM")]
		return(potential_ports)

	# -- Object defination
	def __init__(self, port=None, name="pico", verbose=True, connect=True):
		#TODO: Add Eception

		self.connected = False
		
		self.name = name
		self.port = port
		self.print_ = lambda string: print(string) if verbose else None
		self.pico = None   # Actual device interface
		self.fs = {}       # A symbolic representation of the Filesystem on the device. 

		if connect:
			self.connect()

	def __del__(self):
		self.pico.exit_raw_repl()

	def disconnect(self):
		self.pico.exit_raw_repl()


	def connect(self, port):
		try:
			port = port.strip()
			print(f"Attempting connection to — {port}")
			self.pico = pyboard.Pyboard(port, 115200)
			self.port = port
			self.connected = True
			print(f"Connected to port: {self.port}")
		except:
			print("Connection failed!")
			pass

	def auto_connect(self, port=None):
		"""
		Function tries and connects to the first valid RPiPico Device
		connected to the 
		"""

		if self.port == None:
			if platform.system() == "Linux":
				#print("Plateform is Linux.")
				port = '/dev/ttyACM'
			elif platform.system() == "Darwin":
				#print("Plateform is Darwin (MacOS).")
				port = '/dev/cu.usbmodem10'
			else:
				print("Unsupported Plateform.")
				return
		
		# Try Sequential connections
		#for i in range(0, 6):
		#	try:	
		#			port_ = port + str(i)
		#			print(port_)
		#			self.__connect__(port_)
		#			if self.connected:
		#				break
		#	except:
		#		pass

		
		# Selective Port Connections based on System Scan
		for pport in RPiPicoDevice.potential_ports():
			if "Board in FS mode" in pport:
				print(pport.split(" ")[0])
				self.connect(port=pport.split(" ")[0])

			if self.connected:
				self.pico.enter_raw_repl()
				print(f"{self.name} -connected-to-> {self.port}")
				break
		
		if not self.connected:
			print("No Pico device found. Not connected.")
			RPiPicoDevice.all_ports()

	def emit_device(self, object_):
		"""
		A dynamic class is created inside the object.
		"""
		class PicoProxyObject:

			def __init__(self, pico):
				self.obj = object_
				self.pico = pico
				self.unsafe = True

			def __getattr__(self, fn, *args, **kwargs):
				if self.unsafe:
					return self.pico(self.__exec_str__(fn, args, kwargs))
				else:

					if fn in dir(self.obj):
						return self.pico(self.__exec_str__(fn, args, kwargs))
						
					else:
						# Handle other attributes or raise an AttributeError
						raise AttributeError(f"'{type(self.obj).__name__}' object has no attribute '{fn}'")

			def __exec_str__(fn, *args, **kwargs):
				args_str = str(list(args)).strip('[').strip(']')
				optional_comma = ', '*(len(args)!=0 and len(kwargs) != 0)
				kwargs_str = ""
				for i, key in enumerate(kwargs):
					if isinstance(kwargs[key], str):
						obj = f"'{str(kwargs[key])}'"
					else:
						obj = str(kwargs[key])
					kwargs_str += (str(key) + "=" + obj)
					if i != len(kwargs)-1:
						kwargs_str += ", "
				
				return f"{fn}({args_str}{optional_comma}{kwargs_str})"

			def __repr__(self):
				return f"< PicoProxyObject on {self.pico} >"

		### Emit device
		return PicoProxyObject(object_)




	def __call__(self, command):
		self.print_(f"{self.name}! do >> {command}")
		ret = self.pico.exec(command)
		self.print_(f"{self.name} said >> {ret.decode()}")
		return ret.decode()

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.__call__('exec(open("main.py").read())')

	def scan_root(self):
		"""
		Scan the filesystem on the pico device
		"""
		self.fs = {key:None for key in self.pico.fs_listdir(".")}
		return self.fs
	
	
	def sync_files(self, files, root=False):
		"""
		
		root [optional] : Syncs the file in the root location of the 
		pico filesystem, without creating a folder.
		"""
		
		files_ = list(deepcopy(files))
		if os.path.isdir(files):
			files = [os.path.abspath(file) for file in os.listdir(files)]
			if root:
				folder = "."
			else:
				folder = os.path.basename(os.path.dirname(files))
		elif os.path.isfile(files):
			files = list(files)
			folder = "."
			

		log.info(f"Syncing files: {files} to {folder} on pico device.")
		

		# Check if the current foldername is in the root
		self.scan_root()
		# If it doesn't exist, create it
		if folder in self.fs.keys() and folder != ".":
			self.pico.fs_mkdir(folder)
			log.info(f"Cretaed folder on pico filesystem: {folder}")


		# Then do a for loop of file-syncs
		for i, file in enumerate(files):
			self.pico.fs_cp(file, os.path.join(folder, \
								  os.path.basename(files_[i])))
			log.info(f"Wrote file to pico fs: {file}")



class NullRPiPicoDevice(RPiPicoDevice):

	def __init__(self, port=None, name="pico", verbose=True, connect=True):
		
		self.connected = True # Always
		self.name = name
		self.port = port 
		self.print_ = lambda string: print(string) if verbose else None

		if connect:
			self.connect()

	def __del__(self):
		return

	def disconnect(self):
		self.print_("disconnect: Null connection closed for NullRPiPicoDevice.")



	def connect(self, port=None):
		# Try connection
		self.print_("connect: Null connection established for NullRPiPicoDevice.")


	def __call__(self, command):
		self.print_(f"{command}: All calls are ignored by the NullRPiPicoDevice device.")
		return ""

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.print_("exec_main: All calls are ignored by the NullRPiPicoDevice device.")
		return None

	def scan_root(self):
		self.print_("scan_root: All calls are ignored by the NullRPiPicoDevice device.")
		return None

	def sync_files(self, files, root=False):
		self.print_("sync_files: All calls are ignored by the NullRPiPicoDevice device.")
		return None

	def auto_connect(self, port=None):
		self.print_("auto_connect: All calls are ignored by the NullRPiPicoDevice device.")
		return None


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


if __name__ == "__main__":
	input_ = input("Will test filesync on pico: type yes to continue")
	if input_ == "yes":
		pico = RPiPicoDevice(connect=False)
		pico.auto_connect()
		pico.exec_main()
		pico.pico.enter_raw_repl()
		#pico.pico.follow(10)
		#pico.pico.exec("do()")
		#pico.pico.follow(10)
		#print(dir(pico.pico.serial))
		#from time import sleep
		#while True:
		#	print(".")
		#	r = pico.pico.serial.readline().decode('utf-8').strip()
		#	print(r)
		#	sleep(0.5)
		
		#pico.pico.follow()
