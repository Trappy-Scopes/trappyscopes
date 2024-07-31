import sounddevice as sd
import numpy as np
from time import sleep

class Alarm:

	def __init__(self):
		pass

	def beep(self, n):
		"""
		Number of beeps.
		"""
		for i in range(n):
			self.__sine__(600, 1)


	def __sine__(self, freq, duration, sample_rate=22050):
		t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
		x = 0.5 * np.sin(2 * np.pi * freq * t)
		sd.play(x, sample_rate)
		sleep(1)