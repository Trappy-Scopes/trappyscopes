from lights.abcs.lights import Light as abstractLight
from picodevice import RPiPicoDevice


class PicoLight(abstractLight):
	"""
	Specific implementation of RPiPico device and abcs.lights
	to control lights on RPi Pico Microcontroller.
	"""
	
	#1
	def __init__(self, RPiPicoDevice, obj_name):
		self.name = obj_name
		self.pico = picodevice

	#2
	def on(self, lux=1.0, channel=None):
		return self.pico(f"{self.name}.on(lum={lux}, channel={channel})")

	#3
	def off(self, channel=None):
		return self.pico(f"{self.name}.off(lum=lux, channel={channel})")

	#4
	def block(self, channels=None):
		return self.pico(f"{self.name}.block(channel={channel})")

	#5
	def setch(self, channel, lux=1.0):
		return self.pico(f"{self.name}.setch(channel={channel}, lux={lux})")

	#6
	def setV(self, channel, volt):
		return self.pico(f"{self.name}.setV({channel}, {volt})")


	#7
	def setVs(self, rV, gV, bV):
		return self.pico(f"{self.name}.setVs({rV}, {gV}, {bV})")

	#8
	def setIs(self, rI_mA, gI_mA, bI_mA):
		return self.pico(f"{self.name}.setIs({rI_mA}, {gI_mA}, {bI_mA})")

	#9
	def setI(self, channel, current_mA):
		return self.pico(f"{self.name}.setI({channel}, {current_mA})")

	#10
	def rgb_sweep(self, period_s=1.0):
		return self.pico(f"{self.name}.rgb_sweep(period_s={period_s})")

	
	#11            
	def set_max(self, channel=None):
		return self.pico(f"{self.name}.set_max(channel={channel})")
	
	
	#12     
	def red(lux=1.0):
		return self.pico(f"{self.name}.red(lux={lux})")
	  
	#13  	
	def green(lux=1.0):
		return self.pico(f"{self.name}.green(lux={lux})")

	#14
	def blue(lux=1.0):
		return self.pico(f"{self.name}.blue(lux={lux})")

	#15
	def white(lux=1.0):
		return self.pico(f"{self.name}.white(lux={lux})")

	#16
	def mixer(self, color, lux=1.0):
		"""
		Implements secondary colors.
		"""
		return self.pico(f"{self.name}.mixer(color, lux={lux})")

	#17
	def strobe(self, timer=None):
		"""
		Is a non-blocking call if a timer object is passed.
		"""
		return self.pico(f"{self.name}.strobe(timer={timer})")

	# 18
	def state(self):
		return self.pico(f"{self.name}.state()")

	# 19
	def __repr__(self):
		return self.pico(f"{self.name}")

	
	

