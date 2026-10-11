import nanoid


## Default generators shipped by Trappyscopes

def uid():
	"""Default 10 digit-hex uid"""
	return nanoid.generate('1234567890abcdef', 10)
## Default generators shipped by Trappyscopes


class UIDEngine:
	""" UID engine that returns the set uid generator. Right now, it returns only the default one."""
	def get(key):
		return uid
