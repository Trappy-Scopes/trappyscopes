from pico_firmware.idioms.actionset import ActionSet
#from pico_firmware.bookeeping.checkpointer import Checkpointer


class MultiChController:

	def __init__(self, channels=[]):
		self.channels = ActionSet(channels)

	#@Checkpointer.write
	def setVs(self, *args):
		for i, ch in enumerate(self.channels):
			ch.setV(args[i])