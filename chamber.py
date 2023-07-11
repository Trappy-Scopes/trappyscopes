

class Chamber:
	"""
	Describes utility functions for detecting and measuring chambers.
	"""

	def detect_ring(frames, magnification=1, resolution=[1920, 1080]):
		"""
		Do a ring detection.
		"""
		pass

	def multiplex(frames, magnification=1, resolution=[1920, 1080], hint_n=None):
		"""
		In the presence of multiple chambers `n` in the fov, 
		this function splits the frames into `n` segments.
		"""

	def __init__(self, diameter=None, type_=None, frames=None, **kwargs):

		self.type = type_
		self.diameter = diameter
		if diameter == None:
			if not frames == None:
				rings = *Chamber.detect_ring(frames, **kwargs)
				self.diameter = min([ring.diameter for ring in rings])

	def region_detection(self):
		"""
		Does a region analysis and returns a region-props object.
		"""
		pass