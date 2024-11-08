import socket

from yamlprotocol import YamlProtocol



class Network:

	def __init__(self):
		self.network = None
		net = YamlProtocol.load(Share.networkinfo_path)
		if net != None:
			self.network = net["network"]
			self.iptable = {dev["name"] : dev["ip"] for dev in self.network}

	def net_connect(self, devicename):
		"""
		Connect to a devicename over network
		"""
		if "." in devicename: ## To check if it is an ip address
			ip = devicename
		else:
			ip = self.network[devicename]["ip"]
		print(f"Attempting connections to device:: {devicename} at {ip}.")

		if self.network[devicename]["os"] == "micropython":
			self.tree[devicename] = MicropythonDevice(ip=ip)

	def internet_connected():

		try:
			# Attempt to resolve Google's DNS server
			socket.create_connection(("8.8.8.8", 53), timeout=3)
			return True
		except OSError:
			return False