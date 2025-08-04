"""
Test script header which should mention important information like author, references, and licencing
information.

author: Yatharth Bhasin
date: 30-July-2025
licence: MIT Licence

Copyright (c) <year> <copyright holders>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


## Do common imports
import time
import os
from rich import print
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


## Describe the script. This is important and will be logged in the Experiment system.
__description__ = \
"""
Simple coin toss simulator.
This script is used for testing of the  `ScriptEngine`system. It serves as the general
recommended template for writing scripts.
"""


### It is recommended that you include a quick explainer.
print("Use create_exp() to create an experiment.")
print("Use add_coin_object() to add a coin to the scope.")
print("Use simulate_coin_toss() to change outcome.")



## Define specific functions
def create_exp():
	"""
	Specialised function to construct a test experiment.
	"""
	global exp
	exp = Experiment.Construct(["test", "experiment" "scripted_run", "coin_toss"], 
								user=True, eid=True, date=True, time=True, scopeid=True)


def add_coin_object(name="coin", attribs={"win":"H", "all_states": ["H", "T"]}):
	"""
	This function by default adds a physical object representation on the scope.
	The `PhysicalObject` represents a coin.
	"""

	## One time imports should be contained in functions to avoid population of the namespace.
	from hive.physical import PhysicalObject
	global scope

	scope = ScopeAssembly.current
	print("[red]Current scope structure")
	print(scope.draw_tree())


	print("[green]Now we add the coin")
	scope.add_device("coin", PhysicalObject("coin", **attribs))
	print(scope.draw_tree())


def simulate_coin_toss():
	"""
	Do a toss and set outcome of the physical object.
	"""
	global scope
	import random
	flip = random.randint(0, 1)
	scope.coin["win"] = (flip==0)*"H" + (flip==1)*"T"
	print(scope.coin)

## End of initalization message
print("Script initalization finished.")

if __name__ == "__main__":
	## This part will always run

	## Simulate 5 coin-tosses in 5 seconds
	print("We will create an experiment and simulate 5 tosses. One every second.")
	create_exp()
	add_coin_object()

	from datetime import timedelta
	exp.schedule.every(1).second.do(simulate_coin_toss).until(timedelta(seconds=5))


