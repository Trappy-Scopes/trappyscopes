from pssh.clients import ParallelSSHClient, SSHClient

from pssh.utils import enable_host_logger
enable_host_logger()

"""
SSH based multi-login systems. Almost obselete.
"""

class Device:

	def __init__(self, addr, password):
		self.addr = addr
		self.password = password

	def parse_roll(keyroll):
		roll = set()
		for device in keyroll:
			roll.append(Device(device["addr"], device["password"]))
		return roll




class SSHLayer(SSHClient):

	def __init__(self, device):
		self.device = device
		super().__init__(device.addr, device.password)

	def open():
		pass

	def close():
		pass

	def __exit__(self):
		self.close()

"""
Idiom:

user --creates--> MicroscopeHive --creates--> SSHHive + NullMicroscopeObjects
"""


class SSHHive:
	pass

class MicroscopeHive(ParallelSSHClient):
	"""
	A collection of ssh clients.
	"""
	def __init__(self):
		self.group = OrderedDict()

	def rollcall(self, keyroll):
		for device in keyroll:
			self.add(keyroll[device])

	def synchronise(self):
		# close the group
		self.close_group()

		# open whole group
		super().__init__(self.group)


	def add(self, device):
		self.group[device["name"]] = \
			{
				"name"     : device["name"]
				"addr"     : device["addr"],
				"password" : device["password"],
				"device"   : SSHClient(device["addr"], device["password"])
			}


	def __call__(self, cmd):
		self.hive_exec(cmd)

	def hive_exec(self, cmd):
		for device in self.group:
			client = self.group[device]["device"]
			client.run_command(cmd)
			client.join(consume_output=True)


	def __get_item__(self, device_name):
		return self.group[device_name]["device"]



	def close_group(self):
		for device in self.group:
			self.group[device].close()

	def __exit__(self):
		self.close_group()

