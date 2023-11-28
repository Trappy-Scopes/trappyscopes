

class DeviceTree:
	"""
	Its the collection of devices / independent peripherals with operational access.
	"""

	def __init__(self):
		self.tree = {}
		self.descs = {}


	def add_device(self, name, deviceobj, description=None):
		self.tree[name] = deviceobj
		self.descs[name] = description

		if description == None:
			self.descs[name] = "Mystery device does magical things!"

	

