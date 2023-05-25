from mcu_controls import MCUControls


class PWMLights:
	"""
	Invalid input values are ignored.
	"""

	def __init__(mcu_port, mid, pwm_res=16):
		self.mcu = mcu_port
		self.mid = mid
		self.pwm_res = pwm_res


	def test():
		"""
		Sets a test sequence for lighting.
		"""
		self.mcu.send(f"{self.mid}->lights-test")


	def on(lum=1.0):
		"""
		Switch on lights.
		"""
		if lum >= 0 and lum lum <= 1:
			self.mcu.send(f"{self.mid}->lights-on-{lux}")

	def off():
		self.mcu.send(f"{self.mid}->lights-off")


	def red(lum=1.0):
		if lum >= 0 and lum lum <= 1:
			self.mcu.send(f"{self.mid}->lights-red-{lux}")
	

	def green(lum=1.0):
		if lum >= 0 and lum lum <= 1:
			self.mcu.send(f"{self.mid}->lights-green-{lux}")


	def blue(lum=1.0):
		if lum >= 0 and lum lum <= 1:
			self.mcu.send(f"{self.mid}->lights-blue-{lux}")


	def white(lux=1.0):
		if lum >= 0 and lum lum <= 1:
			self.mcu.send(f"{self.mid}->lights-white-{lux}")

