class FluidicsDevice:
	"""
	Describes utility functions for detecting and measuring chambers.
	"""

	current = []

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

	def __init__(self, name, dia_mm=None, frames=None, **kwargs):

		self.name = name
		self.dia_mm = dia_mm
		#if diameter == None:
		#if not frames == None:
		#	rings = Chamber.detect_ring(frames, **kwargs)
		#	self.diameter = min([ring.diameter for ring in rings])
		FluidicsDevice.current = self

	def __getstate__(self):
		return {"name": self.name, "type": "fluidicsdevice", "dia_mm": self.dia_mm}

	def region_detection(self):
		"""
		Does a region analysis and returns a region-props object.
		"""
		pass

	def scan_particles(self):
		"""
		Detects particles (cells) in a given region. 
		"""
		pass


	def detect_motion(self):
		"""
		Does low-processing motion detection on the feed.
		"""
		pass