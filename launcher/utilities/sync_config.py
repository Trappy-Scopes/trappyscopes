"""
Sync the whole trappyverse/ folder with the config server. Only job: rsync
(§7.2 of docs/notes/restructuring.md -- one folder, both directions,
"update" mode so the latest copy of each file wins either way).

One thing not explicit in the original spec, added deliberately: the remote
destination is namespaced by scopeid, not one shared folder for every scope.
trappyverse/ now holds per-scope local state (relocated shelves, see
hive/physical.py) alongside configs -- syncing every scope into the same
remote folder would let one scope's device state silently overwrite
another's. Configs meant to be shared across scopes still can be, by putting
them in config.config_files and syncing those paths explicitly; this
utility's job is just the folder transfer.
"""

import os

from rich.console import Console
from rich.prompt import Confirm

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share
import core.sync as sync


def destination_for(block, config):
	"""(path inside the share, scopeid) for this scope's config folder.

	The launcher runs before the experiment environment sets Share.scopeid,
	so the scope ID comes from the config's `name`. It is appended to the
	templated destination unless the template already places it, so
	"configs" and "configs/{scopeid}" both give configs/<scopeid>.
	"""
	import re
	scopeid = Share.scopeid or config.get("name", "unknown-scope")
	raw = block.get("destination") or ""
	templated = (TrappyConfig.current or TrappyConfig()).template(raw, scopeid=scopeid)
	if re.search(r"\{\s*scopeid\b", raw):
		return templated, scopeid
	return os.path.join(templated, scopeid), scopeid


def sync_trappyverse(config=None, console=None):
	"""
	Sync ~/trappyverse/ with the config server. Returns True if both
	directions completed without error (or there was nothing configured to
	sync, which isn't a failure), False otherwise.
	"""
	console = console or Console()
	if config is None:
		config = TrappyConfig().get()

	block = TrappyConfig.optional_block(config, "config", "config_server")
	if block is None:
		console.print("[yellow]config_server is not configured or is inactive -- nothing to sync.[/yellow]")
		return True

	## config_server.destination is templated like Experiment.file_server.
	## destination (TrappyConfig.template(): {scopeid}, {date}, {time},
	## {user}). Checked before mounting, so a bad template fails cleanly.
	try:
		destination, scopeid = destination_for(block, config)
	except Exception as e:
		console.print(f"[red]config_server.destination ('{block.get('destination')}') "
					  f"is not a valid template: {e!r}. Names: {{scopeid}}, {{date}}, "
					  f"{{time}}, {{user}}.[/red]")
		return False

	mount_point = sync.mount(block["server"], block["share"],
							  block["username"], block["password"])
	remote = os.path.join(mount_point, destination).rstrip("/") + "/"
	local = os.path.join(os.path.expanduser("~"), "trappyverse") + "/"
	os.makedirs(local, exist_ok=True)

	## AI Generated -- rsync fails (exit 23) when its SOURCE doesn't exist -- expected, not
	## an error, the first time a given scope ever syncs: nothing has been
	## pushed to the server for it yet, so there's genuinely nothing to
	## pull. That also means the push right after would be *creating* a
	## new remote scope entry, not just refreshing an existing one -- an
	## explicit, confirmed action, not something to do silently just
	## because a scope's config_server happens to be turned on.
	if not os.path.isdir(remote):
		console.print(f"[yellow]No existing config found on the server for scope "
					   f"'{scopeid}' ({remote}).[/yellow]")
		if not Confirm.ask(f"Create it now?", default=True):
			console.print("[dim]Not synced.[/dim]")
			return True
		## rsync creates only the last path component; destination/ may not
		## exist on the share yet either.
		os.makedirs(remote, exist_ok=True)
		pull_ok, pulled = True, []
	else:
		pull_result = sync.sync(remote, local, mode="update", itemize=True)
		pull_ok = pull_result.returncode == 0
		pulled = sync.changed_files(pull_result)

	console.print(f"Syncing {local} <-> {remote} (latest copy wins)...")
	push_result = sync.sync(local, remote, mode="update", itemize=True)
	push_ok = push_result.returncode == 0
	pushed = sync.changed_files(push_result)

	if pulled:
		console.print(f"[cyan]Pulled from server ({len(pulled)}):[/cyan] {', '.join(pulled)}")
	if pushed:
		console.print(f"[cyan]Pushed to server ({len(pushed)}):[/cyan] {', '.join(pushed)}")
	if not pulled and not pushed and pull_ok and push_ok:
		console.print("[dim]Nothing to transfer -- both sides already match.[/dim]")

	ok = pull_ok and push_ok
	if ok:
		console.print("[green]trappyverse/ synced.[/green]")
	else:
		console.print("[red]Sync had errors.[/red]")
	return ok


if __name__ == "__main__":
	sync_trappyverse()
