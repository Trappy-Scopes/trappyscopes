import rpyc

from core.exceptions import TSDeviceNotRegistered

class Lab(object):
	"""
	Collection of devices and assemblies that represents the whole lab.
	"""
	def __init__(self, arg):
		self.devices = {}

		self.conn = {}

	def open(self, device):
		pass

	def close(self, device):
		pass

	def start_process(self, device, commmand):
		"""
		Uses Rpyc server call.
		"""
		self.conn[device] = rpyc.classic.connect(device)    # use default TCP port (18812)
		proc = conn.modules.subprocess.Popen(commmand, stdout = -1, stderr = -1)
		stdout, stderr = proc.communicate()
		print(stdout.split())
		print(stderr.split())

		return stdout

	def __getattr__(self, device):
		if device in self.conn.devices:
			return self.conn[device]
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



