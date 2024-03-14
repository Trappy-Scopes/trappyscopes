import sys
from colorama import Fore

class Share:
	scopeid = None
	argparse = {"noep": False}

	user = "ghost"
	expname = None

	def updateps1(user=None, exp=None):
		
		if user:
			Share.user = user
		if exp:
			Share.expname = exp
		if exp == "":
			Share.expname = None

		def template():
			return f"{Fore.BLUE}user:{Share.user}{Fore.RESET} || {Fore.YELLOW}‹‹{Share.scopeid}››{Fore.RESET} {f'Experiment: {Fore.RED}{Share.expname}{Fore.RESET}'*(Share.expname != None)} >>> "
		sys.ps1 = template()

Share.updateps1()
	
