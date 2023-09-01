import platform
from logging import log

from utilities import pyboard

class RPiPicoDevice:

	def Select(mode, *args, **kwargs):
		if mode == "null":
			return NullRPiPicoDevice(*args, **kwargs)
		else:
			return RPiPicoDevice(*args, **kwargs)

	def all_ports():
		print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		for port in all_ports:
			print(port)
		print("-"*10)

	def potential_ports(): #TODO
		print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		potential_ports = [port for port in all_ports \
						   if port.__contains__("/dev/cu.") \
						   or port.__contains__("/dev/ttyACM")]

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


	def connect(self, port=None):
		# Try connection
		try:
			if self.port == None:
				if platform.system() == "Linux":
					print("Plateform is Linux.")
					port = '/dev/ttyACM'
				elif platform.system() == "Darwin":
					print("Plateform is Darwin (MacOS).")
					port = '/dev/cu.usbmodem10'
				else:
					print("Unsupported Plateform.")

				port_ = port + "0"

			print(f"Attempting connection to — {port_}")
			self.pico = pyboard.Pyboard(port_, 115200)
			self.port = port_
			self.connected = True
		except:
			for i in range(1, 6):
				port_ = port + str(i)
				print(port_)
				try:
					self.pico = pyboard.Pyboard(port_ + str(i), 115200)
					self.port = port_
				except:
					pass

		if self.connected:
			self.pico.enter_raw_repl()
			print(f"{self.name} -connected-to-> {self.port}")
		else:
			print("No Pico device found. Not connected.")


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
		pico filesystem.
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
		return None

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

