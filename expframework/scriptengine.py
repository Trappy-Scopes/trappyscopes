from colorama import Fore, Style
from rich import print
from rich.rule import Rule
from rich.panel import Panel
import os

from .experiment import Experiment

class ScriptEngine:

	execlist = []
	payload = []
	def run_all(globals_, scripts=None):
		if scripts == None:
			scripts = ScriptEngine.execlist
		for script in scripts:
			if script != None: ## TODo: need better verification
				print(Rule(title=f"Executing script: {script}", align="center", style="yellow"))
				print(Panel("Press Ctrl+C to interrupt the experiment.", title="Instructions"))
				#print("scopeid" in globals(), globals())
				with open(script) as f:
					try:
						ScriptEngine.payload.append(os.path.abspath(script))
						exec(f.read(), globals_)
					except KeyboardInterrupt:
						print('\n', Rule(title="Experiment interrupted!", align="center", style="red"))
						Experiment.current.interrupted()

	def now(globals_, script):
		ScriptEngine.execlist = [script]

		ScriptEngine.run_all(globals_)
