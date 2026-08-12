"""
Firmware sync test -- identify a MicroPython device, then push pico_firmware to it.

Exercises SerialMPDevice.sync_files() end to end on real hardware:

    1. find the device            -- already mounted on the scope, or connect now
    2. prove it is the right one  -- board name, circuit id, uuid, filesystem
    3. dry run                    -- list every file that WOULD be written
    4. sync                       -- create directories, copy, per-file result
    5. verify                     -- compare sizes on the device against local
    6. offer a reset              -- new firmware does nothing until the board reboots

Written after finding that the old sync_files() could not copy a nested tree at
all: its mkdir was commented out, so every write below the top level failed with
ENOENT, one failure abandoned the rest of the walk, and it printed "Sync
completed" regardless. This script is the thing that would have caught that.

author: Yatharth Bhasin
date: 10-August-2026
licence: MIT Licence

Copyright (c) 2026 Yatharth Bhasin

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

## Do common imports
import os
import time
import logging as log
from rich import print
from rich.prompt import Prompt, Confirm
from rich.table import Table
from hive.assembly import ScopeAssembly

__description__ = \
"""
Identify a connected MicroPython board and sync the pico_firmware tree to it.

Confirms the board first (name, circuit id, uuid, existing filesystem), then
dry-runs the sync so you can see exactly what would be written, then copies,
then verifies every file by size against the local copy.

Nothing is written until fw_sync() is called, and fw_sync() refuses unless a
device has been chosen and confirmed with fw_device()/fw_identify().
"""

### Quick explainer
print("[bold]firmware sync test[/bold]")
print("  fw_device()      pick the board: mounted on the scope, or connect now")
print("  fw_identify()    board name, circuit, uuid, what is already on it")
print("  fw_tree()        find the local pico_firmware folder")
print("  fw_dryrun()      list what WOULD be written -- touches nothing")
print("  fw_sync()        do it, with per-file results")
print("  fw_verify()      compare device file sizes against local")
print("  fw_run()         all of the above, in order, with prompts")
print("  fw_reset()       soft-reset the board so the new firmware runs")


## ---------------------------------------------------------------- config
## Where the firmware lives locally. The first one that exists wins.
FW_CANDIDATES = (
	"pico_firmware",
	os.path.expanduser("~/code/Trappy-Scopes/pico_firmware/pico_firmware"),
	os.path.expanduser("~/code/Trappy-Scopes/pico_firmware"),
	os.path.expanduser("~/trappyscopes/pico_firmware"),
)
FW_TARGET = "pico_firmware"      ## destination folder ON the board

DEVICE = None                    ## the SerialMPDevice under test
LOCAL = None                     ## resolved local folder
CONFIRMED = False                ## fw_identify() sets this
LAST_SYNC = None


## ---------------------------------------------------------------- device
def fw_device(name=None, connect=False, search_name=None):
	"""Choose the board to sync.

	With no arguments it looks for a SerialMPDevice already mounted on the
	scope -- the usual case, since the pumps and keypad are mounted at startup.
	Pass connect=True to open a new connection instead, which is what you want
	for a bare board that no circuit has claimed.
	"""
	global DEVICE, CONFIRMED
	CONFIRMED = False
	scope = ScopeAssembly.current

	if connect:
		from hive.processorgroups.micropython import SerialMPDevice
		DEVICE = SerialMPDevice(name=name or "syncdev", connect="autoconnect",
								search_name=search_name)
		if not getattr(DEVICE, "connected", False):
			print("[red]No MicroPython board found.[/] Is it plugged in, and is "
					"another session holding the port?")
			DEVICE = None
			return None
		print("[green]Connected[/] on {}".format(DEVICE.port))
		return DEVICE

	## Anything on the tree that can actually sync: has sync_files AND a pyboard
	candidates = {}
	for dev_name, dev in getattr(scope, "devices", {}).items():
		if hasattr(dev, "sync_files") and getattr(dev, "device", None) is not None:
			candidates[dev_name] = dev

	if not candidates:
		print("[yellow]No MicroPython device mounted on the scope.[/]")
		print("  [dim]fw_device(connect=True) to open one directly.[/dim]")
		return None

	if name is None and len(candidates) == 1:
		name = list(candidates)[0]
	elif name is None:
		print("Several boards are mounted: {}".format(sorted(candidates)))
		name = Prompt.ask("  which one", choices=sorted(candidates))

	DEVICE = candidates.get(name)
	if DEVICE is None:
		print("[red]No such device: {}[/]".format(name))
		return None
	print("[green]Using[/] scope.{} on {}".format(name, getattr(DEVICE, "port", "?")))
	return DEVICE


def fw_identify(assume_yes=False):
	"""Prove the board is the one you meant, before writing anything to it.

	Reads the board's own identity and lists what is already on its filesystem.
	Sets the flag fw_sync() checks.
	"""
	global CONFIRMED
	if DEVICE is None:
		print("[red]Run fw_device() first.[/]")
		return False

	table = Table(title="board identity")
	table.add_column("field")
	table.add_column("value")

	def ask(expr, label):
		try:
			value = DEVICE(expr)
		except Exception as err:
			value = "[red]{}[/red]".format(err)
		table.add_row(label, str(value))
		return value

	name = ask("board.name", "board.name")
	circuit = ask("board.circuit_id", "board.circuit_id")
	ask("Handshake.uuid", "uuid")
	ask("os.uname().version", "micropython")

	try:
		root = DEVICE.device.fs_listdir("")
		names = sorted(entry.name if hasattr(entry, "name") else str(entry)
						for entry in root)
		table.add_row("/ contains", ", ".join(names) or "[dim]empty[/dim]")
	except Exception as err:
		table.add_row("/ contains", "[red]{}[/red]".format(err))
	print(table)

	if assume_yes:
		CONFIRMED = True
	else:
		CONFIRMED = Confirm.ask(
				"  Sync firmware to [bold]{}[/bold] (circuit {})?".format(name, circuit),
				default=False)
	if not CONFIRMED:
		print("[yellow]Not confirmed -- fw_sync() will refuse.[/]")
	return CONFIRMED


## ---------------------------------------------------------------- local tree
def fw_tree(path=None):
	"""Locate the local pico_firmware folder and describe what is in it."""
	global LOCAL
	candidates = (path,) if path else FW_CANDIDATES
	for cand in candidates:
		if cand and os.path.isdir(cand):
			LOCAL = cand
			break
	else:
		print("[red]No pico_firmware folder found.[/] Tried:")
		for cand in candidates:
			print("  [dim]{}[/dim]".format(cand))
		print("  [dim]fw_tree('/path/to/pico_firmware')[/dim]")
		return None

	files, total = 0, 0
	skipped = 0
	for root, dirs, names in os.walk(LOCAL):
		dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
		for n in names:
			if n.startswith(".") or n.endswith(".pyc"):
				skipped += 1
				continue
			files += 1
			total += os.path.getsize(os.path.join(root, n))
	print("[green]Local firmware:[/] {}".format(LOCAL))
	print("  {} files, {:.1f} kB{}".format(
			files, total / 1024.0,
			", {} junk files excluded".format(skipped) if skipped else ""))
	if total > 900 * 1024:
		print("  [yellow]That is large for a Pico filesystem -- check for stray "
				"data files.[/]")
	return LOCAL


## ---------------------------------------------------------------- sync
def fw_dryrun():
	"""List every file that would be written. Touches nothing on the board."""
	if DEVICE is None or (LOCAL is None and fw_tree() is None):
		print("[red]Run fw_device() and fw_tree() first.[/]")
		return None
	result = DEVICE.sync_files(LOCAL, FW_TARGET, dry_run=True, verbose=False)
	print("[bold]dry run[/bold] -- {} files would be written to {}/".format(
			len(result["sent"]), FW_TARGET))
	for path in result["sent"][:40]:
		print("  [dim]{}[/dim]".format(path))
	if len(result["sent"]) > 40:
		print("  [dim]... and {} more[/dim]".format(len(result["sent"]) - 40))
	return result


def fw_sync(skip_unchanged=True, force=False):
	"""Copy the tree to the board.

	Refuses unless fw_identify() confirmed the device -- writing firmware to the
	wrong board is tedious to undo and easy to do when several are plugged in.
	"""
	global LAST_SYNC
	if DEVICE is None:
		print("[red]Run fw_device() first.[/]")
		return None
	if LOCAL is None and fw_tree() is None:
		return None
	if not CONFIRMED and not force:
		print("[red]Device not confirmed.[/] Run fw_identify(), or fw_sync(force=True).")
		return None

	t0 = time.time()
	LAST_SYNC = DEVICE.sync_files(LOCAL, FW_TARGET, skip_unchanged=skip_unchanged,
									verbose=True)
	LAST_SYNC["seconds"] = round(time.time() - t0, 1)
	print("  [dim]{} s[/dim]".format(LAST_SYNC["seconds"]))
	if LAST_SYNC["failed"]:
		print("[red]{} file(s) failed -- the board's firmware is now a mixture "
				"of versions. Fix and re-run before resetting it.[/]".format(
				len(LAST_SYNC["failed"])))
	return LAST_SYNC


def fw_verify(sample=None):
	"""Compare every synced file's size on the device against the local copy.

	Size is a weak checksum, but it is what the device can answer cheaply, and
	it catches the failure that matters here: a file that never arrived, or
	arrived truncated because the link dropped mid-write.
	"""
	if DEVICE is None or LOCAL is None:
		print("[red]Run fw_device() and fw_tree() first.[/]")
		return None

	checked, missing, mismatched = [], [], []
	for root, dirs, names in os.walk(LOCAL):
		dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
		rel = os.path.relpath(root, LOCAL)
		remote_root = FW_TARGET if rel == "." else "/".join(
				[FW_TARGET] + rel.replace("\\", "/").split("/"))
		for n in names:
			if n.startswith(".") or n.endswith(".pyc"):
				continue
			remote = "{}/{}".format(remote_root, n)
			local_size = os.path.getsize(os.path.join(root, n))
			try:
				st = DEVICE.device.fs_stat(remote)
				remote_size = st[6]
			except Exception:
				missing.append(remote)
				continue
			if remote_size != local_size:
				mismatched.append((remote, local_size, remote_size))
			else:
				checked.append(remote)
			if sample and len(checked) >= sample:
				break

	table = Table(title="verification")
	for col in ("result", "count"):
		table.add_column(col)
	table.add_row("[green]match[/green]", str(len(checked)))
	table.add_row("[red]missing[/red]" if missing else "missing", str(len(missing)))
	table.add_row("[red]wrong size[/red]" if mismatched else "wrong size",
					str(len(mismatched)))
	print(table)
	for path in missing[:10]:
		print("  [red]missing[/] {}".format(path))
	for path, a, b in mismatched[:10]:
		print("  [red]size[/] {} local {} device {}".format(path, a, b))

	ok = not missing and not mismatched
	print("[bold]{}[/bold]".format(
		"Sync verified." if ok else "Sync INCOMPLETE -- do not reset the board yet."))
	return {"ok": ok, "checked": len(checked), "missing": missing,
			"mismatched": mismatched}


def fw_reset(soft=True):
	"""Reset the board so the new firmware actually runs.

	Nothing you copied takes effect until the board reboots: main.py has already
	run, and the old modules are already imported.
	"""
	if DEVICE is None:
		print("[red]Run fw_device() first.[/]")
		return None
	try:
		if soft:
			DEVICE.device.exec_raw_no_follow("import machine; machine.soft_reset()")
		else:
			DEVICE.device.exec_raw_no_follow("import machine; machine.reset()")
	except Exception as err:
		## a reset always looks like a failure from here -- the board stops
		## answering mid-command, which is the point
		log.debug("reset returned: %s", err)
	print("[green]Reset sent.[/] The link is now stale -- reconnect the device "
			"(or re-run fw_device(connect=True)) before talking to it again.")
	return True


## ---------------------------------------------------------------- all of it
def fw_run(assume_yes=False, connect=False, name=None, search_name=None,
			skip_unchanged=True, reset=False):
	"""Whole procedure: device, identity, tree, dry run, sync, verify.

	    fw_run()                       mounted board, prompts before writing
	    fw_run(connect=True)           open a fresh connection first
	    fw_run(assume_yes=True)        no prompts, for a board you know
	"""
	if fw_device(name=name, connect=connect, search_name=search_name) is None:
		return None
	if not fw_identify(assume_yes=assume_yes):
		return None
	if fw_tree() is None:
		return None

	fw_dryrun()
	if not assume_yes and not Confirm.ask("  Write these files?", default=False):
		print("[yellow]Nothing written.[/]")
		return None

	result = fw_sync(skip_unchanged=skip_unchanged)
	if result is None:
		return None
	check = fw_verify()

	if check and check["ok"]:
		if reset or (not assume_yes and Confirm.ask(
				"  Reset the board now?", default=False)):
			fw_reset()
	return {"sync": result, "verify": check}


## End of initalization message
print("Script initalization finished.")

if __name__ == "__main__":
	print("[bold]Ready.[/bold] fw_run() for the whole thing, or step through "
			"with fw_device() / fw_identify() / fw_dryrun() / fw_sync().")
