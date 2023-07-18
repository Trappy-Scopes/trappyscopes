from abc import abstractmethod

class AbstractLaser:
	"""
	Interface for laser controller.
	"""
	@abstractmethod
	def __init__(self, interface=("spi", pins), gate_pin=None,
				 Ilimit_mA):
		pass

	@abstractmethod
	def set_max():
		pass

	@abstractmethod
	def set_min():
		pass

	@abstractmethod
	def pulse_ms(pulse_duration, lux=1.0):
		pass

	@abstractmethod
	def on(lux=1.0):
		pass

	@abstractmethod
	def off():
		pass

	@abstractmethod
	def feedback(fb_pin, sampling_factor=1):
		pass

	@abstractmethod
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



