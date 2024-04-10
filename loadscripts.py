from colorama import Fore, Style
from rich import print
from rich.rule import Rule

class ScriptEngine:

	execlist = []

	def run_all(globals_, scripts=None):
		if scripts == None:
			scripts = ScriptEngine.execlist
		for script in scripts:
			if script != None: ## TODo: need better verification
				print(Rule(title=f"Executing script: {script}", align="center", style="yellow"))
				#print("scopeid" in globals(), globals())
				with open(script) as f:
					exec(f.read(), globals_)

