from colorama import Fore
import datetime
import sys
from rich.panel import Panel
from rich import print

from sharing import Share

class User:
	
	info = {"user": "ghost", "login_time":datetime.datetime.now()}
	
	user_list = ["YB", "CC", "PS", "ghost"]

	def login(user):
		loginpanel = ""
		if user in User.user_list:
			loginpanel += "Welcome back!\n"
		else:
			loginpanel += "[red]Intruder detected![default]\n"
		loginpanel += f"[blue]trappy-scope says: [default]Hello! [red]{user}[default].\n"
		now = datetime.datetime.now()
		loginpanel +=  f"Login dt: {str(now)}"
		scope_user = user
		User.info["user"] = user
		User.info["login_time"] = now

		print(Panel(loginpanel, title="User.login"))
		User.updateps1()
	
	def logout():
		if User.info["user"] != "ghost":
			print("Tchau!")
			User.info["user"] = "ghost"
			User.updateps1()

	def updateps1():
		Share.updateps1(user=User.info["user"])
		
