import sys
from config.common import Common
import os

class Share:

	## Software level info
	scopecli_fullpath = os.path.abspath(".")



	scopeid = None
	argparse = {"noep": False}

	### User info
	user = "ghost"

	## Experiment info
	expname = None
	expdir = Common.expdir

	## 

	def updateps1(user=None, exp=None):
		
		if user:
			Share.user = user
		if exp:
			Share.expname = exp
		if exp == "":
			Share.expname = None

		def template():
			from colorama import Fore
			return f"{Fore.BLUE}user:{Share.user}{Fore.RESET} || {Fore.YELLOW}‹‹{Share.scopeid}››{Fore.RESET} {f'Experiment: {Fore.RED}{Share.expname}{Fore.RESET}'*(Share.expname != None)} >>> "
		sys.ps1 = template()

Share.updateps1()
	
