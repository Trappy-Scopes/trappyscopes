from core.exceptions import TSBaseModelError

from dataclasses import dataclass

@dataclass
class BaseDevice: #ProcessorGroup

	"""
	This is the "Base" of all `device_type` objects in the trappy-scopes ecosystem.
	"""
	name: str
	id_: str | None = None
	description: str | None = None
	devicetype: str = "basedevice"

	def __post_init__(self):
		if self.id_ == None:
			self.id_ = self.name

	def Construct(name, devicetype, id_=None, description=None):
		if not devicetype in ["basedevice", "actuator", "detector", "processorgroup"]:
			raise TSBaseModelError

		## Imported here to prevent circular imports - thus an expensive call.
		from .actuator import Actuator
		from .detector import Detector
		from processorgroups.abstractprocessorgroup import ProcessorGroup
		basemodelmap = {"actuator": Actuator, "detector": Detector, 
						"basedevice": BaseDevice, "processorgroup": ProcessorGroup}

		return basemodelmap[devicetype](name, id_=id_, devicetype=devicetype, 
										description=description)