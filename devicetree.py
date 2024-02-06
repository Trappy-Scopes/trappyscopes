from device_state import device_perma_state


class RPi():
	"""
	Placeholder object for RPi 4B.
	"""
	def __repr__(self):
		return device_perma_state()

class DeviceTree:
	"""
	Its the collection of devices / independent peripherals with operational access.

	* cluster	
		|- trappy_scope
			|- rpi
				|- cam (camera)
			|- pico
				|- lit (lights)
				|- beacon
				|- sensors.tandh
				|- sensors.spectrometer
			|- remote-pico
				|- pump (peristatic pump)
			|- remote-pico
				|- alignment_device
			|- remote-pico
				|- cluster

	"""

	def __init__(self):
		self.tree = {"rpi": Rpi(), "pico": None}
		self.descs = {}


	def add_device(self, name, deviceobj, description=None):
		self.tree[name] = deviceobj
		self.descs[name] = description

		if description == None:
			self.descs[name] = "Mystery device does magical things!"

	

