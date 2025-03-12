import sys
#from config.common import Common
import os
from datetime import date as date_
import time


class Share:


	## Software level info
	scopecli_fullpath = os.path.abspath(".")


	mid = None
	scopeid = None
	argparse = {"noep": False}

	### User info
	user = "ghost"

	## Experiment info
	expname = None
	expdir = os.path.join(os.path.expanduser("~"), "experiments")
	logdir = os.path.join(os.path.expanduser("~"), "experiments")



	def updateps1(user=None, exp=None):
		
		if user:
			Share.user = user
		if exp:
			Share.expname = exp
		if exp == "":
			Share.expname = None

		def template():
			from colorama import Fore
			return f"{Fore.BLUE}user:{Share.user}{Fore.RESET} || {Fore.YELLOW}‹‹{Share.scopeid}››{Fore.RESET} {f'Experiment: {Fore.RED}{Share.expname}{Fore.RESET}'*(Share.expname != None)} \n>>> "
		sys.ps1 = template()


	def get_date_str():
		date = str(date_.today()).replace("-", "_")
		return date
	def get_time_str():
		t = time.localtime(time.time())
		time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
		return time_str



Share.updateps1()


	
