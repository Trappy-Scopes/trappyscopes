from colorama import Fore
import datetime
import sys
from rich.panel import Panel
from rich import print

from core.permaconfig.config import TrappyConfig  # AI Generated
from core.permaconfig.sharing import Share

class User:

	info = {"user": "ghost", "login_time":datetime.datetime.now()}

	_GHOST_RECORD = {"full_name": "Unknown", "email": None, "designation": None}

	def registry():
		"""AI Generated -- {code: {full_name, email, designation}}, from the
		config's `Users:` block (an "expand" field -- see README's
		"Expanded config fields" table -- so a lab manifest can add users
		without disturbing whatever a device's own config already
		declares). Always includes "ghost", the unauthenticated default,
		even if the config doesn't mention it."""
		known = {}
		if TrappyConfig.current is not None:
			known = TrappyConfig.current.expanded("Users")
		return {"ghost": dict(User._GHOST_RECORD), **known}

	def login(user, force=False):
		"""AI Generated -- `force=True` deliberately bypasses the registry
		check (e.g. a visiting collaborator not yet added to `Users:`) --
		it is the one, explicit escape hatch, not the default path."""
		from .session import Session  # AI Generated -- deferred: session.py imports User at module level

		registry = User.registry()
		if user not in registry and not force:
			print(Panel(f"[red]Unrecognized user '{user}' -- not in config Users:. "
						 f"Pass force=True to log in anyway.[/red]", title="User.login"))
			return False

		record = registry.get(user, {**User._GHOST_RECORD, "full_name": user})
		now = datetime.datetime.now()
		User.info = {"user": user, **record, "login_time": now}

		loginpanel = "Welcome back!\n" if user in registry else "[yellow]Unrecognized user, logged in with force=True.[/yellow]\n"
		loginpanel += f"[blue]trappy-scope says: [default]Hello! [red]{record.get('full_name', user)}[default].\n"
		loginpanel += f"Login dt: {str(now)}"
		print(Panel(loginpanel, title="User.login"))

		Session()  # AI Generated -- fresh session per login; User.info is already updated above
		from expframework.experiment import Experiment  # AI Generated -- deferred, see login()'s note above
		if Experiment.current is not None:
			Experiment.current._log_user()
			Experiment.current._log_session()

		User.updateps1()
		return True

	def logout():
		from .session import Session  # AI Generated -- deferred, see login()

		if User.info["user"] != "ghost":
			print("Tchau!")
			User.info = {"user": "ghost", **User._GHOST_RECORD, "login_time": datetime.datetime.now()}
			Session()  # AI Generated -- fresh session on logout too; User.info is already "ghost" above
			from expframework.experiment import Experiment  # AI Generated -- deferred, see login()
			if Experiment.current is not None:
				Experiment.current._log_user()
				Experiment.current._log_session()
			User.updateps1()

	def updateps1():
		Share.updateps1(user=User.info["user"])

	def name():
		return User.info["user"]

