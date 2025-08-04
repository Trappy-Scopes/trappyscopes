import platform
import logging as log
import os

from utilities.resolvetypes import resolve_type
from core.external import pyboard
from rich import print

from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup


class MicropythonDevice(AbstractProcessorGroup):

	def __init__(self, name=None, connect=True, port=None, exec_main=False, handshake=False):
		super().__init__(name)
		self.connect_ = connect

		self.device = None
		self.board_name = None
		self.port = None
		self.connected = False
		self.exec_main_ = exec_main
		self.handshake_ = True

	def __getstate__(self):
		return {}
	def __setstate__(self, state):
		pass

	def __del__(self):
		if self.device:
			self.device.exit_raw_repl()

	def __call__(self, command):
		raise Exception("Method not defined!")

	def exec_main(self):
		"""
		Execute main function on the Pico device.
		"""
		self.__call__('exec(open("main.py").read())')

	def scan_root(self):
		"""
		Scan the filesystem on the pico device
		"""
		fs = {key:None for key in self.device.fs_listdir(".")}
		return fs

	def exec_cleanup(self, command):
		result = self.__call__(command)
		return result
	
	def readline(self, timeout=15):
		output = self.device.read_until(1, b"\r\n", timeout=timeout)  # Read data with timeout
		if output:
			return output.decode('utf-8')


class SerialMPDevice(MicropythonDevice):
	exclusion_list = []
	def __init__(self, name=None, connect=True, port=None, exec_main=False, handshake=False, search_name=False):
		MicropythonDevice.__init__(self, name=name, connect=connect, port=port, exec_main=False, handshake=False,)

		self.search_name = search_name
		if self.connect_ == "autoconnect":
			self.auto_connect()

		if self.connected:
			if exec_main:
				self.exec_main()

			if handshake:
				self.handshake()
		else:
			log.error(f"SerialMPDevice construction failed: {name}")

	# ---------- Serial utilities ------------------
	def all_ports():
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		return [str(port) for port in all_ports]

	def print_all_ports():
		print("All availbale ports:")
		all_ports = SerialMPDevice.all_ports()
		for port in all_ports:
			print(port)
		print("-"*10)

	def potential_ports():
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		all_ports = [str(port) for port in all_ports]
		potential_ports = [port for port in all_ports \
						   if str(port).__contains__("/dev/cu.") \
						   or str(port).__contains__("/dev/ttyACM")]
		return(potential_ports)

	def mount_all():
		"""
		This method mounts all available micropython serial ports and return a list of
		them.
		"""
		all_ports = SerialMPDevice.potential_ports()
		mpdevices = []
		for port in all_ports:
			device = SerialMPDevice(connect=True, port=port)
			if device.is_connected():
				mpdevices.append(device)
		return mpdevices
	
	def connect(self, port):
		try:
			port = port.strip()
			log.debug(f"Attempting connection to — {port}")
			self.device = pyboard.Pyboard(port, 115200)
			self.port = port
			self.connected = True
			log.debug(f"Connected to port: {self.port}")
			self.device.enter_raw_repl()
			self.board_name = self.device.exec("import board")
			self.board_name = self.exec_cleanup("board.name")
			log.debug(f"Board name: {self.board_name}")
		except Exception as e:
			log.debug(f"Connection failed - {port}!")
			log.error(e)

	def disconnect(self):
		self.device.exit_raw_repl()
		self.device.close()
		if self.port in SerialMPDevice.exclusion_list:
			SerialMPDevice.exclusion_list.remove(self.port)

	def auto_connect(self, port=None):
		"""
		Function tries and connects to the first valid SerialMPDevice it finds.
		"""
		log.info("Attempting micropython autoconnect.")
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
		all_ports = list(SerialMPDevice.potential_ports())
		for pport in all_ports:
			port = pport.split(" ")[0]
			if "Board in FS mode" in str(pport) and port not in SerialMPDevice.exclusion_list:
				log.debug(f"Trying out -> {pport.split(' ')[0]}")
				self.connect(port=port)

			if self.connected:
				log.debug(f"{self.name} -connection-on-> {self.port}")
				
				self.device.enter_raw_repl()
				
				if self.search_name != False:
					if self.board_name != self.search_name:
						log.debug('Not the correct deice. Closing.')
						self.disconnect()
					else:
						log.debug("Correct decice found!")
						SerialMPDevice.exclusion_list.append(self.port)
						break
				else:
					break

				
		if not self.connected:
			log.error("No SerialMP device found. Not connected.")
			SerialMPDevice.print_all_ports()
		else:
			return True

	def handshake(self):
		from ..assembly import ScopeAssembly
		scope = ScopeAssembly.current
		try:
			all_pico_devs = self.exec_cleanup("Handshake.obj_list(globals_=globals())")
			for device in all_pico_devs:
				proxy_device = self.emit_proxy(device)
				scope.add_device(device, proxy_device, description="Micropython proxy peripheral.")
		except Exception as e:
			print(e)
			log.error(f"{self.name} handshake failed!")

	# -------------  Serial Utilities -----------------------

	def __call__(self, command):
		log.debug(f"{self.name} << {command}")
		printed =  'print(' + str(command).replace('\'', '\"') + ')'
		ret = self.device.exec(printed)
		log.debug(f"{self.name} >> {ret.decode()}")
		return resolve_type(ret.decode().strip("\r\nNone").strip("\r\n"))

	def sync_files(self, local_folder, target_folder):
		try:
			# Traverse through local directory
			for root, dirs, files in os.walk(local_folder):
				# Create equivalent folder structure on MicroPython device
				remote_root = os.path.join(target_folder, os.path.relpath(root, local_folder)).replace("\\", "/")
				remote_root = remote_root.replace("/.", "")
				#self.__call__(f"import os\ntry:\n\tos.mkdir('{remote_root}')\nexcept OSError:\n\tpass")
				
				# Send each file in the directory
				for file_name in files:
					local_path = os.path.join(root, file_name)
					remote_path = f"{remote_root}/{file_name}"

					#send_file_to_micropython(pyboard, local_path, remote_path)
					#with open(local_path, 'rb') as file:
					#file_data = file.read()
					self.device.fs_put(local_path, remote_path)
					print(f"Transferred file: {local_path} -> {remote_path}")
		
		except Exception as e:
			print("[red] Sync failed ----------> [default]")
			print(e)
		finally:
			pass
		print(f"Sync completed: {local_folder} to {target_folder} on MicroPython device.")
