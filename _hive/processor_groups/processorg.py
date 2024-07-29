

class ProcessorGroup(BaseDevice):

	def __init__(self, name, size=4):

		super().__init__(name)
		
		self.size = size
		self.group = {}

		self.control = {}