import beepy as beep



class Alarm:

	def beep(n):
		"""
		Number of beeps.
		"""
		for i in range(n):
			beep.beep(4)