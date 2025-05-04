from .experiment import Experiment

import os
from colorama import Fore

## Depreciated
class Calibration(Experiment):
	...
	#def __init__(self, name, append_eid=False, **kwargs):
	#	super().__init__(name, append_eid=append_eid)
	#	self.exp_dir = os.path.join(config.common.CALIB_DIR, self.name)

class Test(Experiment):

	def __init__(self, name, append_eid=False, **kwargs):
		self.checks = []
		super().__init__(name, append_eid=append_eid, kwargs=kwargs)

	def testfn(self, callable_, *args, **kwargs):
		"""
		Only fails if exceptions are raised. TODO
		"""
		self.log("testfn", attribs={"check":str(callable_)})
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
			print(Rule(title=f"{callable_} : OK", style="green"))
			self.checks.append(1) ## Inverted
			return True

		except Exception as e:
			print(Rule(title=f"{callable_} : NOK", style="red"))
			print(Fore.RED)
			print(e)
			print(Fore.RESET)
			self.checks.append(0) ## Inverted
			return False

	def conclude(self):
		if sum(self.checks) == len(self.checks):
			print(f"{Fore.GREEN}All checks passed!{Fore.RESET}")
		print(f"Checks: {Fore.BLUE}{sum(self.checks)} / {len(self.checks)} passed.{Fore.RESET}")
		self.logs["checks_passed"] = [sum(self.checks), len(self.checks)]