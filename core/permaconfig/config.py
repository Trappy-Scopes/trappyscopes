import os
import confuse
import logging
from copy import deepcopy
from rich import print
import logging as log

from ..exceptions import TS_ConfigNotFound


class TrappyConfig(confuse.Configuration):
	"""
	Trappy-Scopes configuration. It is meant to be used as a singleton class
	but does not enforce it.
	"""


	## current instance
	current = None

	## Config must be present at these two paths in the order of preference
	default_paths = [os.path.join(os.path.expanduser("~"), "trappyconfig.yaml"),
					 os.path.join(os.path.expanduser("~"), \
					 	".config", "trappyscopes", "trappyconfig.yaml")]


	def __init__(self):
		"""
		Initalize the configuration and configure the terminal environment for use.
		"""
		super().__init__('trappyscopes', __name__)

		found = False

		for file in TrappyConfig.default_paths:
			if os.path.exists(file):
				found = True
				self.set_file(file)
				print(f"[green][OK] [bold cyan]Trappy-Scopes[default] config set: {file}")
				break
		if not found:
			raise TS_ConfigNotFound("Config file not found.")

		## Configure logger
		try:
			from ..permaconfig import loggersettings
			logger = logging.getLogger()
			logger.setLevel(self["config"]["log_level"].get())  # or any level you need
			logger.addHandler(loggersettings.error_collector)
		except Exception as e:
			print(e)
			print(f"[red][NOK] [bold cyan]Trappy-Scopes[default] config: Logger configuration failed. Try importing core.permaconfig.loggersettings as it is.")
		

		## Configure rich
		try:
			from ..permaconfig import richsettings
		except Exception as e:
			print(e)
			print(f"[red][NOK] [bold cyan]Trappy-Scopes[default] config: rich configuration failed. Try importing core.permaconfig.richsettings as it is.")

		## Remove unactive blocks
		#for key, device in self["devices"].items():
		#	if "active" in device.keys():
		#		if device["active"].get() == False:
		#			#self.get().pop('devices', key)
		#			#log.info(f"Inactive device: {key}")


		## Singelton template
		TrappyConfig.current = self



	def all_config_paths(self):
		return list(set(deepcopy(Config.default_paths) + self["config_files"].get()))


	def get_feature():
		"""
		This is used for a subfunction where the validation is only performed
		if the feature is active.
		"""
		pass


	def panel(self):
		"""
		Draw a panel with all the nested configuration.
		"""
		from rich.pretty import Pretty
		from rich.panel import Panel
		from rich.tree import Tree
		from collections import OrderedDict

		def dict_to_tree(d, tree=None):
		    if tree is None:
		        tree = Tree("root")
		    for key, value in d.items():
		        if isinstance(value, dict) or isinstance(value, OrderedDict):
		            branch = tree.add(f"[bold]{key}[/bold]")
		            dict_to_tree(value, branch)
		        else:
		            tree.add(f"[bold]{key}[/bold]: {value}")
		    return tree

		devicepanel = Panel(dict_to_tree(self.get()), title="Device")
		print(devicepanel)

