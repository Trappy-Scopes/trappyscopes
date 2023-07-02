import os
from pprint import pprint
import logging as log
import yaml
from yaml.loader import SafeLoader
import sys
import uuid

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

		with open(os.path.join(dir_, ".experiment"), "w") as f:
			f.write(str(uuid.uuid4()))

		with open(os.path.join(dir_, f"{name}.yaml"), "w") as f:
			f.write("")


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
		self.log_file = os.path.join(self.exp_dir, f"{name}.yaml")
		self.logs = {}
		self.events = []

		self.all_exps = Experiment.list_all()
		# Check if the experiment exists

		
		if os.path.join(config.common.DATA_DIR, self.name) in self.all_exps:
			log.info(f"Loading Experiment: {self.name}")
			pprint(os.listdir(self.exp_dir))
			
			# Load experiment logs
			self.logs = yaml.load(self.log_file, SafeLoader)
			print("!!!", self.logs)
			#self.events = list(self.logs.keys())
		else:
			Experiment.new(self.name)
			log.info(f"Creating New Experiment: {self.name}")
			log.info(f"{self.name}: {self.exp_dir}")
		sys.ps1 = self.header()



	def __del__(self):
		#with open(self.exp_file, "r") as f:
		#	yaml.dump(self.logs, f)
		pass

	def log_event(self, string):
		"""
		Format -> Event: datetime
		"""
		now = datetime.datetime.now() 
		self.log[string] = str(now)
		self.events += string

	def header(self):
		return f"|| Experiment: {self.name} >>> "

if __name__ == "__main__":
	exp = Experiment("test")
	pprint(exp.list_all())
