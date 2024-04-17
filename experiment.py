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
from collections import OrderedDict

from rich import print
from rich.progress import track
from rich.text import Text
from rich.prompt import Prompt
from rich.rule import Rule

import config.common
from user import User
from sharing import Share
from utilities.resolvetypes import resolve_type
from bookeeping.session import Session
from uid import uid
from yamlprotocol import YamlProtocol
from devicestate import sys_perma_state


class Experiment:
	"""
	
	## Metadata and fields
		|- name
		|- eid (uid)
		|- created
		|- system-info (syspermastate)
		|- camera-info !!!
		|-Session
		:	|- sid (uid) 
		:	|- <User login info>
		:	|- <git commit details>
		:	|- <python package information>
		:	|- <eid>
		:	|- <last-counter>
		|- Measurements
		:	|- series1
		:	|- series2
		|- <Event 1>
		|- <Event 2>
		|- <Event 3>
		|- <Event n>


	## File structure
	<Experiment_name>
		|- .experiment 			    (identifier)
		|- Experiment_name.yaml     (event logs)
		|- data1, data2, data3, ... (data - in the repository)
		|- postprocess              (postprocessed data)
		|- analysis                 (analysis results)
	## Clean until exp.events() return  coherant and chronological sequence of
	## experiment steps.


	"""


	#####SINGLETON#####
	current = None
	#####SINGLETON#####


	def new(name, append_eid=False):
		"""
		Create a new experiment with the given name.
		"""

		uuid = uid()

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
			f.write(yaml.dump({"name": name, 
							   "uuid": uuid,
							   "created": now,
							   "syspermastate": sys_perma_state()}))
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
		

		self.logs = OrderedDict()

		self.unsaved = False # Flag that indicates unsaved changes
		self.active = True   # Flag that indicates whether the Experiment is currently active.
		self.init_time = time.perf_counter()
		self.counter = 0
		self.exp_timer = 0 ### Populated by time.perf_counter() values.
		self.attribs = {}
		self.modalities = {} ## Measuremnt modalities
		#TODO self.metadata = Metadata()

		### Draw ruler
		from rich.rule import Rule
		print(Rule(title="Experiment open", align="center", style="green"))
		####
		log.info(f"Loading Experiment: {self.name}")

		# Load experiment logs
		with open(self.log_file) as file:
			logs_in_file = yaml.load(file, Loader=Loader)
		if logs_in_file:
			self.logs = logs_in_file
		
			

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
		print(f"[cyan]{self.filetree()}[default]")

		print("Devnotes: Experiment class TODO: submodule Metadata object.")


		## User Information
		self.logs["user"] = User.info

		self.log("session", attrib=Session.current.__getstate__())
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
			os.chdir(self.lastwd)
			print(f"Working directory changed to: {os.getcwd()}")
			Share.updateps1(exp="")
			self.active = False
		from rich.rule import Rule
		print(Rule(title="Experiment closed", align="center", style="red"))

	def filetree(self):
		"""
		Print the current file tree of the experiment.
		"""
		from subprocess import run
		out = run(["tree", "-a"], capture_output=True, text=True)
		return out.stdout


	def set_sync_flag(self):
		"""
		Mark the experiment for synchronisation.
		"""
		syncid = uid()
		sync = {"sync": True, "syncid": syncid, "dt": datetime.datetime.now()}
		YamlProtocol.dump(".sync", sync)
		log.critical(f"Set experiment syncronisation with syncid: {syncid}")
		self.log("set_sync", attrib={"syncid": syncid})

	def unset_sync_flag(self):
		"""
		Umark the experiment **explicitly** for synchronisation.
		Note: In the absence of .sync file, syncronisation is not performed.
		"""
		if os.path.isfile(".sync"):
			os.remove(".sync")
		log.critical("Unset experiment syncronisation.")
		self.log("unset_sync")


	def log(self, action, attrib={}):
		if action in self.logs:
			action = f"{action}-{time.time_ns()}"
		log_ = {"mtime": time.time_ns(), "dt":datetime.datetime.now()}
		log_.update(attrib)
		self.logs[action] = log_
		return action

	def events(self):
		return list(self.logs.keys())

	def log_event(self, string):
		"""
		Format -> Event: datetime. ### Obsolete
		"""
		if self.active:
			now = datetime.datetime.now() 
			self.logs[str(now)] = string
			self.unsaved = True
		else:
			print("Experiment is not active. Please use exp_close() function or start a new experiment.")

	### User text & metadata entry


	@increment_counter
	@autosave
	def note(self, string):
		self.log("user_note", attrib={"note": string, "type":"user_note"})

	def write(self):
		"""
		Wrapper that opens the user prompt. Maybe more modalities - confusion, problem, e
		"""
		inp = Prompt.ask("[blue] User Note >>> ")
		self.note(inp)
		return inp

	@increment_counter
	@autosave
	def add_attrib(key, value):
		"""
		Is this a useful function?
		Add an attribute to the Experiment object.
		"""
		self.attribs[key] = value

	###

	def unique(self, string):
		return not (string in self.logs)

	def __sanatize__(self, name):
		return name

	def __node_validator__(self, name, type_=None):
		"""
		Validate node/acquisition/filenames
		"""
		return True
	def __head_validator__(name):
		"""
		Validate experiment directory name.
		"""
		return True


	## ----- Measurements ----------------------------
	def new_measuement(self, name, measurand={}, attribs={}):
		"""
		Returns a Stream wrapper aroind a given measurement object.
		"""
		onemeasure = Measurement(name, measurand=measurand, attribs=attribs)
		self.modalities[name] = onemeasure
		log.log(f"Added measurment modality: {name}")
		return self.modalities(self.modalities[name]).Stream()



	### ----- Event Model -----------------------------

	
	@increment_counter
	@autosave
	def delay(self, name, seconds, steps=100):
		"""
		Add a experiment step dealy with a progress bar and automatic logging.
		Todo: Correct processor drift.
		"""
		try:
			start = time.time_ns()
			print(start)
			for i in track(range(steps), description=f"exp-step: blocking delay: [red]{name}[default] | [cyan]{seconds}s[default] >> "):
			    time.sleep(seconds/steps)  # Simulate work being done
			self.log(name, attrib={"type":"delay", "duration":seconds, "start_ns":start, 
								   "end_ns": time.time_ns(), "interrupted": False, "counter":self.counter})
		except KeyboardInterrupt:
			self.log(name, attrib={"type":"delay", "duration":seconds, "start_ns":start,
					 "end_ns": time.time_ns(), "interrupted": True, "counter":self.counter})
		print(time.time_ns())

	
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

	@increment_counter
	@autosave
	def multiprompt(self, callables, labels=[]):
		"""
		The received prompt is sent through all callable functions in sequence.
		A callable that accepts the prompt must return True.
		A callbale function takes one arguement : the prompt which has been type deducted and cleaned.
		"""
		#labels = [str(l) for l in labels]
		startdt = datetime.datetime.now()
		inp = Prompt.ask(f"Experiment user-multiprompt :: [cyan]choices: {labels}[default]", default=False)
		
		inp = resolve_type(inp)

		callableid = -1
		for i, call in enumerate(callables):
			response = call(inp)
			#print("closure: ", call.__closure__)
			if response == True:
				callableid = i
				break
		if callableid == -1:
			print(Rule(title=f"Exp multiprompt >> Prompt not accepted : {inp}!", align="center", style="red"))
			self.log("user_multiprompt", attrib={"type": "user_multiprompt", "prompt":inp, \
					  "choices":labels, "counter":self.counter, \
					  "accepted": False, "prompt_requested":startdt, "prompt_received": datetime.datetime.now()})
		else:
			print(Rule(title=f"Exp multiprompt >> Prompt accepted: {inp} : {callables[callableid]}", align="center", style="green"))
			self.log("user_multiprompt", attrib={"type": "user_multiprompt", "prompt":inp, \
					  "choices":labels, "counter":self.counter, \
					  "accepted": True, "prompt_requested":startdt, "prompt_received": datetime.datetime.now()})
		return inp


	@increment_counter
	@autosave
	def interrupted(self):
		"""
		Marks an interrupt event - Experiment flow was interrupted by the user.
		"""
		self.log("interrupted", attrib={"type": "interrupt",
									    "counter":self.counter})


	### ───────────────────────────── Timers ──────────────────────────────
	def start_timer(self):
		self.exp_timer = time.perf_counter()
		return self.exp_timer
	def timer_elapsed(self):
		return time.perf_counter() - self.exp_timer

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
