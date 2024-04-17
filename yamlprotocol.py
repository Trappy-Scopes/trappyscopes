import yaml

class YamlProtocol:


	def dump(file, state):
		with open(file, "w") as f:
			f.write(yaml.dump(state))
			#f.write(yaml.dump(state, dumper=yaml.SafeDumper))

	def load(file):
		with open(file, "r") as f:
			yaml.load(file, Loader=yaml.Loader)



