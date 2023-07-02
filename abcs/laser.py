

class Laser:
	"""
	Interface for laser controller.
	"""

	def __init__(self, interface=("spi", pins), gate_pin=None,
				 Ilimit_mA):
		pass


	def set_max():
		pass

	def set_min():
		pass

	def pulse_ms(pulse_duration, lux=1.0):
		pass

	def on(lux=1.0):
		pass

	def off():
		pass

	def feedback(fb_pin, sampling_factor=1):
		pass

	def LaserSelect(controller, args, kwargs):

		laser = Laser(*args, **kwargs)
		controller = controller.strip()

		if controller.lower() == "thorlabs_mcb":
			laser = Laser(*args, **kwargs)
			# Modify parameters

		elif controller.lower() == "lt3092":
			  laser = Laser(*args, **kwargs)

		else:
			print("Laser::Contoller::Select: Unknown controller passed.")



