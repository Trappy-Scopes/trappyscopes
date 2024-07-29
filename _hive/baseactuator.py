


class Actuator(BaseDevice):
	
	def __init__(self, obj):
		"""
		Credits: https://stackoverflow.com/a/1445289
		"""
		self.__class__ = type(obj.__class__.__name__,
								  (self.__class__, obj.__class__),
								  {})
		self.__dict__ = obj.__dict__
		

		# A sensor can be read
		self.read = None
		self.write = None