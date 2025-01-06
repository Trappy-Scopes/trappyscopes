import types
import logging as log
from importlib import import_module


from core.exceptions import MissingConfigException
from basedevice import BaseDevice



from rich.console import Console
console = Console()


class DynamicDevice:
	
	def __init__(self, deviceconfig):
		"""
		The part of configuration that is specific to the device.
		This is a temporary object that creates and returns another
		object. This class should be viewed as a factory object.

		deviceconfig should be of the form: {name: {<configs>}}
		"""
		dynamic_name = deviceconfig.keys()[0]
		dynamic = types.new_class(f"<DynamicDevice-{dynamic_name}>", (BaseDevice,))

		for dev_name, dev_spec in deviceconfig.values():
			if isinstance(dev_spec, dict):
				try:
					device = self.dynamic_creator(dev_name, dev_spec)
				except Exception:
					console.print_exception(show_locals=True)
					log.error(f"Sub-device construction failed for {dynamic_name}: {device}.")
					device = None

				if device != None:
					setattr(dynamic, dev_name, device)
					log.debug(f"Constructed sub-device for {dynamic_name}: {device}.")
		return dynamic

	def dynamic_creator(self, name, subconfig):
		"""
		name : name of the object.
		subconfig: Configuration that defines a single object.
		#todo implement the tag keyword
		"""
		if not all(["tag", "kind"]) in subconfig:
			raise MissingConfigException

		## Attempt import
		try:
			constructor = import_module(subconfig["kind"])
		except ImportError:
			log.error(f"Module not found: {constructor}")
			subdevice = None
			return subdevice
		
		## Attempt construction
		try:
			subdevice = constructor(*subconfig["args"], **kwargs["kwargs"])
			return subdevice

		


