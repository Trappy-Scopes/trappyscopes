from abc import abstractmethod

class Light:
	"""
	Object used to control the LED panel for lighting.
	"""
	
	#1
	@abstractmethod
	def __init__(self, pins, norm=False):
		pass

	#2
	@abstractmethod
	def on(lum=1.0, channel=None):
		pass

	#3
	@abstractmethod
	def off(channel=None):
		pass

	#4
	@abstractmethod
	def block(self, channels=None):
		pass

	#5
	@abstractmethod
	def setch(self, channel, lux=1.0):
		pass

	#6
	@abstractmethod
	def setV(self, channel, volt):
	    pass

	#7
	@abstractmethod
	def setVs(self, rV, gV, bV):
		pass

	#8
	@abstractmethod
	def setIs(self, rI_mA, gI_mA, bI_mA):
		pass

	#9
	@abstractmethod
	def setI(self, channel, current_mA):
		pass

	#10
	@abstractmethod
	def rgb_sweep(self, period_s=1.0):
		pass
	
	#11
	@abstractmethod            
	def set_max(self, channel=None):
	    pass
	
	#12     
	@abstractmethod
	def red(lum=1.0):
	    pass
	  
	#13  	
	@abstractmethod
	def green(lum=1.0):
	    pass

	#14
	@abstractmethod
	def blue(lum=1.0):
	    pass

	#15
	@abstractmethod
	def white(lux=1.0):
		pass

	#16
	@abstractmethod
	def mixer(self, color, lux=1.0):
		"""
		Implements secondary colors.
		"""
		pass

	#17
	@abstractmethod
	def strobe(self, timer=None):
		"""
		Is a non-blocking call if a timer object is passed.
		"""
		pass

	# 18
	@abstractmethod
	def state(self):
		pass

	@abstractmethod
	def __repr__(self):
		pass


	def interpolate(in_val, in_min, in_max, out_min, out_max):
	    in_span = in_max - in_min
	    out_span = out_max - out_min
	    out_val = float(in_val - in_min) / float(in_span)
	    return out_min + (out_val * out_span)

	
	

