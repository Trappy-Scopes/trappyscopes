"""
"Check virtual environment" menu item: does the environment declared in
config.venv (command + name) actually exist, and if not, offer to create
it. Nothing in this codebase checked this before -- core.installer.
environment's venv handling is a generic PEP 668 fallback, unrelated to
config.venv specifically.

Every config.venv example in this codebase (default_config.yaml's
template and the one real trappyconfig.yaml checked this session) uses
the same shape: `command: source .../bin/activate`, `name: <env>` --
classic conda activation. A plain venv is declared the same way
(`command: source ~/trappyvenv/bin/activate`, `name: trappyvenv`) and is
checked by its directory; conda envs against conda/mamba. If config.venv is
not declared but the launcher runs inside a venv, check() offers to record
that venv in the config file.
"""

import os
import re
import shutil
import subprocess
import sys

from rich.console import Console
from rich.prompt import Confirm

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share


def _min_python_version():
	"""Lower bound of requires-python from pyproject.toml (e.g. "3.12"
	from ">=3.12,<4.0") -- read with a plain regex, not a TOML parser:
	this can run from whatever interpreter happens to be on PATH before
	a proper environment necessarily exists, and tomllib itself needs
	Python 3.11+, not guaranteed here."""
	path = os.path.join(Share.scopecli_fullpath, "pyproject.toml")
	try:
		with open(path) as f:
			text = f.read()
		match = re.search(r'requires-python\s*=\s*"[>=~]*\s*(\d+\.\d+)', text)
		if match:
			return match.group(1)
	except OSError:
		pass
	return "3.11"


def _config_or_none():
	"""The scope configuration, or None on a fresh machine that has no
	trappyconfig.yaml yet (TrappyConfig raises TS_ConfigNotFound)."""
	from core.exceptions import TS_ConfigNotFound
	try:
		return TrappyConfig().get()
	except TS_ConfigNotFound:
		return None


def _running_venv():
	"""The plain venv this interpreter runs in, or None (system Python or conda)."""
	if os.environ.get("CONDA_DEFAULT_ENV") or sys.prefix == sys.base_prefix:
		return None
	return sys.prefix


def _plain_venv_dir(command):
	"""`source <dir>/bin/activate` -> <dir>, expanded; None for anything else."""
	m = re.match(r"\s*(?:source|\.)\s+(\S+)/bin/activate\s*$", command or "")
	return os.path.expanduser(m.group(1)) if m else None


def _record_venv(prefix, console):
	"""Write the running venv into the config file as config.venv, editing the
	existing `venv:` block in place so the file's comments survive."""
	path = TrappyConfig.current.loaded_from
	home = os.path.expanduser("~")
	shown = "~" + prefix[len(home):] if prefix.startswith(home + os.sep) else prefix
	with open(path) as f:
		lines = f.readlines()
	idx = next((i for i, line in enumerate(lines) if re.match(r"^(\s+)venv:\s*(#.*)?$", line)), None)
	if idx is None:
		console.print(f"[yellow]No `venv:` block found in {path}. Add this under `config:`:[/yellow]\n"
					  f"  venv:\n      active: true\n      command: source {shown}/bin/activate\n"
					  f"      name: {os.path.basename(prefix)}")
		return
	indent = len(lines[idx]) - len(lines[idx].lstrip())
	end = idx + 1
	while end < len(lines) and (not lines[end].strip()
			or len(lines[end]) - len(lines[end].lstrip()) > indent):
		end += 1
	while end > idx + 1 and not lines[end - 1].strip():
		end -= 1
	child = " " * (indent + 4)
	lines[idx + 1:end] = [f"{child}active: true\n",
						  f"{child}command: source {shown}/bin/activate\n",
						  f"{child}name: {os.path.basename(prefix)}\n"]
	with open(path, "w") as f:
		f.writelines(lines)
	console.print(f"[green]Recorded config.venv: source {shown}/bin/activate[/green] ({path})")


def status():  # AI Generated -- extracted from check() below for the Install/setup status panel
	"""(ready: bool, detail: str) -- read-only, no prompts, safe to call
	on every "Install / setup" menu redraw. Shared by check() (which adds
	the interactive flow on top) and the status panel. Must not raise:
	the panel calls it before a configuration file exists."""
	config = _config_or_none()
	if config is None:
		return False, "no configuration file yet -- create it first"
	venv = TrappyConfig.optional_block(config, "config", "venv")
	if venv is None:
		running = _running_venv()
		if running:
			return False, f"running in {running}, but config.venv does not record it"
		return True, "not declared or inactive -- nothing required"

	name = venv.get("name")
	command = venv.get("command", "")
	venv_dir = _plain_venv_dir(command)
	if venv_dir:
		if os.path.isfile(os.path.join(venv_dir, "bin", "python")):
			return True, f"{venv_dir} exists"
		return False, f"{venv_dir} does not exist yet"
	if not name or "conda" not in command.lower():
		return False, "declared, but neither a venv nor a conda command -- can't check automatically"

	exe = shutil.which("mamba") or shutil.which("conda")
	if not exe:
		return False, "no conda/mamba on PATH -- can't check automatically"

	result = subprocess.run([exe, "env", "list"], capture_output=True, text=True)
	existing = {line.split()[0] for line in result.stdout.splitlines()
				if line and not line.startswith("#")}
	if name in existing:
		return True, f"{name} exists"
	return False, f"{name} does not exist yet"


def check(console=None):
	console = console or Console()
	config = _config_or_none()
	if config is None:
		console.print("[yellow]No trappyconfig.yaml yet -- run \"Create configuration file\" first.[/yellow]")
		return
	venv = TrappyConfig.optional_block(config, "config", "venv")
	if venv is None:
		running = _running_venv()
		if running and Confirm.ask(f"Record the running venv ({running}) in the configuration?",
									default=True):
			_record_venv(running, console)
			return
		console.print("[dim]config.venv is not declared or inactive -- nothing to check.[/dim]")
		return

	name = venv.get("name")
	command = venv.get("command", "")
	console.print(f"Declared venv: [bold]{name}[/bold]  (activated via: {command})")

	ready, detail = status()
	console.print(f"[{'green' if ready else 'yellow'}]{detail}.[/{'green' if ready else 'yellow'}]")
	if ready:
		return

	venv_dir = _plain_venv_dir(command)
	if venv_dir:
		if Confirm.ask(f"Create venv {venv_dir} now (with system site packages)?", default=True):
			command_ = [sys.executable, "-m", "venv", "--system-site-packages", venv_dir]
			console.print(f"$ {' '.join(command_)}")
			ok = subprocess.run(command_).returncode == 0
			console.print(f"[green]Created {venv_dir}.[/green]" if ok else f"[red]Failed to create {venv_dir}.[/red]")
		return

	## Only offer to create it when the reason isn't "can't check
	## automatically" (an unrecognised command, or no conda/mamba on PATH) --
	## in those cases there's nothing this function can act on.
	exe = shutil.which("mamba") or shutil.which("conda")
	if not name or "conda" not in command.lower() or not exe:
		return

	if not Confirm.ask(f"Create conda environment '{name}' now?", default=True):
		return

	version = _min_python_version()
	command_ = [exe, "create", "-n", name, "-y", f"python={version}"]
	console.print(f"$ {' '.join(command_)}")
	result = subprocess.run(command_)
	if result.returncode == 0:
		console.print(f"[green]Created {name}.[/green]")
	else:
		console.print(f"[red]Failed to create {name}.[/red]")


if __name__ == "__main__":
	check()
