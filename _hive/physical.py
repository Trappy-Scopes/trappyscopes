

class PhysicalObject(object):
	current = self
	def __init__(self, name, **kwargs):
		self.name = name
		self.type = None
		self.attribs = kwargs
		PhysicalObject.current = self

	def __getstate__(self):
		return {"name": self.name, "type": self.type, **self.attribs}
