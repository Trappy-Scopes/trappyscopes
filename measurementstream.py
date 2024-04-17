from measurement import Measurement


class MeasureStream:
	"""
	Returns time adjusted copies of a measurement.
	"""
	def __init__(self, measurement):
		self.measure = measurement
		self.results = []
	
	def measure(self, **kwargs):
		newm = deepcopy(self.measure)
		newm.advance()

		## Overload specific fields
		for key, value in kwargs:
			newm[key] = value

		self.results.append(newm)
		return newm

	#def __copy__():
	#	pass

	#def __deepcopy__():
	#	pass