import yaml
import os
from copy import deepcopy

class Fammods:
	"""
	Minimal module that can be used to keep track of multiple public/private git modules.
	"""

	default_config = {"name": None, "parent_dir": ".", "git_remote_links": []}
	auth = None


	def __configfile__(name):
		"""
		Private. Generates the configuration abs filename with the prescribed format.
		"""
		return os.path.abspath(os.path.join(os.path.expanduser("~"), f".fammods_config_{name}"))

	def __gitclone__(git_url, config):
		"""
		Private git clone function.
		"""
		modulefoldername = git_url.split("/")[-1].split(".")[0]
		fullpath = os.path.join(config["parent_dir"], modulefoldername)

		if os.path.isdir(fullpath):
			print("Error: fammodss gitclone: Folder already exists.", "\n", fullpath)
			return False

		if Fammods.auth:
			git_url = git_url.replace("https://", f"https://{Fammods.auth['username']}:{Fammods.auth['password']}")

		os.mkdir(fullpath)
		errno = os.system(f"git clone {git_url} {git_url}")
		print("fammods clone procedure returned exist code: ", errno)
		return errno == 0

	def new(name, parent_dir):
		"""
		Create a new family of modules.
		"""
		if os.path.isfile(Fammods.__configfile__(name)):
			print("Error: family name already exists!")
			return False

		if not os.path.isdir(parent_dir):
			print("Error: parent_dir is an invalid directory!")
			return False
		else:
			name = Fammods.__configfile__(name)

			config = deepcopy(Fammods.default_config)
			config.update({"name": name, "parent_dir": os.path.abspath(parent_dir)})

			with open(name, "w") as f:
				f.write(yaml.dump(config)) 
			return name

	def add(famname, git_url):
		"""
		Add a module to the family.
		"""
		with open(Fammods.__configfile__(famname), "r") as f:
			config = yaml.load(f, Loader=yaml.Loader)

		## Try installation
		success = Fammods.__gitclone__(git_url, config)

		if success:
			## Add to the list
			config["git_remote_links"].append(git_url)

			with open(name, "w") as f:
				yaml.dump(f, Fammods.config) 
			return name

	def gitpull(famname):
		"""
		call `git pull` on all modules.
		"""
		with open(Fammods.__configfile__(famname), "r") as f:
			config = yaml.load(f, Loader=yaml.Loader)
		here = os.getcwd()

		for git_url in config["git_remote_links"]:
			modfolder = os.path.join(config["parent_dir"], git_url.split("/")[-1].split(".")[0])

			try:
				os.chdir(modfolder)
				authstring = ""
				
				if Fammods.auth:
					git_url = git_url.replace("https://", f"https://{Fammods.auth['username']}:{Fammods.auth['password']}")
					authstring = git_url
				
				## Pull
				os.system(f"git pull {authstring}")

			except Exception as e:
				print(e)

			os.chdir(here)
	def set_auth(username, password):
		"""
		Set the authenticator for git interactions.
		"""
		Fammods.auth = {"username": username, "password": password}

	def unset_auth():
		"""
		Unset the authenticato for safety.
		"""
		Fammods.auth = None

