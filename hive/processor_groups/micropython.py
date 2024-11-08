

class MicropythonDevice:


	# Check
	def mount_all():
		"""
		This method mounts all available micropython serial ports to
		the device tree.
		"""
		from hive.micropythondevice import SerialMPDevice
		all_ports = SerialMPDevice.potential_ports()
		for port in all_ports:
			device = SerialMPDevice(connect=True, port=port)
			if device.is_connected():
				name = device.name
				if name == None:
					name = port
				self.add_mp_device(name, device)