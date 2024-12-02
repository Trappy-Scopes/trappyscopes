


class ScopeFrame:
	frame = []

	def populate(partialdevice):
		if "frame" in partialdevice:
			print("Device metadata has scope-frame information.")
			ScopeFrame.frame = partialdevice["frame"]
		else:
			print("No scope-frame information found.")