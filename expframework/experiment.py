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
import schedule
from threading import Thread
import pickle
import atexit

from rich import print
from rich.progress import track
from rich.text import Text
from rich.prompt import Prompt
from rich.rule import Rule
from rich.align import Align
from rich.panel import Panel
from rich.pretty import Pretty


from utilities.resolvetypes import resolve_type

from core.permaconfig.config import TrappyConfig

from core.bookkeeping.user import User
from core.permaconfig.sharing import Share
from core.bookkeeping.session import Session
from core.uid import uid
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.bookkeeping.systeminfo import sys_perma_state
from core.exceptions import TS_InvalidNameException
from core.tsevents import TSEvent
from core.idioms.clock import Clock

from .report import ExpReport
from .expsync import ExpSync
from .notebook import ExpNotebook
from .clockgroup import ClockGroup

class ExpEvent(TSEvent):
	def __init__(self, kind="expevent", attribs={}):
		super().__init__()
		
		self.update({
					"type"       : kind, ## Can be overrided here.
			 		"eid"        : Experiment.current.eid,
					"scriptid"   : Experiment.current.scriptid,
			  		"exptime"    : Experiment.current.expclock.time_elapsed()
		   			})
		self.update(attribs)
		
ExperimentEvent = ExpEvent


class ExpScheduler(schedule.Scheduler):
	def __init__(self):
		super().__init__()
		self.thread = None
		self.end_thread = False
		self.loop()

	def post_register(self, name):
		Experiment.current.log("periodic_task", 
			attribs={"name": name, "info": str(self.get_jobs()[-1])})
	def loop(self):
		def callback():
			while not self.end_thread:
				self.run_pending()
				time.sleep(0.5)
			print("Experiment.schedule.loop has been terminated.")
		self.thread = Thread(name="exp.schedule.loop", target=callback)
		self.thread.start()

class Experiment(ExpSync, ExpReport, ExpNotebook, ClockGroup):
	"""

	A Trappy-Scope Experiment.
	.
	|- header < name, eid, path, syncpath, ...>
	|- params (experiment parameters, what is being perturbed?)
	|- clocks (timing)
	|- events (chronological record of what happened)
	|- measurements (MeasurementStreams)
	|- scheduler (scheduler -> actions)
	*


	ExperimentEvents are emiited into the experiment.yaml file.
	An experiment is qualified programaatically as a directory with a .experiment file.
	A Measurement is a "special" event that contains scientific data.


				.
			 	|---> Events (user actions, actuator movements, file_emissions, acquisitions, measurement_stream)
	Experiment--|
	Event		|---> Measurements
				·
	
	## Experiment is structured as follows.
	<experiment_name>.yaml file
		.
		|- name
		|- eid (uid)
		|- created
		|- system-info (syspermastate)
		|- <sessions.yaml>
		:	|- sid (uid) 
		:	|- <User login info>
		:	|- <git commit details>
		:	|- <python package information>
		:	|- <eid>
		:	|- <last-eventid>
		|- Measurements / results
		:	|- series1
		:	|- series2
		|- <Event 1>
		|- <Event 2>
		|- <Event 3>
		|- <Event n>


	## File structure
	<Experiment_name>
		|- .git                     (optional - git repository of the experiment)
		|- .experiment 			    (identifier)
		|- .sync                    (Experiment has been setup for synchronisation)
		|- .analysis                (Information about use in specific analyses)
		|- <experiment_name>.yaml   (experiment logs)
		|- <logs>
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


		dir_ = os.path.join(os.path.expanduser(TrappyConfig.current["config"]["expdir"].get()), name)
		os.mkdir(dir_)
		os.mkdir(os.path.join(dir_, "postprocess"))
		os.mkdir(os.path.join(dir_, "analysis"))
		os.mkdir(os.path.join(dir_, "converted"))
		os.mkdir(os.path.join(dir_, "scripts"))


		# Copy payload to the dir_
		with open(os.path.join(dir_, ".experiment"), "w") as f:
			f.write(uuid)


		# Create experiment.yaml and sessions.yaml file
		with open(os.path.join(dir_, "experiment.yaml"), "w") as f:
			now = datetime.datetime.now()
			#print(yaml.dump({"Experiment created": [name, uuid]}))
			init_md = {"name": name, 
					   "eid": uuid,
					   "created": now,
					   "syspermastate": sys_perma_state()}
			f.write(yaml.dump(init_md))
			print(init_md)

		with open(os.path.join(dir_, "sessions.yaml"), "w") as f:
			f.write(yaml.dump([]))
		Session.current = Session(name=uuid)

		return name

	def list_all():
		"""
		Returns a list of the fullpath of all qualified experiments.
		"""
		data_dir = os.path.expanduser(TrappyConfig.current["config"]["expdir"].get())
		all_dirs = os.listdir(data_dir)
		all_dirs = [os.path.join(data_dir, dir_) for dir_ in all_dirs if \
			os.path.isfile(os.path.join(data_dir, dir_, ".experiment"))]
		return all_dirs

	def list_all_names():
		"""
		Returns a list of just the names of all qualified experiments.
		"""
		exps = Experiment.list_all()
		return [e.rsplit("/", 1)[1] for e in exps]

	def list_all_eids():
		"""
		Return a dict with eid: experiment name.
		"""
		exps = Experiment.list_all()
		expmap = {open(os.path.join(exp, ".experiment"), "r").read()
					: exp.rsplit("/", 1)[1] for exp in exps}
		return expmap

	def list_all_pathmap():
		"""
		Returns a dictionary of all the experiment names with fullpaths.
		"""
		exps = Experiment.list_all()
		expnames = Experiment.list_all_names()
		return dict(zip(expnames, exps))



	def autosave(func, *args, **kwargs):
		"""
		Decorator that can be used to save the experiment file after certain changes
		are made.
		"""
		def wrapper( *args, **kwargs):
			ret = func( *args, **kwargs)
			Experiment.current.__save__()
			return ret
		return wrapper

	def is_event(func, *args, **kwargs):
		"""
		Decorate a meember function as a function that generates an event.
		"""
		def wrapper( *args, **kwargs):
			Experiment.current.eventid += 1
			ret = func( *args, **kwargs)
			return ret
		return wrapper


	def Construct(attribs, *args, scopeid=True, username=True, 
				  date=True, time=True, eid=True, **kwargs):
		scopeid_ = f"{Share.scopeid}__" * scopeid
		username_ = f"{User.name()}__"  * date
		date_ = f"{Share.get_date_str()}__" * date
		time_ = f"{Share.get_time_str()}__" * time
		namestr = ""
		for key in [scopeid_, username_, date_, time_, *[f"{attr}_" for attr in attribs]]:
			namestr +=key
		log.debug(f"Constructed experiment name: {namestr}__<eid>")
		return Experiment(namestr, *args, append_eid=eid, **kwargs)
		


	def __init__(self, name, append_eid=False, **kwargs):
		"""
		Create an experiment.

		name: Experiment name.
		append_eid : append the experiment eid at the end of the name.
		Other common kwargs: md -> experiment metadata passed to Experiment.Construct.
		"""

		### Close current - if open
		if isinstance(Experiment.current, Experiment):
			Experiment.current.close()

		all_exps = Experiment.list_all()
		
		## First stage validation -> detect obvious culprits
		if not self.__head_validator__(name):
			raise TS_InvalidNameException(f"Experiment name invalid!")
		
		## Clean experiment name
		self.name = self.__sanatize__(name)
		
		## Second stage validaion -> detect any unwanted artifacts.
		if not self.__head_validator__(name):
			raise TS_InvalidNameException(f"Sanatized experiment name invalid!")
		

		# Check if the experiment exists -> a sanatised and valid name is guaranted
		# to pass through and will always be recovered.
		data_dir = os.path.expanduser(TrappyConfig.current["config"]["expdir"].get())
		if not os.path.join(data_dir, self.name) in all_exps:
			self.name = Experiment.new(self.name, append_eid=append_eid)
			log.info(f"Creating new experiment: {self.name}")

		self.exp_dir = os.path.join(data_dir, self.name)
		self.log_file = os.path.join(self.exp_dir, "experiment.yaml")
		

		### Draw ruler -> declare the experiment open!
		from rich.rule import Rule
		print(Rule(title="Experiment open", align="center", style="green"))
		log.info(f"Loading Experiment: {self.name}")


		## Load logs
		self.logs = YamlProtocol.load(self.log_file)
		if not self.logs:
			log.error("Experiment logs missing!")
			self.logs = OrderedDict()

		### ------ Create the state of the experiment  --------
		self.attribs = {}   ## Persistent experiment parameters.
		self.mstreams = {}  ## Measuremnt streams that are conserved over sessions.

		## Different experiment clocks
		self.expclock = Clock()
		self.all_clocks = {}  ## Set of all timers.

		self.schedule = ExpScheduler() ## TODO: Scheduler would not automatically restart.
		### ---------------------------------------------------


		## Load experiment state
		pickle_file = os.path.join(self.exp_dir, "expstate.pickle")
		if os.path.exists(pickle_file):
			try:
				with open(pickle_file, "rb") as file:
					state = pickle.load(file)
					self.__setstate__(state)
					log.info("Experiment state found and loaded!")
			except Exception as e:
				print(f"[red] Exception raised: {e}")
				log.error("Failed to load experiment state.")
		else:
			log.warning("Experiment state not found. Not a problem if this is a new experiment.")


		# Changing Working Directory to Experiment Directory		
		Share.updateps1(exp=self.name)
		self.lastwd = os.getcwd()
		os.chdir(self.exp_dir)
		print(f"Working directory changed to: {os.getcwd()}")
		print(f"[cyan]{self.filetree()}[default]")


		## User Information
		self.logs["user"] = User.info
		if "results" not in self.logs:
			self.logs["results"] = []
		if "events" not in self.logs:
			self.logs["events"] = []

		## eid and scriptid
		if "eid" in self.logs:
			self.eid = self.logs["eid"]
		else:
			self.eid = None
			log.critical("Experiment id is missing!")
		self.scriptid = None

		## Session
		YamlProtocol.append_list("sessions.yaml", 
								 {"eid": self.eid,
					  			  **Session.current.__getstate__()}
					  			)
		

		self.sessions = YamlProtocol.load("sessions.yaml")
		
		self.unsaved = False # Flag that indicates unsaved changes
		self.active = True   # Flag that indicates whether the Experiment is currently active.
		self.eventid = 0


		
		
		## ExpSync
		self.destination_dir = None
		if "destination_dir" in self.logs:
			self.destination_dir = self.logs["destination_dir"]
		super().__init__(self.name, 
						 destination_dir=self.destination_dir)
		
		### Set the current pointer
		## Don't move this!
		Experiment.current = self

		## ExpReport
		ExpReport.__init__(self, self.eid)

		## Start logging events
		self.log("session", attribs={"sessionid": Session.current.__getstate__()["name"]})
		

		## Patch
		self.params = self.attribs

		self.copy_payload()
	
	def __repr__(self):
		return f"< Experiment: {self.name} :::: duration: {self.expclock.time_elapsed():.3f} s >"

	

	def __getstate__(self):
		## Attributes and streams are non-fungable and should be pickled.
		return {"mstreams": self.mstreams, "attribs": self.attribs, 
				"expclock": self.expclock, 
				"all_clocks": self.all_clocks}
	
	def __setstate__(self, state):
		## Attributes and streams are non-fungable and should be pickled.
		self.mstreams = state["mstreams"]
		self.attribs = state["attribs"]
		self.expclock = state["expclock"]
		self.all_clocks = state["all_clocks"]
	
	def __save__(self):
		if self.active:
			with open(self.log_file, "w") as f:
				f.write(yaml.dump(self.logs))
		print(Align.right(Text("⬤   exp logs saved", style="green dim", justify="right")))


	def copy_payload(self, payload=None, kind="scripts"):
		"""
		Copy a given payload inside the experiment folder. Copying is skipped if the payload already exists. If the version changes,

		TODO: check versioned paths for directory comparisons.

		For directories, each file stat is compared.
		payload: list of files or directories.
		kind: defaults to "scripts". A descriptor of the payload. The value is used to create a folder where the payload is appended.
		"""
		import shutil
		import filecmp
		if payload == None:
			from .scriptengine import ScriptEngine
			payload = ScriptEngine.payload
		#payload = list(payload)
		os.makedirs(kind, exist_ok=True)
		
		for file in payload:
			script_shortname = os.path.basename(os.path.normpath(file))
			#print(script_shortname)
			potential_path = os.path.join(self.exp_dir, kind, script_shortname)
			type_ = "file"
			copy_fn = shutil.copy2
			if os.path.isdir(file):
				type_ = "dir"
				copy_fn = shutil.copytree
			
			if os.path.exists(potential_path):
				compare = None
				if type_ == "file":
					compare = filecmp.cmp(file, potential_path, shallow=False)
				else: ## Assume its a directory
					compare = filecmp.dircmp(file, potential_path) ## shallow was not defined before python 3.13
				
				if compare:
					## Payload already exists
					self.log_event("payload_skip", attribs={"path":file, "payload":os.path.join(kind, script_shortname), "payload_kind":kind})
				else:
					## Payload already exists but version has changed
					ext = os.path.splitext(script_shortname)[1]
					all_files = os.listdir(os.path.join(self.exp_dir, kind))
					versions = [file for file in all_files if script_shortname.replace(ext, "") in file]
					next_version = len(versions)
					new_version_name = str(script_shortname).replace(ext, "") + f"_v{next_version}" + ext
					self.log_event("payload_version_change", attribs={"path":file, "payload":os.path.join(kind, new_version_name), "version":next_version, "payload_kind":kind})
					
					copy_fn(file, os.path.join(kind, new_version_name))
			else:
				self.log_event("payload_added", attribs={"path":file, "payload":os.path.join(kind, script_shortname), "payload_kind":kind})
				copy_fn(file, os.path.join(kind, script_shortname))

	def __exit__(self):
		self.close()

	def endthreads(self):
		self.schedule.end_thread = True

	@atexit.register
	def close():
		if Experiment.current:
			Experiment.current.close()
	def close(self):
		self.schedule.end_thread = True



		###
		self.logs["attribs"] = self.attribs
		with open("expstate.pickle", "wb") as file:
			pickle.dump(self.__getstate__(), file)

		#if self.unsaved:
		end_time = time.perf_counter()
		print(f"Experiment duration: {self.expclock.time_elapsed():.3f} seconds.")
		#self.logs["exp_duration_s"] = self.expclock.time_elapsed()
		with open(self.log_file, "w") as f:
			f.write(yaml.dump(self.logs))
		print(f"Experiment logs updated: {self.log_file}")
		Experiment.current = None
		if self.active:
			self.active = False

			if isinstance(self.schedule.thread, Thread):
				self.schedule.thread.join()

			os.chdir(self.lastwd)	
			print(f"Working directory changed to: {os.getcwd()}")
			Share.updateps1(exp="")

			
		from rich.rule import Rule
		print(Rule(title="Experiment closed", align="center", style="red"))


	def newfile(self, filename, attribs={}, abspath=True, eid=True):
		"""
		filename: relative path from the exp_dir.
		attribs: attributes to add to the event.
		abspath: whether to return the absolute path from filesystem home.
		eid: prepend eid to the path name.
		"""

		## Clean
		filename = self.__sanatize__(filename)

		## Combine
		if abspath:
			eid_ = f"{self.eid}_"
			filename = os.path.join(self.exp_dir, f"{eid_*eid}{filename}")
		else:
			filename = f"{self.eid}_{filename}"

		if self.__node_validator__(filename):
			### Log
			attribs.update({"filename": filename})
			self.log("filename_created", attribs=attribs)
			return filename
		else:
			log.critical(f"File name invalid: {filename}")
			return None

	def filetree(self):
		"""
		Print the current file tree of the experiment.
		TODO: pythonic way.
		"""
		from subprocess import run
		out = run(["tree", "-a"], capture_output=True, text=True)
		return out.stdout

	@autosave
	def dirstat(self):
		stat = {file:os.stat(file) for file in os.listdir(".")}
		self.log("files_stat", attribs=stat)

	def set_sync_flag(self):
		"""
		:depreciated
		Mark the experiment for synchronisation.
		"""
		syncid = uid()
		sync = {"sync": True, "syncid": syncid, "dt": datetime.datetime.now()}
		YamlProtocol.dump(".sync", sync)
		log.critical(f"Set experiment syncronisation with syncid: {syncid}")
		self.log("set_sync", attribs={"syncid": syncid})

	def unset_sync_flag(self):
		"""
		Umark the experiment **explicitly** for synchronisation.
		Note: In the absence of .sync file, syncronisation is not performed.
		"""
		if os.path.isfile(".sync"):
			os.remove(".sync")
		log.critical("Unset experiment syncronisation.")
		self.log("unset_sync")


	#def log(self, action, attrib={}):
	#	if action in self.logs:
	#		action = f"{action}-{time.time_ns()}"
	#	log_ = {"mtime": time.time_ns(), "dt":datetime.datetime.now()}
	#	log_.update(attrib)
	#	self.logs[action] = log_
	#	return action

	def log(self, event, attribs={}):
		self.logs["events"].append(dict(ExpEvent(kind=event, attribs=attribs)))

	def events(self):
		return list(self.logs.keys())

	def log_event(self, string, attribs={}):
		"""
		Format -> Event: datetime. ### Obsolete
		"""
		self.log(string, attribs=attribs)
		return
		if self.active:
			now = datetime.datetime.now() 
			self.logs[str(now)] = string
			self.unsaved = True
		else:
			print("Experiment is not active. Please use exp_close() function or start a new experiment.")

	### User text & metadata entry


	@is_event
	@autosave
	def note(self, string):
		self.log("user_note", attribs={"note": string})
		return Panel(string, title=f"Noted! @ {self.expclock.time_elapsed():.3f}")

	def write(self):
		"""
		Wrapper that opens the user prompt. Maybe more modalities - confusion, problem, e
		"""
		inp = Prompt.ask("[blue] User Note >>> ")
		self.note(inp)
		return inp

	@is_event
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
	def __head_validator__(self, name):
		"""
		Validate experiment directory name.
		"""
		flag = True
		matchers = ["()", ".", "\n", "\r", "\\n", "\\r"]
		matching = [partstr for partstr in name if any((matcher in name) 
					for matcher in matchers)]
		if matching:
			flag = False
		return flag


	## ----- Measurements ----------------------------
	@autosave
	def new_measurementstream(self, name, detections=[], measurements=[], monitors=[]):
		"""
		Returns a stream wrapper aroind a given measurement object.
		"""
		from .measurement import MeasurementStream

		ms = MeasurementStream(name=name)
		for detection in detections:
			ms.add_detection(detection)
		for measurement in measurements:
			ms.add_measurement(measurement)
		for monitor in monitors:
			ms.add_monitor(monitor)

		ms.auto_update_tables = True
		ms.auto_update_explogs = True
		ms.auto_update_df = True

		self.mstreams[name] = ms
		log.info(f"Added measurment stream: {name}")
		self.log("measurement_stream", attribs={"name":name, "measureid": ms.uid, 
				 "detections":ms.detections, "measurements":ms.measurements,
				 "monitors":ms.monitors})
		print(Panel(Pretty(self.mstreams[name]), 
					title=f"Measurement stream created: {name}", style="white on blue"))
		return self.mstreams[name]

	@autosave
	def new_measurement(self, **kwargs):
		from expframework.measurement import Measurement

		self.logs["results"].append(Measurement(**kwargs))
		return self.logs["results"][-1]


	### ----- Event Model -----------------------------

	
	@is_event
	@autosave
	def delay(self, name, seconds, steps=100):
		"""
		Add a experiment step dealy with a progress bar and automatic logging.
		Todo: Correct processor drift.
		"""
		interrupted = False
		start = time.time_ns()
		print(start)
		try:
			for i in track(range(steps), description=f"exp-step: blocking delay: [red]{name}[default] | [cyan]{seconds}s[default] >> "):
			    time.sleep(seconds/steps)  # Simulate work being done
		except KeyboardInterrupt:
			interrupted = True
			print(f"[red]Dealy interrupted @ {((time.time_ns()-start)*10**-9):3f}/{seconds}")
		self.log("delay", attribs={"name":name, "duration":seconds, "start_ns":start,
				 "end_ns": time.time_ns(), "interrupted": interrupted})
		print(time.time_ns())

	
	@is_event
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
		
		
		print(desc)
		interrupted = False
		start = time.time_ns()
		try:
			
			#####################
			task(*args, **kwargs)
			#####################
			
			end = time.time_ns()
			print(f"Task duration: {float(end-start)*10**-9} s")
		except KeyboardInterrupt:
			end = time.time_ns()
		self.log("tracked_task", attribs={"name":name, "duration":float(end-start)*(10**-9), "start_ns":start, 
				 "end_ns": end, "interrupted": False, "task": str(task), "args": args, "kwargs":kwargs,
				 "description": desc, "task_description": task.__doc__})
	
	@is_event
	@autosave
	def user_prompt(self, prompt, label=None):
		start = time.time_ns()

		prompt_ = prompt
		if prompt == None:
			prompt_ = "!!Any key!!"
		prompt_string = Rule(title=f"Waiting for prompt : <<<{prompt_}>>> ", style="red")
		
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

		attribs={"name": name, "prompt":prompt, "label":label}
		
		
		attribs["prompt_requested"] = datetime.datetime.now()
		
		inp = "no_inp"
		print(prompt_string)
		inp = Prompt.ask("Response >>")
		while not conditional(inp):
			print(prompt_string)
			inp = Prompt.ask("Response >>")

		
		print(Rule(title=f"prompt accepted : {prompt_}", style="green"))
		
		attribs["prompt_received"] = datetime.datetime.now()
		event = self.log("user_prompt", attribs=attribs)
		print("Time elapsed: ", f"{(self.logs['events'][-1]['machinetime']-start)/10**9:.3f}", "s")


	@is_event
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
		accepted = False
		if callableid == -1:
			print(Rule(title=f"Exp multiprompt >> Prompt not accepted : {inp}!", align="center", style="red"))
		else:
			print(Rule(title=f"Exp multiprompt >> Prompt accepted: {inp} : {callables[callableid]}", align="center", style="green"))
			accepted = True
		self.log("user_multiprompt", attrib={"prompt":inp, \
			     "choices":labels, "accepted": accepted, "prompt_requested":startdt, 
			     "prompt_received": datetime.datetime.now()})
		return inp


	@is_event
	@autosave
	def interrupted(self):
		"""
		Marks an interrupt event - Experiment flow was interrupted by the user.
		"""
		self.log("exp_interrupted")





if __name__ == "__main__":
	exp = Experiment("test")
	pprint(exp.list_all())
