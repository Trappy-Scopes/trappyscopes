from time

from _hive.physical import PhysicalObject
from _core.sharing.vault import Vault
from _hive.assembly import ScopeAssembly

class Fluidics(PhysicalObject):
	"""
	Describes utility functions for detecting and measuring chambers.
	"""

	def __init__(self, name, dia_mm=None, frames=None, **kwargs):
		super().__init__(name)
		self.type = "fluidics_device"
		self.attribs = kwargs


	def record():
		"""
		Records the current chamer into the Vault.
		"""
		ScopeAssembly.current.cam.capture("img", Vault.now(self.fludics))

		

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