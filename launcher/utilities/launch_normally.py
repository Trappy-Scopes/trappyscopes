"""
"Launch normally": what happens when you run `trappyscope` without
--launcher, and also the first, default menu item when you do. Runs the
whole pre-flight sequence, then hands off to the real scope CLI.

Sequence: environment (uv/conda/PEP668/hardware-profile sync) -> check
config -> sync config (if configured) -> re-check (a file rewritten by the
sync has not itself been validated) -> repo status/sync -> boot. Whatever
flags the original `trappyscope` invocation carried are already sitting in
Share.argparse by the time boot() runs -- core.argparser parses the whole
of sys.argv in one pass before the launcher/fast-track branch is even
chosen, so there's nothing extra to forward here.

config.launch turns the install, config sync and repo sync steps on or off
(all off by default); the launcher menu offers each of them on its own either
way.

Environment activation was the one open piece of this sequence (§7.3 step
0, since the very first session on this codebase) -- now implemented, via
core.installer.environment.
"""

from rich.console import Console

from . import check_config, sync_config, repo_sync, environment, boot as boot_


LAUNCH_STEPS = ("install", "config_sync", "repo_sync")


def launch_steps():
	"""{step: on/off} from config.launch -- which pre-flight steps Launch
	normally runs. Missing keys, a missing block and a missing config file
	all mean off, like the template. Read from the file directly: the
	install step runs before the config check, possibly before a config
	exists."""
	import os
	import yaml
	from core.permaconfig.config import TrappyConfig
	block = {}
	for path in TrappyConfig.default_paths:
		if os.path.exists(path):
			try:
				with open(path) as f:
					block = ((yaml.safe_load(f) or {}).get("config") or {}).get("launch") or {}
			except Exception:
				block = {}
			break
	return {step: bool(block.get(step, False)) for step in LAUNCH_STEPS}


def run(console=None):
	console = console or Console()
	steps = launch_steps()
	skipped = [s for s, on in steps.items() if not on]
	if skipped:
		console.print(f"[dim]config.launch: skipping {', '.join(skipped)} "
					  f"(turn on in config.launch, or run from the launcher menu).[/dim]")

	## Hardware-profile install (uv, apt, conda-forge). Asks before installing.
	if steps["install"]:
		environment.ensure()

	if not check_config.check(console=console):
		return

	if steps["config_sync"] and sync_config.sync_trappyverse(console=console):
		if not check_config.check(console=console):
			return

	if steps["repo_sync"]:
		repo_sync.check_and_sync(console=console)

	## AI Generated -- moved here from expenv/recipes/freestyle.py.
	## After repo sync, not before -- so the wallpaper's version line
	## reflects whatever code a pull just brought in, not the commit that
	## was checked out when the launcher started.
	from core.permaconfig.config import TrappyConfig
	config = TrappyConfig().get()
	## .get(): TrappyConfig().get() does not fill keys a config file leaves out
	## from default_config.yaml, so a missing key must fall back here (false).
	if config["config"].get("set_wallpaper", False):
		## AI Generated -- wallpaper generation is a cosmetic nice-to-have,
		## not something that should ever take the whole launcher down
		## with it (confirmed: it did, via a stale asset path after the
		## utilities/ -> core/utilities/ move). Report and move on.
		try:
			from core.utilities.wallpaper import generate_wallpaper, set_wallpaper
			wallpaper_path = generate_wallpaper(config)
			set_wallpaper(wallpaper_path)
		except Exception as e:
			console.print(f"[yellow]Wallpaper generation failed, skipping: {e}[/yellow]")

	boot_.boot()


if __name__ == "__main__":
	run()
