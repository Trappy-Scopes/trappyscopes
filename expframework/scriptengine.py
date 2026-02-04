from rich import print
from rich.rule import Rule
from rich.panel import Panel
import os
from importlib import import_module
from collections.abc import Iterable



from .experiment import Experiment


class ScriptEngine:
	"""
	Scripts execution framework.

	TODO: Importing module fails when an experiment is already loaded. Use `raise_exceptions=False` in that case.

	Payload copying - scipts are copied to the experiemnt/scripts folder.
	Copying is performed:
	1. When experiments are created - all the scripts in the past
	2. With an open experiment: when the script passes the commitment phase, i.e.
	   after its successfully imported and is about to be executed.
	"""
	execlist = []
	payload = []   ## Of what is copied to the Experiment payload
	modules = []
	
	def run(globals_, scripts=None, raise_exceptions=False):
		"""Run a list of scripts."""
		
		if isinstance(scripts, str): ## If a single path is given
			scripts = [scripts]

		if scripts == None:
			scripts = ScriptEngine.execlist
		
		for script in scripts:
			if not os.path.exists(script):
				print(Panel(f"Script not found: {script}", style="red"))
				if raise_exceptions:
					raise FileNotFoundError
			elif script != None:
				
				## Import script as a module
				try:
					import_path = script.lstrip(os.sep).replace(".py", "").replace(os.sep, ".")
					script_mod = import_module(import_path)
					ScriptEngine.modules.append(script_mod)
				except Exception as e:
					print(f"Script could not be imported as a module: {script}")
					if raise_exceptions:
						raise e
					else:
						ScriptEngine.modules.append(None)

				## Now execute the script
				if True:
					print('\n', Rule(title=f"Running script: {script}", align="center", style="yellow"))
					description = "No script description."
					if ScriptEngine.modules[-1] != None:
						if "__description__" in dir(ScriptEngine.modules[-1]):
							description = ScriptEngine.modules[-1].__description__
						print(Panel(description, title="description"))
					
					## Commitment to execution is performed
					ScriptEngine.payload.append(os.path.abspath(script))
					if Experiment.current:
						Experiment.current.copy_payload([ScriptEngine.payload[-1]])
					
					## Run the script
					with open(script) as f:	
						if Experiment.current:
							Experiment.current.log_event("script_run", 
								attribs={"path": script, "description":description})
						try:
							exec(f.read(), globals_)
						except KeyboardInterrupt:
							print('\n', Rule(title="Script interrupted!", align="center", style="red"))
							if Experiment.current:
								Experiment.current.log_event("script_interrupted", 
									attribs={"path": script})

	def find(globals_):
		""" Find and run scripts."""
		print("\n\n")
		print("[bold blue]Find scripts >>> [default]")
		print("Press Ctrl+Z to exit or enter to ignore.")
		from prompt_toolkit import prompt
		from prompt_toolkit.completion import WordCompleter
		from core.permaconfig.config import TrappyConfig


		## Load scriptpaths
		all_script_paths = TrappyConfig.current["Experiment"]["scripts_dirs"].get()
		all_script_paths = [os.path.expanduser(path) for path in all_script_paths]
		print("Looking into:", all_script_paths)
		#scriptcompleter = PathCompleter(only_directories=False, 
		#							    get_paths=lambda: all_script_paths, 
		#							    file_filter=lambda file: file.endswith(".py") or os.path.isdir(file), 
		#							    expanduser=True)

		paths = []
		paths = []
		for root in all_script_paths:
			for dirpath, dirnames, filenames in os.walk(root):
			    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
			    paths.append(dirpath)
			    paths += [os.path.join(dirpath, f) for f in filenames]
		paths = [path for path in paths if path.endswith(".py")]



		scriptcompleter = WordCompleter(paths, sentence=True)
		script_name = prompt('Enter script path [ press tab to expand ] -> ', completer=scriptcompleter)
		ScriptEngine.run(globals_, scripts=script_name)
