import os
from rich import print

def capture(action, name, *args, **kwargs):
	"""
	Default capture 
	"""
	if not cam.is_open():
		cam.open()
		sleep(1)
	print(f"acq: {name}")
	
	if not action:
		action = "video"
	
	# File  uniqueness check
	if unique_check:
		if exp.active:
			if not exp.unique(name):
				print(f"{Fore.RED}File already exists - ignoring the call.{Fore.RESET}")
				return
	
	# Capture call -------------------------------
	cam.capture(action, name,  *args, **kwargs) #|
	#### -----------------------------------------

	#cam.close()
	
	if exp or exp.active():
		exp.log_event(name)

def preview(tsec):
	if cam:
		if cam.is_open():
			cam.preview(tsec=30)


def close_exp():
	"""
	Close experiment and reset the current directory to the original.
	"""
	exp.close()
	if cam:
		if cam.is_open():
			cam.close()
	print("--- Exiting experiment --\n")

# Overloaded Exit function





def findexp():
	"""
	Find and load an experiment from the microscope. Only confirms once.
	"""
	global exp
	print("\n\n")
	print("[bold blue]Find experiment >>> [default]")
	print("Press Ctrl+Z to exit or enter to ignore.")
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter
	from experiment import Experiment

	expcompleter = WordCompleter([os.path.basename(exp_) for exp_ in Experiment.list_all()])
	exp_name = prompt('Input the session/experiment name -> ', completer=expcompleter)
	#autocompleter.directory("/Users/byatharth/experiments")
	#exp_name = input("Input the session/experiment name -> ")
	exp_name.strip()


	exp = None
	if exp_name:
		exp = Experiment(exp_name)


def delexp():
	"""
	Delete an experiment from the microscope. Only confirms once.
	"""
	global exp
	print("\n\n")
	print("[bold red]Delete experiment >>> [default]")
	print("Press Ctrl+Z to exit or enter to ignore.")
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter
	from experiment import Experiment

	expcompleter = WordCompleter([os.path.basename(exp_) for exp_ in Experiment.list_all()])
	exp_name = prompt('Input the session/experiment name -> ', completer=expcompleter)
	#autocompleter.directory("/Users/byatharth/experiments")
	#exp_name = input("Input the session/experiment name -> ")
	exp_name.strip()


	exp = None
	if exp_name:
		exp = Experiment(exp_name)
		path = exp.exp_dir
		exp.close()
		from rich.prompt import Confirm
		confirmdelete = Confirm.ask(f"Delete for sure? : {exp_name}")
		if confirmdelete:
			import shutil
			shutil.rmtree(path)


def explorefn(fn):
	"""
	Inspect and print a function/callable.
	"""
	from rich import inspect
	inspect(fn, methods=True, all=True)


