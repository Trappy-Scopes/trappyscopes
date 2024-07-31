

class TS_InvalidNameException(Exception):
	"""
	Raised when an invalid name is passed and normal error handling is not sufficient.
	Example: during object creation -> use to quit object creation altogether when an
	invalid name is passed.
	"""
	...


class TSDeviceNotRegistered(Exception):
	...