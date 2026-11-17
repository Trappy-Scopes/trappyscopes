"""
"Repository utility >" submenu: status for every repository declared in
config.git_dependencies (split-out dependents like pico_firmware or a
protocols directory) plus trappyscopes' own codebase -- previously the
one repo this tool had no update option for at all -- then an animated
menu (same _show_menu() mechanism as MicroPython/Configuration) to pick
ONE to pull. Pulling re-shows an updated table before the menu appears
again, rather than syncing everything behind at once with no way to see
what changed afterward.

Uses GitPython rather than shelling out to `git` and parsing text --
already a project dependency, and already the established pattern here
(core/bookkeeping/session.py uses it to record the commit id per session).
"""

import os

import git
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share

_SELF_LABEL = "trappyscopes (this codebase)"


def _entry(value):
	"""AI Generated -- one git_dependencies entry, in either shape.

	    label: /path/to/repo                       -- no branch pinned
	    label: {path: /path/to/repo, branch: dev}  -- pinned

	The bare-string form is what every existing trappyconfig.yaml uses, so it
	has to keep working; the mapping form is additive.
	"""
	if isinstance(value, dict):
		return value.get("path"), value.get("branch")
	return value, None


def declared_branches():
	"""AI Generated -- {label: branch} for every repo that pins one.

	trappyscopes' own checkout is pinned by `config.branch`; the others by a
	`branch:` key on their git_dependencies entry. A repo that pins nothing is
	absent from this map and is left on whatever is checked out.
	"""
	TrappyConfig()
	branches = {}
	try:
		own = TrappyConfig.current.leaf("config", "branch")
	except Exception:
		own = None
	if own:
		branches[_SELF_LABEL] = str(own)

	git_dependencies = TrappyConfig.current.expanded("config", "git_dependencies")
	for value in git_dependencies.values():
		path, branch = _entry(value)
		if branch:
			branches[path] = str(branch)
	return branches


def _status(path):
	"""Returns (dirty, ahead, behind, error) for the repo at `path`."""
	try:
		repo = git.Repo(path)
	except git.InvalidGitRepositoryError:
		return None, None, None, "not a git repository"
	except git.NoSuchPathError:
		return None, None, None, "path does not exist"

	dirty = repo.is_dirty()
	branch = None
	try:
		branch = repo.active_branch.name
		repo.remotes.origin.fetch()
		ahead = sum(1 for _ in repo.iter_commits(f"origin/{branch}..HEAD"))
		behind = sum(1 for _ in repo.iter_commits(f"HEAD..origin/{branch}"))
	except Exception as e:
		return dirty, None, None, branch, f"fetch failed: {e}"

	return dirty, ahead, behind, branch, None


def all_repos():
	"""{label: path} -- config.git_dependencies plus trappyscopes' own
	repo (Share.scopecli_fullpath, the same path _version_line() in
	tui.py already reads its commit from).

	AI Generated -- git_dependencies is an "expand" field (see README's "Expanded config
	fields" table): a lab-wide manifest appended via config.config_files
	should be able to add shared repos without disturbing whatever this
	device's own primary trappyconfig.yaml already declares, so this
	reads it via TrappyConfig.expanded(), not a plain dict .get() chain
	-- the latter would let the higher-priority source silently replace
	the other's entries wholesale instead of union them."""
	TrappyConfig()  # ensures TrappyConfig.current is set, same as everywhere else
	git_dependencies = TrappyConfig.current.expanded("config", "git_dependencies")
	repos = {}
	for value in git_dependencies.values():
		path, _ = _entry(value)
		if path:
			repos[path] = path
	repos[_SELF_LABEL] = Share.scopecli_fullpath
	return repos


def status_table(repos):
	"""(Table, {label: (dirty, ahead, behind, error)}) for `repos` (as
	returned by all_repos()) -- built together so the menu that follows
	doesn't have to re-fetch what the table just showed."""
	branches = declared_branches()

	table = Table(title="Repository status")
	table.add_column("Repository")
	table.add_column("Branch")
	table.add_column("Dirty")
	table.add_column("Ahead")
	table.add_column("Behind")
	table.add_column("Note", style="red")

	statuses = {}
	for label, path in repos.items():
		path = os.path.expanduser(path)
		dirty, ahead, behind, branch, error = _status(path)
		statuses[label] = (dirty, ahead, behind, branch, error)

		## "dev" when it matches or nothing is pinned; "main -> dev" in red
		## when the checkout is not on the branch the config asks for.
		want = branches.get(label)
		if want and branch and want != branch:
			shown = f"[red]{branch} -> {want}[/red]"
		else:
			shown = branch or "-"

		table.add_row(
			label,
			shown,
			"-" if dirty is None else ("yes" if dirty else "no"),
			"-" if ahead is None else str(ahead),
			"-" if behind is None else str(behind),
			error or "",
		)
	return table, statuses


def pull(label, path, console):
	"""Pull one repo by label/path (as returned by all_repos()). Used by
	the launcher's animated picker (tui.py's _show_repo_menu()); public
	so it isn't a same-module-only private helper."""
	try:
		git.Repo(os.path.expanduser(path)).remotes.origin.pull()
		console.print(f"[green]pulled[/green] {label}")
		if label == _SELF_LABEL:
			console.print("[yellow]trappyscopes itself was updated -- restart the "
						   "launcher (exit and run `trappyscope` again) to actually "
						   "run the new code. This running session is still "
						   "executing what was already loaded in memory; only the "
						   "version line will reflect the pull immediately.[/yellow]")
	except Exception as e:
		console.print(f"[red]Pull failed: {e}[/red]")


def checkout(label, path, branch, console):
	"""AI Generated -- put one repo on the branch its config asks for.

	Refuses on a dirty checkout rather than stashing or forcing. A scope with
	uncommitted work has it for a reason -- usually an edit made at the bench
	-- and silently moving the branch out from under it is worse than leaving
	the device on the wrong branch and saying so.

	Creates a local tracking branch when one does not exist yet, so a device
	that has only ever had `main` can be moved to `dev` without anyone
	running git by hand on it.
	"""
	path = os.path.expanduser(path)
	try:
		repo = git.Repo(path)
	except Exception as e:
		console.print(f"[red]{label}: not a git repository ({e})[/red]")
		return False

	if repo.is_dirty():
		console.print(f"[red]{label}: uncommitted changes -- not switching to "
					  f"'{branch}'. Commit or stash them first.[/red]")
		return False

	try:
		repo.remotes.origin.fetch(prune=True)
		if branch in (h.name for h in repo.heads):
			repo.git.checkout(branch)
		elif f"origin/{branch}" in (r.name for r in repo.remotes.origin.refs):
			repo.git.checkout("-b", branch, f"origin/{branch}")
			console.print(f"[dim]{label}: created local '{branch}' tracking "
						  f"origin/{branch}[/dim]")
		else:
			console.print(f"[red]{label}: no branch '{branch}' locally or on "
						  f"origin.[/red]")
			return False
	except Exception as e:
		console.print(f"[red]{label}: checkout of '{branch}' failed: {e}[/red]")
		return False

	console.print(f"[green]{label}[/green] is now on [bold]{branch}[/bold]")
	if label == _SELF_LABEL:
		console.print("[yellow]trappyscopes itself changed branch -- restart the "
					  "launcher (exit and run `trappyscope` again). This session "
					  "is still running the code it loaded at start.[/yellow]")
	return True


def check_and_sync(console=None):
	"""Show status for every declared repo (all_repos()), then -- if
	confirmed -- pull whichever are behind their remote. Non-interactive
	-menu equivalent of tui.py's _show_repo_menu() picker, for the "launch
	normally" boot sequence (which has no menu to pick a single repo from)."""
	console = console or Console()
	repos = all_repos()
	table, statuses = status_table(repos)
	console.print(table)

	## Branch first: pulling a repo that is on the wrong branch pulls the
	## wrong branch, so offer the switch before the pull and re-read status
	## afterwards.
	branches = declared_branches()
	wrong = [(label, branches[label]) for label, (_, _, _, branch, error)
			 in statuses.items()
			 if error is None and label in branches and branch != branches[label]]
	if wrong:
		listed = ", ".join(f"{label} -> {want}" for label, want in wrong)
		if Confirm.ask(f"Switch {len(wrong)} repo(s) to the branch the config "
					   f"asks for ({listed})?", default=True):
			for label, want in wrong:
				checkout(label, repos[label], want, console)
			table, statuses = status_table(repos)
			console.print(table)

	pullable = [label for label, (dirty, ahead, behind, branch, error)
				in statuses.items() if error is None and behind]
	if not pullable:
		return
	if not Confirm.ask(f"Pull {len(pullable)} repo(s) that are behind?", default=True):
		return

	for label in pullable:
		pull(label, repos[label], console)


if __name__ == "__main__":
	_console = Console()
	_table, _ = status_table(all_repos())
	_console.print(_table)
