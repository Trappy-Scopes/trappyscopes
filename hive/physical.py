import shelve
import os

class PhysicalObject(object):
	"""
	
	"""


	def __init__(self, name, kind=None, persistent=False, **kwargs):		
		self.attribs = kwargs
		self.attribs["name"] =  name
		self.attribs["kind"] =  kind
		self.persistent = persistent


		if persistent:
			state = shelve.open(os.path.join(os.path.expanduser("~"), name))

			## Current should override state
			for key, value in self.attribs.items():
				state[key] = value
			
			self.attribs = state


	def __getstate__(self):
		return {key:value for key, value in self.attribs.items()}

	def __close__(self):
		if self.persistent:
			self.attribs.sync()
			self.attribs.close()

	def __repr__(self):
		n = 3
		preview = list(self.attribs.items())[:n]
		preview_repr = ", ".join(f"{k!r}: {v!r}" for k, v in preview)
		suffix = "..." if len(self.attribs) > n else ""
		return f"< PhysicalObject{'-persistent'*self.persistent} :: {preview_repr}{suffix} >"

	def __getitem__(self, key):
		return self.attribs[key]

	def __setitem__(self, key, value):
		self.attribs[key] = value
