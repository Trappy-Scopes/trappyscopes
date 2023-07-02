import sys
sys.path.append("../abcs/")
from abc import abstractmethod

from abcs.lights import Light
from abcs.lights.Light import interpolate



#  /$$$$$$$   /$$$$$$  /$$$$$$$         /$$$$$$   /$$$$$$  /$$      /$$ /$$      /$$  /$$$$$$  /$$   /$$
# | $$__  $$ /$$__  $$| $$__  $$       /$$__  $$ /$$__  $$| $$$    /$$$| $$$    /$$$ /$$__  $$| $$$ | $$
# | $$  \ $$| $$  \__/| $$  \ $$      | $$  \__/| $$  \ $$| $$$$  /$$$$| $$$$  /$$$$| $$  \ $$| $$$$| $$
# | $$$$$$$/| $$ /$$$$| $$$$$$$       | $$      | $$  | $$| $$ $$/$$ $$| $$ $$/$$ $$| $$  | $$| $$ $$ $$
# | $$__  $$| $$|_  $$| $$__  $$      | $$      | $$  | $$| $$  $$$| $$| $$  $$$| $$| $$  | $$| $$  $$$$
# | $$  \ $$| $$  \ $$| $$  \ $$      | $$    $$| $$  | $$| $$\  $ | $$| $$\  $ | $$| $$  | $$| $$\  $$$
# | $$  | $$|  $$$$$$/| $$$$$$$/      |  $$$$$$/|  $$$$$$/| $$ \/  | $$| $$ \/  | $$|  $$$$$$/| $$ \  $$
# |__/  |__/ \______/ |_______/        \______/  \______/ |__/     |__/|__/     |__/ \______/ |__/  \__/
#                                                                                                                                                                                                           
#                                                                                                       
#   /$$$$$$  /$$   /$$  /$$$$$$  /$$$$$$$  /$$$$$$$$       /$$       /$$$$$$$$ /$$$$$$$                 
#  /$$__  $$| $$$ | $$ /$$__  $$| $$__  $$| $$_____/      | $$      | $$_____/| $$__  $$                
# | $$  \ $$| $$$$| $$| $$  \ $$| $$  \ $$| $$            | $$      | $$      | $$  \ $$                
# | $$$$$$$$| $$ $$ $$| $$  | $$| $$  | $$| $$$$$         | $$      | $$$$$   | $$  | $$                
# | $$__  $$| $$  $$$$| $$  | $$| $$  | $$| $$__/         | $$      | $$__/   | $$  | $$                
# | $$  | $$| $$\  $$$| $$  | $$| $$  | $$| $$            | $$      | $$      | $$  | $$                
# | $$  | $$| $$ \  $$|  $$$$$$/| $$$$$$$/| $$$$$$$$      | $$$$$$$$| $$$$$$$$| $$$$$$$/                
# |__/  |__/|__/  \__/ \______/ |_______/ |________/      |________/|________/|_______/                 
                                                                                                      


class CcPwmRgbLed:
	"""
	Object used to control Multichannel Common Anode LED
	with Raspberry Pi Pico.
	"""
	
	# 1
	def __init__(self, rpin, gpin, bpin):

		self.channels = ['r', 'g', 'b']
		self.pin_map  = {'r': rpin, 'g': gpin, 'b': bpin}
		self.ch_map   = {'r': Pin(rpin), 'g': Pin(gpin), 'b': Pin(bpin)}
		self.dc_map   = {'r': 65535, 'g': 65535, 'b': 65535} # Duty Cycle
		self.freq     = int(30*1e5)
		self.normalise = False

		# CONSTANTS
		self.DUTYMAX = 0
		self.DUTYMIN = 2**16 - 1


		#self.rnorm = [1.0, 
		#			  3.0 - 1.8 + (3.2-3.0)/(2.0 -1.8),
		#			  3.0 - 1.8 + (3.2-3.0)/(2.0 -1.8)]


	#2
	def on(lux=0.0, channels=None):
	    """
	    Initializes the PWM object on the given channel.
	    and sets the frequency. Operation required after
	    blocking a channel.
	    """

	    if channels == None:
	    	channels = "rgb"

	    for ch in channels:
	    	if ch in self.channels:
	        	self.ch_map[ch] = \
	         	PWM(Pin(self.pin_map[ch], mode=Pin.OUT))
	        self.ch_map[channel].freq(self.freq)
	        self.set_ch(ch, lux=0.0)

	#3
	def off(channels=None):
		if channels == None:
	    	channels = "rgb"

	    for ch in channels:
	    	if ch in self.channels:
	    		self.set_ch(ch, lux=0.0)
	
	#4
	def block(self, channels=None):
		if channel == None:
			channels = "rgb"
		if channel in self.channels:
            if isinstance(ch_map[channel], PWM):
                self.ch_map[channel].deinit()
                print(isinstance(self.ch_map[channel], PWM))
            
            self.ch_map[channel] = Pin(self.pin_map[channel], mode=Pin.OUT)
            self.ch_map[channel].on()

	#5
	def set_ch(self, channel, lux=1.0):
		"""
		Maps Lux to the controlling parameter of the actual device.
		Control method: Negative PWM gating on 3.3V applied Voltage.
		"""
		def interpolate(in_val, in_min, in_max, out_min, out_max):
		    in_span = in_max - in_min
		    out_span = out_max - out_min
		    out_val = float(in_val - in_min) / float(in_span)
		    return out_min + (out_val * out_span)

		if channel in self.channels:
			dutycycle_u16 =  65535 - int(interpolate(lux, 0.0, 1.0, 0, 1, 65535))
			self.ch_map[channel].duty_u16(int(dutycycle_u16))


	#6
	def setV(self, channel, volt):
	    if channel in self.channels:
            dutycycle_u16 =  65535 - int(float(volt)/3.3*65535)
            self.ch_map[channel].duty_u16(int(dutycycle_u16))



	#7
	def setVs(self, rV, gV, bV):
		self.setV('r', rV)
		self.setV('g', gV)
		self.setV('b', bV)

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
	def sweep(self, period_s=1.0):
		pass
	
	#11
	@abstractmethod            
	def set_max(self, channel=None):
	    pass
	
	#12     
	@abstractmethod
	def red(lux=1.0):
	    self.set_ch('r', lux=lux)
	  
	#13  	
	@abstractmethod
	def green(lum=1.0):
	    self.set_ch('g', lux=lux)

	#14
	@abstractmethod
	def blue(lum=1.0):
	    self.set_ch('b', lux=lux)

	#15
	@abstractmethod
	def white(lux=1.0):
		# TODO: balance colors
		self.set_ch('r', lux=lux)
		self.set_ch('g', lux=lux)
		self.set_ch('b', lux=lux)

	#16
	@abstractmethod
	def mixer(self, color, lux=1.0)
		pass

	#17
	@abstractmethod
	def strobe():
		pass
	

