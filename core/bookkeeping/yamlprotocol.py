import yaml
import os

from rich import print

class YamlProtocol:


	def dump(file, state):
		with open(file, "w") as f:
			f.write(yaml.dump(state))
			#f.write(yaml.dump(state, dumper=yaml.SafeDumper))

	def load(file):
		if not os.path.isfile(file):
			print(f"[red]YamlProtocol.load : file not found : ˚{file}")
			return None

		payload = None
		with open(file, "r") as f:
			payload = yaml.load(f, Loader=yaml.Loader)
		return payload

	def append_list(file, element):

		load = []
		with open('sessions.yaml', 'r') as f:
			load = YamlProtocol.load(file)
		
		if not isinstance(load, list):
			print(f"[red]The yaml file is not a list: {file}")
		load = [load]
		load.append(element)
		
		with open('sessions.yaml', 'w') as f:
			load = yaml.dump(load, f, default_flow_style=False)



