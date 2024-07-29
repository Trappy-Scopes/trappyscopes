

# API v1.0

class Machine:

	def __init__(self, name):

		self.name = name
		self.processors = []
		self.actuators = []
		self.detectors = []

		self.tree = {}
		self.network = None

		## Rewired configuration of the current machine
		self.abstracts= {}
