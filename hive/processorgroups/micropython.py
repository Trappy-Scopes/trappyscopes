import platform
import logging as log

from utilities.resolvetypes import resolve_type
from core.external import pyboard

from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup


class MicropythonDevice(AbstractProcessorGroup):

	def __init__(self, name=None, connect=True, port=None):
		super().__init__(name)
		self.connect_ = connect

		self.device = None
		
		self.port = None
		self.connected = False

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
	



class SerialMPDevice(MicropythonDevice):
	
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
		except:
			log.debug(f"Connection failed - {port}!")

	def disconnect(self):
		self.device.exit_raw_repl()

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
			if "Board in FS mode" in str(pport):
				log.debug(f"Trying out -> {pport.split(' ')[0]}")
				self.connect(port=pport.split(" ")[0])

			if self.connected:
				self.device.enter_raw_repl()
				log.debug(f"{self.name} -connection-on-> {self.port}")
				break
	
		if not self.connected:
			log.error("No SerialMP device found. Not connected.")
			SerialMPDevice.print_all_ports()
		else:
			return True



	# -------------  Serial Utilities -----------------------

	def __call__(self, command):
		log.debug(f"{self.name} << {command}")
		printed =  'print(' + str(command).replace('\'', '\"') + ')'
		ret = self.device.exec(printed)
		log.debug(f"{self.name} >> {ret.decode()}")
		return resolve_type(ret.decode().strip("\r\n"))

	def sync_files(self, local_folder, target_folder):
		try:
			# Traverse through local directory
			for root, dirs, files in os.walk(source):
				# Create equivalent folder structure on MicroPython device
				remote_root = os.path.join(target_folder, os.path.relpath(root, local_folder)).replace("\\", "/")
				pyboard.exec(f"import os; os.makedirs('{remote_root}', exist_ok=True)")
				
				# Send each file in the directory
				for file_name in files:
					local_path = os.path.join(root, file_name)
					remote_path = f"{remote_root}/{file_name}"

					#send_file_to_micropython(pyboard, local_path, remote_path)
					with open(local_path, 'rb') as file:
						file_data = file.read()
						pyboard.fs_put(file_data, remote_path)
						print(f"Transferred file: {local_path} -> {remote_path}")
		
		finally:
			pass
		print(f"Sync completed: {local_folder} to {target_folder} on MicroPython device.")