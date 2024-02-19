import readline
import os
from experiment import Experiment
#import actions


## Other utility functions
targets = ["run_script", "load_exp", "Experiment"] ## First targets


## Actions
#target.append(dir(actions))


## All experiments
## Append in the completer itself


## All scripts
s_ = os.listdir("scripts")
s_abs = [os.path.join("scripts", s) for s in s_]
targets.append("script/")
targets.append(s_)
targets.append(s_abs)


def completer(state):
	t_ = target + Experiment.list_all_names()

	options = [i for i in t_ if i.startswith(state)]
	if state < len(options): ## Completion target should be smaller than the possible options
		return options[state]
	#else:
	#	return None
	#return options

def directory(directory, abs=False):
	all_nodes = os.listdir(directory)
	commands = all_nodes
	readline.parse_and_bind("tab: complete")
	readline.set_completer(completer)
	commands = []

print("Setting autocompleter")
readline.set_completer_delims(' \t\n;')
#readline.parse_and_bind("tab: complete")
#readline.set_completer(completer)

import readline, glob
def complete(text, state):
#   return (glob.glob(os.path.text+'*')+[None])[state]
	return Experiment.list_all_names()[state]
readline.parse_and_bind("tab: complete")
readline.set_completer(complete)