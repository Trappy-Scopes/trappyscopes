from colorama import Fore
import datetime
import sys

class User:
	
	info = {"user": "ghost", "login_time":datetime.datetime.now()}
	
	user_list = ["YB", "CC", "PS", "ghost"]
	exp_hook = None

	def login(user):
		if user in User.user_list:
			print("Welcome back!")
		else:
			print("Intruder detected!")
		print(f"{Fore.BLUE}trappy-scope says: {Fore.RESET}Hello! {user}.")
		now = datetime.datetime.now()
		print(f"Login dt: {str(now)}")
		scope_user = user
		User.info["user"] = user
		if User.exp_hook:
			if User.exp_hook.active:
				User.exp_hook.user = scope_user
				sys.ps1 = User.exp_hook.header()
			else:
				sys.ps1 = f"{Fore.BLUE}user:{scope_user}{Fore.RESET} || >>> "

		elif user == "" or user == None:
			sys.ps1 = ">>> "
		else:
			sys.ps1 = f"{Fore.BLUE}user:{scope_user}{Fore.RESET} || >>> "
		User.info["login_time"] = now
	def logout():
		if User.info["user"] != ghost:
			print("Tchau!")
			User.info["user"] = ghost
			User.login("ghost")