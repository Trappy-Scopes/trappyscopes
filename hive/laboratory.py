import rpyc
import logging as log

from core.exceptions import TSDeviceNotRegistered
from hive.processorgroups.abstractprocessorgroup import ProcessorGroup


from rich import print

class RemoteLink(ProcessorGroup):
	def __init__(self, device, mode="classic"):
		if mode == "classic":
			self.device =  rpyc.classic.connect(device)    # use default TCP port (18812)
	
	def __call__(self):
		self.device.root()

class Lab(object):
	"""
	Collection of devices and assemblies that represents the whole lab.
	"""

	def __init__(self):
		self.devices = {}

	def open(self, devices):
		for device in list(devices):
			try:
				device_name = device.replace(".local", "").strip()
				self.devices[device_name] = self.__connect__(device)
				log.info(f"Device connected: {device_name}!")
			except Exception as e:
				log.error(f"Device connection failed: {device_name}!")
				print("[red]", e)


	def close(self, devices, mode="classic"):
		for device_name, device in self.devices.items():
			log.info(f"Closed connection to: {device_name}")
			device.close()


	def start_process(self, device, commmand):
		"""
		Uses Rpyc server call.
		"""
		self.conn[device] = self.__connect__()
		
		#proc = conn.modules.subprocess.Popen(commmand, stdout = -1, stderr = -1)
		#stdout, stderr = proc.communicate()
		#print(stdout.split())
		#print(stderr.split())

		return stdout

	def __connect__(self, device, mode="classic"):
		if mode == "classic":
			self.device =  rpyc.classic.connect(device)    # use default TCP port (18812)

	def __getitem__(self, device):
		if device in self.devices:
			return self.devices[device]
		else:
			raise TSDeviceNotRegistered(f"Device not found: {device}")




		
if __name__ == "__main__":
	
	## Create lab
	lab = Lab()

	## See what's up and connect. 
	lab.start_process("m1", "ls")
	lab.start_process("m2", "ls")
	lab.start_process("m3", "ls")
	lab.start_process("m4", "ls")

	## Send hellos
	lab.m1.print("Hello for the mainframe.")
	lab.m2.print("Hello for the mainframe.")
	lab.m3.print("Hello for the mainframe.")
	lab.m4.print("Hello for the mainframe.")

	## Take a picture.
	lab.m1.create_exp("test")
	lab.m1.scope.lit.setVs(2,2,2)
	lab.m1.cam.capture("img", "remote_capture.png")



