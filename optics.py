class Lenses:

	class ZoomLens:
		def __init__(self):
			pass
		def __getstate__(self):
			return {"name": "zoomlens", "type": "optics.lenses.zoomlens"}

		def __repr__(self):
			return f"< Optics.Lenses.Zoomlens >"
	class Asphere:

		models = {"ACL2520U-DG6": {"name":"ACL2520U-DG6", "dia_mm":25, 
								   "focal_length_mm":20.1, "NA":0.60,
								   "grit": 600, "coating": "uncoated",
								    "vendor": "ThorLabs"},
				  "ACL2520U"     : {"name":"ACL2520U", "dia_mm":25, 
								   "focal_length_mm":20.1, "NA":0.60,
								   "grit": 0, "coating": "uncoated",
								    "vendor": "ThorLabs"},
				 }
		def __init__(self, name):
			self.name = name
			self.attribs = {"name": self.name, "type": "optics.lenses.main_asphere"}
			if self.name in Lenses.Asphere.models:
				self.attribs = Lenses.Asphere.models[self.name]
				self.attribs["type"] = "optics.lenses.asphere"
		def __getstate__(self):
			return self.attribs

		def __repr__(self):
			vendor = ""
			if "vendor" in self.attribs:
				vendor = self.attribs["vendor"]
			return f"< Optics.Lenses.Asphere :: {self.name} {vendor} >"


class Optics:

	lenses = []
	assembly = []


	def populate(partialdevice):
		if "lenses" in partialdevice:
			for l in partialdevice["lenses"]:
				if "zoomlens" in l:
					Optics.lenses.append(Lenses.ZoomLens())
				else:
					Optics.lenses.append(Lenses.Asphere(l))