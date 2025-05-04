

class TS_ConfigNotFound(Exception):
	...

class TS_InvalidNameException(Exception):
	"""
	Raised when an invalid name is passed and normal error handling is not sufficient.
	Example: during object creation -> use to quit object creation altogether when an
	invalid name is passed.
	"""
	...


class TSDeviceNotRegistered(Exception):
	...

class TSDeviceCreationFailed(Exception):
	...

class MissingConfigException(Exception):
	"""
	Raised when essential configuration is missing.
	"""
	...

class TSBaseModelError(Exception):
	"""
	Called when the construction is of a type other than "basedevice", "actuator", or "detector".
	"""