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


