import os
from pprint import pprint
import logging as log
import yaml
from yaml.loader import SafeLoader, Loader
import sys
import nanoid
import datetime
from colorama import Fore
import time


from rich import print
from rich.progress import track
from rich.text import Text

import config.common
from user import User
from sharing import Share

class Experiment:
	"""
	Experiment_name
		|- .experiment 			    (identifier)
		|- Experiment_name.yaml     (event logs)
		|- data1, data2, data3, ... (data - in the repository)
		|- postprocess              (postprocessed data)
		|- analysis                 (analysis results)

	"""

	###############
	current = None

	###############


	def new(name, append_eid=False):
		"""
		Create a new experiment with the given name.
		"""

		uuid = nanoid.generate('1234567890abcdef', 10)

		if append_eid:
			name = name + "_" + uuid


		dir_ = os.path.join(config.common.DATA_DIR, name)
		os.mkdir(dir_)
		os.mkdir(os.path.join(dir_, "postprocess"))
		os.mkdir(os.path.join(dir_, "analysis"))
		os.mkdir(os.path.join(dir_, "converted"))

		# Copy payload to the dir_

		with open(os.path.join(dir_, ".experiment"), "w") as f:
			f.write(uuid)

		with open(os.path.join(dir_, "experiment.yaml"), "w") as f:
			now = datetime.datetime.now()
			#print(yaml.dump({"Experiment created": [name, uuid]}))
			f.write(yaml.dump({"Experiment created": 
									{"name": name, 
									"uuid": uuid,
									"created": now}}))
		return name


	def list_all():
		"""
		Returns a list of all qualified experiments.
		"""
		all_dirs = os.listdir(config.common.DATA_DIR)
		all_dirs = [os.path.join(config.common.DATA_DIR, dir_) for dir_ in all_dirs if \
			os.path.isfile(os.path.join(config.common.DATA_DIR, dir_, ".experiment"))]
		return all_dirs

	def list_all_names():
		exps = Experiment.list_all()
		return [e.rsplit("/", 1)[1] for e in exps]


	def autosave(func, *args, **kwargs):
		def wrapper( *args, **kwargs):
			func( *args, **kwargs)
			Experiment.current.__save__()
		return wrapper

	def increment_counter(func, *args, **kwargs):
		def wrapper( *args, **kwargs):
			Experiment.current.counter += 1
			func( *args, **kwargs)
		return wrapper

	def __init__(self, name, append_eid=False):

		### Close current
		if isinstance(Experiment.current, Experiment):
			Experiment.current.close()



		self.all_exps = Experiment.list_all()
		self.name = name
		# Check if the experiment exists
		if not os.path.join(config.common.DATA_DIR, self.name) in self.all_exps:
			self.name = Experiment.new(self.name, append_eid=append_eid)
			log.info(f"Creating New Experiment: {self.name}")
			#log.info(f"{self.name}: {self.exp_dir}")


		self.exp_dir = os.path.join(config.common.DATA_DIR, self.name)
		self.log_file = os.path.join(self.exp_dir, "experiment.yaml")
		self.user = ""
		self.logs = {}
		self.events = []
		self.unsaved = False # Flag that indicates unsaved changes
		self.active = True   # Flag that indicates whether the Experiment is currently active.
		self.init_time = time.perf_counter()
		self.counter = 0

		#TODO self.metadata = Metadata()

		### Draw ruler
		from rich.rule import Rule
		print(Rule(title="Experiment open", align="center", style="green"))
		####


		log.info(f"Loading Experiment: {self.name}")
		print("Experiment so far: ")
		pprint([file for file in os.listdir(self.exp_dir) \
				if os.path.isfile(os.path.join(self.exp_dir, file))])
		
		# Load experiment logs
		with open(self.log_file) as file:
			logs_in_file = yaml.load(file, Loader=Loader)
		if logs_in_file:
			self.logs = logs_in_file
		
		self.events = list(self.logs.keys())
			

		## Read scope-id
		self.scopeid = ""
		with open("config/deviceid.yaml") as deviceid:
			device_metadata = yaml.load(deviceid, Loader=SafeLoader)
			self.scopeid = device_metadata["name"]


		# Changing Working Directory to Experiment Directory		
		Share.updateps1(exp=self.name)
		self.lastwd = os.getcwd()
		os.chdir(self.exp_dir)
		print(f"Working directory changed to: {os.getcwd()}")

		print("Devnotes: Experiment class TODO: submodule Metadata object.")


		## User Information
		self.logs["user"] = User.info

		Experiment.current = self

	
	def __repr__(self):
		end_time = time.perf_counter()
		return f"< Experiment: {self.name} :::: duration: {end_time-self.init_time:.3f} s >"

	def __save__(self):
		if self.active:
			with open(self.log_file, "w") as f:
				f.write(yaml.dump(self.logs))
		print(Text("⬤   exp logs saved.", style="green dim", justify="right"))

	def __exit__(self):
		self.close()

	def close(self):
		#if self.unsaved:
		end_time = time.perf_counter()
		print(f"Experiment duration: {end_time-self.init_time:.3f} seconds.")
		self.logs["exp_duration_s"] = end_time-self.init_time
		with open(self.log_file, "w") as f:
			f.write(yaml.dump(self.logs))
		print(f"Experiment logs updated: {self.log_file}")
		if self.active:
			print(f"Experiment {self.name} was closed.")
			os.chdir(self.lastwd)
			print(f"Working directory changed to: {os.getcwd()}")
			Share.updateps1(exp="")
			self.active = False
		from rich.rule import Rule
		print(Rule(title="Experiment closed", align="center", style="red"))

	def log(self, action, attrib={}):
		if action in self.logs:
			action = f"{action}-{time.time_ns()}"
		log_ = {"mtime": time.time_ns(), "dt":datetime.datetime.now()}
		log_.update(attrib)
		self.logs[action] = log_
		return action

	def log_event(self, string):
		"""
		Format -> Event: datetime
		"""
		if self.active:
			now = datetime.datetime.now() 
			self.logs[str(now)] = string
			self.events.append(string)
			self.unsaved = True
		else:
			print("Experiment is not active. Pleace use exp_close() function or start a new experiment.")

	def unique(self, string):
		return not (string in self.logs)


	def run(self, script):
		print(f"{Fore.RED} Executing script: {script}{Fore.RESET}")
		#with open(script) as f:
		#    exec(f.read(), globals())
		#script = script.split(".")[0]
		__import__(script, globals(), locals())

	def run(script):
		print(f"{Fore.RED} Executing script: {script}{Fore.RESET}")
		#with open(script) as f:
		#    exec(f.read(), globals())
		#script = script.split(".")[0]
		__import__(script, globals(), locals())

	def toggle_beacon(pico):
		pico("beacon.toggle()")

	### ----- Event Model -----------------------------

	
	@increment_counter
	@autosave
	def delay(self, name, seconds, steps=100):

		try:
			start = time.time_ns()
			for i in track(range(seconds), description=f"exp-step: blocking delay: {name} >> "):
			    time.sleep(seconds/steps)  # Simulate work being done
			self.log(name, attrib={"type":"delay", "duration":seconds, "start_ns":start, 
								   "end_ns": time.time_ns(), "interrupted": False, "counter":self.counter})
		except KeyboardInterrupt:
			self.log(name, attrib={"type":"delay", "duration":seconds, "start_ns":start,
					 "end_ns": time.time_ns(), "interrupted": True, "counter":self.counter})

	
	@increment_counter
	@autosave
	def track(self, name, task, *args, **kwargs):
		"""
		Track execution of anhy function and log.
		"""

		if "desc" not in kwargs:
			kwargs["desc"] = "No description."
		desc = kwargs["desc"]
		print(f"exp-step: Tracking task >> {name}")
		print(f"Task: {task}\nDescription: {kwargs.pop('desc')}")
		
		

		try:
			start = time.time_ns()
			print(desc)
			task(*args, **kwargs)
			
			end = time.time_ns()
			self.log(name, attrib={"type":"tracked_task", "duration":float(end-start)/1**-9, "start_ns":start, 
								   "end_ns": end, "interrupted": False, "task": str(task), "args": args, "kwargs":kwargs,
								   "description": desc, "counter":self.counter})
		except KeyboardInterrupt:
			end = time.time_ns()
			self.log(name, attrib={"type":"tracked_task", "duration":float(end-start)/1**-9, "start_ns":start,
								   "end_ns": end, "interrupted": True, "task": str(task), "args": args, "kwargs":kwargs,
								   "description": desc, "counter":self.counter})
	
	@increment_counter
	@autosave
	def user_prompt(self, prompt, label=None):
		prompt_ = prompt
		if prompt == None:
			prompt_ = "!!Any key!!"
		prompt_string = f"==> Waiting for prompt : ```{prompt_}```  >>> "
		
		def conditional(inp):
			print(inp)
			if isinstance(inp, str):
				inp = inp.strip()
			if prompt != None:
				return inp == prompt
			else:
				return True

		name = prompt
		if prompt == None:
			name = "prompt"

		event = self.log(name, attrib={"type": "user_prompt", "prompt":prompt,
									   "label":label, "counter":self.counter})
		
		self.logs[event]["prompt_requested"] = datetime.datetime.now()
		
		inp = "no_inp"
		inp = input(f"{Fore.RED}{prompt_string}{Fore.RESET}")
		while not conditional(inp):
			inp = input(f"{Fore.RED}{prompt_string}{Fore.RESET}")
		
		print(f"[green]--- prompt accepted : {prompt_} --- [default]")
		
		self.logs[event]["prompt_received"] = datetime.datetime.now()

	def follow_protocol(self, *args):
		pass

class Calibration(Experiment):
	
	def __init__(self, name, append_eid=False):
		super().__init__(name, append_eid=append_eid)
		self.exp_dir = os.path.join(config.common.CALIB_DIR, self.name)

class Test(Experiment):

	def __init__(self, name, append_eid=False):
		self.checks = []
		super().__init__(name, append_eid=append_eid)

	def check(self, callable_, *args, **kwargs):
		"""
		Only fails if exceptions are raised. TODO
		"""
		self.log(f"check-{len(self.checks)}", attrib={"check":str(callable_)})
		print(f"<< Check {len(self.checks)} >>")
		try:
			if not args and not kwargs:
				callable_()
			elif not args:
				callable_(kwargs)
			elif kwargs:
				callable_(args)
			else:
				callable_(args, kwargs)
			print(f"{Fore.GREEN}››{Fore.RESET} {callable_} : {Fore.GREEN}OK{Fore.RESET}")
			self.checks.append(1) ## Inverted

		except Exception as e:
			print(f"{Fore.RED}››{Fore.RESET} {callable_} : {Fore.RED}NOK{Fore.RESET}")
			print(Fore.RED)
			print(e)
			print(Fore.RESET)
			self.checks.append(0) ## Inverted

	def conclude(self):
		if sum(self.checks) == len(self.checks):
			print(f"{Fore.GREEN}All checks passed!{Fore.RESET}")
		print(f"Checks: {Fore.BLUE}{sum(self.checks)} / {len(self.checks)} passed.{Fore.RESET}")
		self.logs["checks_passed"] = [sum(self.checks), len(self.checks)]


if __name__ == "__main__":
	exp = Experiment("test")
	pprint(exp.list_all())
