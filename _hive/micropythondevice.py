from basedevice import BaseDevice

class MicropythonDevice(BaseDevice):
	"""

	Interface to communicate with micropython devices.
	|- BaseDevice	
	:	|- Micropython device
	:	:	|- NetworkMPDevice
	:	:	|- SerialMPDevice
	:	:	|- NullMPDevice
	:	*
	*
	"""

	def emit_proxy(self, object_):
		return BaseDevice.Proxy(object_, self.device)

	def __init__(self, name=None, connect=True, port=None):
		self.name = name
		self.connect_ = connect

		self.device = None
		self.port = None

		self.connected = False
		self.fs = {}

		self.verbose = True

	def print_(*args, **kwargs):
		if self.verbose:
			print(*args, **kwargs)

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.__call__('exec(open("main.py").read())')

	def scan_root(self):
		"""
		Scan the filesystem on the pico device
		"""
		self.fs = {key:None for key in self.device.fs_listdir(".")}
		return self.fs
	
	
	def sync_files(self, files, root=False):
		"""
		## Redo
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
			self.device.fs_mkdir(folder)
			log.info(f"Cretaed folder on pico filesystem: {folder}")


		# Then do a for loop of file-syncs
		for i, file in enumerate(files):
			self.devicce.fs_cp(file, os.path.join(folder, \
								  os.path.basename(files_[i])))
			log.info(f"Wrote file to pico fs: {file}")

class NetworkMPDevice(MicropythonDevice):
	
	def __init__(self, name=None, connect=True, port=None):

		super().__init__(name=name, connect=connect, port=port)

		if self.connect_:
			self.connect()

	def __del__(self):
		pass

	def connect(self, port):
		try:
			ws = websocket.WebSocketApp(ws_url)
			ws.run_forever()
			self.port = port
			self.device = ws
			self.connected = True
		except:
			log.error(f"Connection failed: {port}")
	def disconnect(self):
		pass
	def auto_connect(self, port=None):
		pass

	async def __call__(self, command):
		MicropythonDevice.print_(f"{self.name} << {command}")
		
		await self.device.send(command)
		ret = await self.device.recv()

		MicropythonDevice.print_(f"{self.name} >> {ret.decode()}")
		return resolve_type(ret.decode().strip("\r\n"))


class SerialMPDevice(MicropythonDevice):
	"""
	Specialised device communication protocol for hardwire serial connection
	using pySerial and pyboard library.
	"""
	
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

	def __init__(self, name=None, connect=True, port=None):
		
		super().__init__(name=name, connect=connect, port=port)

		if self.connect_:
			self.connect()

	def __del__(self):
		self.device.exit_raw_repl()

	def connect(self, port):
		try:
			port = port.strip()
			print(f"Attempting connection to — {port}")
			self.device = pyboard.Pyboard(port, 115200)
			self.port = port
			self.connected = True
			print(f"Connected to port: {self.port}")
		except:
			print(f"Connection failed - {port}!")

	def disconnect(self):
		self.device.exit_raw_repl()

	def auto_connect(self, port=None):
		"""
		Function tries and connects to the first valid SerialMPDevice it finds.
		"""

		if self.port == None:
			if platform.system() == "Linux":
				log.debug("Plateform is Linux.")
				port = '/dev/ttyACM'
			elif platform.system() == "Darwin":
				log.debug("Plateform is Darwin (MacOS).")
				port = '/dev/cu.usbmodem10'
			else:
				log.error("Unsupported plateform (os).")
				
		# Selective port connections based on system scan
		for pport in SerialMPDevice.potential_ports():
			if "Board in FS mode" in pport:
				print(f"Trying out -> {pport.split(' ')[0]}")
				self.connect(port=pport.split(" ")[0])

			if self.connected:
				self.device.enter_raw_repl()
				print(f"{self.name} -connection-on-> {self.port}")
			break
	
		if not self.connected:
			log.critical("No SerialMP device found. Not connected.")
			SerialMPDevice.all_ports()

	def __call__(self, command):
		MicropythonDevice.print_(f"{self.name} << {command}")
		ret = self.device.exec(command)
		MicropythonDevice.print_(f"{self.name} >> {ret.decode()}")
		return resolve_type(ret.decode().strip("\r\n"))


class NullDevice(MicropythonDevice):
	
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