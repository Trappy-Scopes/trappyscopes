import os
from pprint import pprint
import logging as log
import yaml
from yaml.loader import SafeLoader
import sys
import nanoid
import datetime
from colorama import Fore

import config.common


class Experiment:
	"""
	Experiment_name
		|- .experiment 			    (identifier)
		|- Experiment_name.yaml     (event logs)
		|- data1, data2, data3, ... (data - in the repository)
		|- postprocess              (postprocessed data)
		|- analysis                 (analysis results)

	"""

	def new(name):
		"""
		Create a new experiment with the given name.
		"""
		dir_ = os.path.join(config.common.DATA_DIR, name)

		os.mkdir(dir_)
		os.mkdir(os.path.join(dir_, "postprocess"))
		os.mkdir(os.path.join(dir_, "analysis"))

		# Copy payload to the dir_

		uuid = nanoid.generate('1234567890abcdef', 10)
		with open(os.path.join(dir_, ".experiment"), "w") as f:
			f.write(uuid)

		with open(os.path.join(dir_, "experiment.yaml"), "w") as f:
			now = datetime.datetime.now()
			#print(yaml.dump({"Experiment created": [name, uuid]}))
			f.write(yaml.dump({"Experiment created": 
									{"name": name, 
									"uuid": uuid,
									"created": now}}))


	def list_all():
		"""
		Returns a list of all qualified experiments.
		"""
		all_dirs = os.listdir(config.common.DATA_DIR)
		all_dirs = [os.path.join(config.common.DATA_DIR, dir_) for dir_ in all_dirs if \
			os.path.isfile(os.path.join(config.common.DATA_DIR, dir_, ".experiment"))]
		return all_dirs

	def __init__(self, name):

		self.name = name
		self.exp_dir = os.path.join(config.common.DATA_DIR, name)
		self.log_file = os.path.join(self.exp_dir, "experiment.yaml")
		
		self.logs = {}
		self.events = []
		self.unsaved = False # Flag that indicates unsaved changes
		self.active = True   # Flag that indicates whether the Experiment is currently active.

		self.all_exps = Experiment.list_all()

		# Check if the experiment exists
		if not os.path.join(config.common.DATA_DIR, self.name) in self.all_exps:
			Experiment.new(self.name)
			log.info(f"Creating New Experiment: {self.name}")
			log.info(f"{self.name}: {self.exp_dir}")

		log.info(f"Loading Experiment: {self.name}")
		print("Experiment so far: ")
		pprint([file for file in os.listdir(self.exp_dir) \
				if os.path.isfile(os.path.join(self.exp_dir, file))])
		
		# Load experiment logs
		with open(self.log_file) as file:
			logs_in_file = yaml.load(file, Loader=SafeLoader)
		if logs_in_file:
			self.logs = logs_in_file
		
		self.events = list(self.logs.keys())
			

		# Changing Working Directory to Experiment Directory		
		sys.ps1 = self.header()
		self.lastwd = os.getcwd()
		os.chdir(self.exp_dir)
		print(f"Working directory changed to: {os.getcwd()}")

	
	def __exit__(self):
		self.close()

	def close(self):
		if self.unsaved: 
			with open(self.log_file, "w") as f:
				f.write(yaml.dump(self.logs))
			print(f"Experiment logs updated: {self.log_file}")
		if self.active:
			print(f"Experiment {self.name} was closed.")
			os.chdir(self.lastwd)
			print(f"Working directory changed to: {os.getcwd()}")
			sys.ps1 = ">>> "
			self.active = False

	def log_event(self, string):
		"""
		Format -> Event: datetime
		"""
		if self.active:
			now = datetime.datetime.now() 
			self.logs[string] = str(now)
			self.events.append(string)
			self.unsaved = True
		else:
			print("Experiment is not active. Pleace use exp_close() function or start a new experiment.")

	def unique(self, string):
		return not (string in self.logs)

	def header(self):
		return f"|| Experiment: {Fore.RED}{self.name}{Fore.RESET} >>> "


	def run(script):
		print(f"{Fore.RED} Executing script: {script}{Fore.RESET}")
		#with open(script) as f:
		#    exec(f.read(), globals())
		#script = script.split(".")[0]
		__import__(script, globals(), locals())

	def toggle_beacon(pico):
		pico("beacon.toggle()")

if __name__ == "__main__":
	exp = Experiment("test")
	pprint(exp.list_all())
