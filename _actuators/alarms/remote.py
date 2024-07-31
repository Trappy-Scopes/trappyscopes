

class Alarm:
	"""
	The same structure is followed by Beacons and Buzzers.
	This class finds a remote buzzer/beacon and returns an object proxy.
	"""

	def __init__(self):
		
		self.proxy = None
		if "buzzer" ScopeAssembly.current:
			self.proxy =  ScopeAssembly.current.buzzer


	def on(self):
		"""
		Turn on the alarm indefinately.
		"""
		self.proxy.on()

	def off(self):
		"""
		Turn off the alarm.
		"""
		self.proxy.off()

	def blink(self):
		"""
		Blink/pulse the alarm indefinately.
		"""
		self.proxy.blink()

	def beep(self, n):
		"""
		Blink/pulse the alarm "n" times.
		"""
		self.proxy.beep(n)