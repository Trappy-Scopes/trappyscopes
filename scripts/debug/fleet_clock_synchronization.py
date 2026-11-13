#!/usr/bin/env python3
# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : November 2026                                                  |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+

"""
AI Generated -- new file, Claude (Anthropic), 2026-11.

Fleet clock synchronisation. Measures how well this scope's clock agrees with
the other scopes, so that disturbances recorded on several scopes can be lined
up in time. The clocks are not made perfect; the error is characterised.

	install_requirements()   # once per scope: chrony, NAS as the only source
	create_exp()
	start_acq_blocking()     # runs for exp.params["duration_h"], then exits

How it works -- standard tools only, nothing home-made
------------------------------------------------------
1. The NAS serves NTP on each scope lane (DSM: Control Panel > Regional
   Options > NTP Service). Every scope follows that one clock.
2. Each scope runs chrony with the lane NAS as its ONLY source. The NAS is
   chosen from this scope's own address and exp.params["lane_servers"], so a
   scope on lane A uses the lane-A address of the NAS, over the cable.
3. This experiment logs what chrony itself measures, like Lab Streaming Layer
   logs clock offsets next to its data:
     tracking.csv  every tracking_period_s, on the same wall-clock seconds on
                   every scope (unprivileged: `chronyc tracking`)
     ntp stream    one row per clock update from the NAS (`chronyc ntpdata`,
                   which needs root; asked only when the update is new)
   The analysis notebook combines the scopes.

Maximum error (chrony's documented bound, `chronyc tracking`):
	max_error_s = |clock_offset_s| + root_dispersion_s + root_delay_s / 2
This is relative to the stratum-1 server the NAS follows. Scope to scope, the
NAS's own part is common to both and can be removed using the NAS's root
delay and dispersion in the ntp stream; that is done in the notebook.

Sign convention: clock_offset_s and offset_s are positive when this scope's
clock is AHEAD (fast); freq_ppm is positive when it would run fast. The ntpdata
sign is checked live against `chronyc sources` (setup stream, sign_check).

RECOMMENDED: make sure the NTP server the scopes follow (here the NAS) is
itself well synchronised before the experiment starts. This is a suggestion;
the run warns but does not stop.

Side effects of install_requirements(), checked on the Raspberry Pi forums
---------------------------------------------------------------------------
- Installing chrony removes systemd-timesyncd (the packages conflict).
- `timedatectl timesync-status` stops working (it is timesyncd-only);
  `timedatectl` itself still works.
- fake-hwclock still restores the last saved time at boot; chrony then steps
  the clock once (makestep, first updates only) and only slews afterwards, so
  there are no jumps mid-run.
- A scope with no lane connection has no time source: chrony keeps the
  clock free-running and the logged error grows.
- The scope does not become a time server (no `allow` line).
- Undo: `sudo apt-get install systemd-timesyncd` (removes chrony). The
  original chrony.conf is kept at /etc/chrony/chrony.conf.orig-trappyscopes.
"""

import atexit
import csv
import datetime
import importlib.util
import ipaddress
import logging as log
import math
import os
import shutil
import socket
import statistics
import subprocess
import tempfile
import threading
import time
from datetime import timedelta

from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


__description__ = \
"""Fleet clock synchronisation -- this scope's clock against the lane NAS.

install_requirements() once per scope, then create_exp() and
start_acq_blocking(). Runs for exp.params["duration_h"] and exits.
"""

## Lane subnet -> the NAS address on that lane. Copied into exp.params by
## populate_exp(); edit it there, or pass lane_servers= to
## install_requirements() before an experiment exists.
LANE_SERVERS = {
	"192.168.1.0/24": "192.168.1.1",
	"192.168.2.0/24": "192.168.2.1",
}
SERVER_OPTIONS = "iburst minpoll 4 maxpoll 6"      # poll every 16-64 s on a LAN

CHRONY_CONF = "/etc/chrony/chrony.conf"
CHRONY_ORIG = "/etc/chrony/chrony.conf.orig-trappyscopes"
TAG = "#[fleet_clock_synchronization] "


## ==========================================================================
##  REQUIREMENTS
## ==========================================================================

REQUIREMENTS = {
	"pip": {},
	"apt": {"chrony": "chronyc"},
}


def check_requirements(verbose=True):
	"""Return (missing_pip, missing_apt)."""
	missing_pip = [dist for dist, mod in REQUIREMENTS["pip"].items()
				   if importlib.util.find_spec(mod) is None]
	missing_apt = [pkg for pkg, exe in REQUIREMENTS["apt"].items()
				   if shutil.which(exe) is None]
	if verbose:
		if missing_pip or missing_apt:
			print(Panel("[yellow]Missing: " + " ".join(missing_pip + missing_apt) +
						"\nRun [bold]install_requirements()[/bold].",
						title="requirements"))
		else:
			print("[green]Requirements present.")
	return missing_pip, missing_apt


def install_requirements(lane_servers=None):
	"""Install chrony and make the lane NAS its only time source.

	Explicit by design: this changes the system, so it never runs implicitly.
	Safe to run again: the config is always rebuilt from the original file.
	"""
	lane_servers = lane_servers or _lane_servers()
	lane = find_lane(lane_servers)
	if not lane["server"]:
		print(Panel(f"[red]{lane['why']}\nNothing changed.", title="install"))
		return False

	print(Panel(f"Lane NAS: [bold]{lane['server']}[/bold] via {lane['iface']} "
				f"({lane['addr']})\n\nThis installs chrony, which REMOVES "
				f"systemd-timesyncd, and makes the NAS the only time source.\n"
				f"Undo: sudo apt-get install systemd-timesyncd",
				title="fleet clock synchronisation"))
	if not sudo_session("apt and the chrony config"):
		print("[red]Needs sudo; nothing changed.")
		return False
	try:
		if shutil.which("chronyc") is None:
			rc, out = _run("sudo -n apt-get install -y chrony", timeout=900)
			if rc != 0:
				print("[yellow]apt failed; refreshing package lists and retrying...")
				_run("sudo -n apt-get update", timeout=900)
				rc, out = _run("sudo -n apt-get install -y chrony", timeout=900)
			if rc != 0:
				print(Panel(f"[red]apt failed (rc={rc}).\n{out[-800:]}", title="install"))
				return False

		if not write_chrony_conf(lane["server"]):
			return False
		_run("sudo -n systemctl enable chrony", timeout=60)
		rc, out = _run("sudo -n systemctl restart chrony", timeout=60)
		if rc != 0:
			print(Panel(f"[red]chrony did not restart.\n{out[-800:]}", title="install"))
			return False

		print("Waiting up to 2 min for chrony to sync to the NAS...")
		_run("chronyc waitsync 60 0.01 0 2", timeout=150)
	finally:
		sudo_end()

	ok, report = verify_setup(lane)
	print(Panel(Pretty(report), title=f"[{'green' if ok else 'red'}]setup "
				f"{'OK' if ok else 'NOT OK'}"))
	return ok


def build_chrony_conf(original, server, options=SERVER_OPTIONS):
	"""The shipped chrony.conf with every other time source switched off.

	Commented out, not deleted, so the file still shows what Debian shipped:
	  pool / server / peer      -- the public pool
	  sourcedir                 -- DHCP-supplied servers and sources.d
	  confdir / include         -- anything else that could add a source
	  leapsectz                 -- Debian's own comment says to drop it when a
	                               source serves leap-smeared time, which
	                               time.google.com (a common NAS upstream) does
	Everything else (driftfile, makestep, rtcsync, ...) is kept.
	"""
	off = ("pool", "server", "peer", "sourcedir", "confdir", "include", "leapsectz")
	out, have = [], set()
	for line in original.splitlines():
		word = line.split()[0] if line.strip() else ""
		if word in off:
			out.append(TAG + line)
		else:
			out.append(line)
			have.add(word)
	out += ["", TAG + "written " + datetime.datetime.now().isoformat(timespec="seconds"),
			"# The lane NAS is the ONLY time source on this scope.",
			f"server {server} {options}"]
	## The two defaults this setup relies on, should a distro not ship them.
	if "makestep" not in have:
		out.append("makestep 1 3")
	if "rtcsync" not in have:
		out.append("rtcsync")         # keeps `timedatectl` reporting "synchronized"
	return "\n".join(out) + "\n"


def write_chrony_conf(server):
	"""Back up the original once, then write the NAS-only config (needs sudo)."""
	_run(f"sudo -n cp -n -p {CHRONY_CONF} {CHRONY_ORIG}", timeout=10)
	src = CHRONY_ORIG if os.path.exists(CHRONY_ORIG) else CHRONY_CONF
	try:
		with open(src) as f:
			original = f.read()
	except OSError as e:
		print(f"[red]Cannot read {src}: {e}")
		return False
	text = build_chrony_conf(original, server, _attr("chrony_server_options",
													 SERVER_OPTIONS))
	fd, tmp = tempfile.mkstemp(suffix=".conf")
	with os.fdopen(fd, "w") as f:
		f.write(text)
	rc, out = _run(f"sudo -n install -m 644 -o root -g root {tmp} {CHRONY_CONF}",
				   timeout=10)
	os.unlink(tmp)
	if rc != 0:
		print(Panel(f"[red]Could not write {CHRONY_CONF}.\n{out}", title="install"))
		return False
	print(f"[green]{CHRONY_CONF} written; original kept at {CHRONY_ORIG}.")
	return True


## ==========================================================================
##  sudo -- authenticate once per run (same scheme as storage_health_statistics)
## ==========================================================================
## Every privileged call uses `sudo -n`, which never prompts. The password is
## typed into sudo itself (`sudo -v` reads /dev/tty) and never passes through
## this script. Never replace this with `sudo -S`.

_sudo_stop = threading.Event()
_sudo_owned = False


def sudo_session(why):
	"""Ensure sudo works for the rest of the run. Returns True if it does."""
	global _sudo_owned
	if _run("sudo -n true", timeout=5)[0] == 0:
		return True
	print(Panel(f"sudo is needed for {why}.\nYou will be asked for your password "
				"[bold]once[/bold]; it is kept alive until the run ends.",
				title="sudo"))
	try:
		rc = subprocess.run(["sudo", "-v"]).returncode      # interactive
	except Exception:
		rc = 1
	if rc != 0:
		print("[yellow]sudo not authenticated.")
		return False
	_sudo_owned = True
	_sudo_stop.clear()

	def _keepalive():
		while not _sudo_stop.wait(60):
			subprocess.run(["sudo", "-n", "-v"], stdout=subprocess.DEVNULL,
						   stderr=subprocess.DEVNULL)

	threading.Thread(target=_keepalive, daemon=True, name="sudo-keepalive").start()
	return True


def sudo_end():
	"""Stop refreshing, and drop the cache if this run created it."""
	global _sudo_owned
	_sudo_stop.set()
	if _sudo_owned:
		subprocess.run(["sudo", "-k"], stdout=subprocess.DEVNULL,
					   stderr=subprocess.DEVNULL)
		_sudo_owned = False


atexit.register(sudo_end)


## ==========================================================================
##  Shell and parsing
## ==========================================================================

def _run(cmd, timeout=60):
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
						   env={**os.environ, "LC_ALL": "C"})
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return None, f"<timed out after {timeout}s>"
	except Exception as e:
		return None, f"<{type(e).__name__}: {e}>"


def _kv(text):
	"""chronyc's 'Key   : value' report -> dict."""
	d = {}
	for line in text.splitlines():
		k, sep, v = line.partition(":")
		if sep:
			d[k.strip()] = v.strip()
	return d


def _num(s):
	"""First number in s, or None."""
	try:
		return float(s.split()[0])
	except (AttributeError, IndexError, ValueError):
		return None


def _signed(s, behind="slow"):
	"""'0.000012 seconds slow of NTP time' -> -0.000012 (positive = fast)."""
	x = _num(s)
	return -x if x is not None and behind in s else x


def read_tracking():
	"""`chronyc tracking` (no root needed). None if chrony is not answering."""
	rc, out = _run("chronyc -n tracking", timeout=10)
	if rc != 0:
		return None
	kv = _kv(out)
	ref = kv.get("Reference ID", "").split()
	t = {
		"ref_id": ref[0] if ref else "",
		"ref_name": ref[1].strip("()") if len(ref) > 1 else "",
		"stratum": _num(kv.get("Stratum")),
		"ref_time": kv.get("Ref time (UTC)", ""),       # changes on every clock update
		"leap": kv.get("Leap status", ""),
		"clock_offset_s": _signed(kv.get("System time", "")),
		"last_offset_s": _num(kv.get("Last offset")),
		"rms_offset_s": _num(kv.get("RMS offset")),
		"freq_ppm": _signed(kv.get("Frequency", "")),
		"skew_ppm": _num(kv.get("Skew")),
		"root_delay_s": _num(kv.get("Root delay")),
		"root_dispersion_s": _num(kv.get("Root dispersion")),
		"update_interval_s": _num(kv.get("Update interval")),
	}
	parts = (t["clock_offset_s"], t["root_dispersion_s"], t["root_delay_s"])
	t["max_error_s"] = (abs(parts[0]) + parts[1] + 0.5 * parts[2]
						if None not in parts else None)
	return t


def read_ntpdata(server):
	"""`chronyc ntpdata` for the NAS: the last NTP exchange. Needs root."""
	rc, out = _run(f"sudo -n chronyc -n ntpdata {server}", timeout=10)
	if rc != 0 or "Remote address" not in out:
		return None
	kv = _kv(out)
	poll = kv.get("Poll interval", "")
	return {
		"nas_leap": kv.get("Leap status", ""),
		"nas_stratum": _num(kv.get("Stratum")),
		"nas_root_delay_s": _num(kv.get("Root delay")),
		"nas_root_dispersion_s": _num(kv.get("Root dispersion")),
		"offset_s": _num(kv.get("Offset")),
		"peer_delay_s": _num(kv.get("Peer delay")),
		"peer_dispersion_s": _num(kv.get("Peer dispersion")),
		"poll_s": _num(poll.split("(")[-1]) if "(" in poll else None,
		"valid_rx": _num(kv.get("Total valid RX")),
		"good_rx": _num(kv.get("Total good RX")),
		"rx_timestamping": kv.get("RX timestamping", ""),
	}


def read_sources():
	"""`chronyc -c sources` -> list of dicts (no root needed)."""
	rc, out = _run("chronyc -n -c sources", timeout=10)
	if rc != 0:
		return None
	keys = ["mode", "state", "name", "stratum", "poll", "reach", "last_rx_s",
			"adj_offset_s", "meas_offset_s", "error_s"]
	return [dict(zip(keys, row)) for row in csv.reader(out.splitlines())
			if len(row) >= len(keys)]


## ==========================================================================
##  Lane and setup checks
## ==========================================================================

def _attr(key, default):
	exp = Experiment.current
	return exp.attribs.get(key, default) if isinstance(exp, Experiment) else default


def _lane_servers():
	return _attr("lane_servers", LANE_SERVERS)


def find_lane(lane_servers):
	"""Which lane is this scope on? Decided by its own IPv4 addresses."""
	rc, out = _run("ip -4 -o addr show", timeout=5)
	seen = []
	for line in out.splitlines():
		parts = line.split()
		if "inet" not in parts:
			continue
		iface = parts[1]
		addr = ipaddress.ip_interface(parts[parts.index("inet") + 1]).ip
		seen.append(f"{iface} {addr}")
		for net, server in lane_servers.items():
			if addr in ipaddress.ip_network(net):
				return {"iface": iface, "addr": str(addr), "server": server, "why": ""}
	return {"iface": "", "addr": "", "server": "",
			"why": f"No address on a lane subnet {list(lane_servers)}. "
				   f"This scope has: {', '.join(seen) or 'none'}. Check the cable, "
				   f"or exp.params['lane_servers']."}


def verify_setup(lane):
	"""Is the NAS the only source, reached over the lane? -> (ok, report)."""
	sources = read_sources() or []
	names = [s["name"] for s in sources]
	route = _run(f"ip -4 route get {lane['server']}", timeout=5)[1].split()
	route_dev = route[route.index("dev") + 1] if "dev" in route else ""
	r = {
		"server": lane["server"],
		"iface": lane["iface"],
		"route_dev": route_dev,
		"chrony_active": _run("systemctl is-active chrony", 5)[1].strip(),
		"timesyncd": _run("systemctl is-active systemd-timesyncd", 5)[1].strip(),
		"sources": names,
		"ntp_synchronized": _run("timedatectl show -p NTPSynchronized --value",
								 5)[1].strip(),
		"chrony_version": _run("chronyc -v", 5)[1].strip(),
	}
	ok = (r["chrony_active"] == "active" and r["timesyncd"] != "active"
		  and names == [lane["server"]] and route_dev == lane["iface"])
	return ok, r


def sign_check(nd, sources):
	"""Does ntpdata's Offset use the documented `sources` sign (positive =
	this clock ahead)? Both describe the same last exchange."""
	try:
		meas = float(next(s for s in sources if s["name"] == nd["server"])
					 ["meas_offset_s"])
		a = nd["offset_s"]
		if abs(a - meas) <= max(1e-6, 0.05 * abs(meas)):
			return "agree"
		if abs(a + meas) <= max(1e-6, 0.05 * abs(meas)):
			return f"OPPOSITE (ntpdata {a:+.6f}, sources {meas:+.6f})"
		return f"differ (ntpdata {a:+.6f}, sources {meas:+.6f})"
	except Exception as e:
		return f"unchecked ({type(e).__name__})"


## ==========================================================================
##  Experiment
## ==========================================================================

def populate_exp():
	exp = Experiment.current
	exp.attribs["lane_servers"] = dict(LANE_SERVERS)
	exp.attribs["chrony_server_options"] = SERVER_OPTIONS
	exp.attribs["duration_h"] = 2.0
	exp.attribs["tracking_period_s"] = 10
	## "HH:MM" (local) to start every scope at the same moment, or None to
	## start at once. Not needed for the analysis -- samples tick on the same
	## wall-clock seconds on every scope -- only to give identical windows.
	exp.attribs["start_at"] = None
	exp.attribs["tandh_sampling_period_minutes"] = 5
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["fleet_clock_sync"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("setup",
		monitors=["phase", "iface", "local_addr", "server", "route_dev",
				  "chrony_version", "chrony_active", "timesyncd", "sources",
				  "ntp_synchronized", "nas_leap", "rx_timestamping", "sign_check"],
		measurements=["n_sources", "nas_stratum", "clock_offset_s", "max_error_s"])
	## One row per clock update from the NAS: low-rate, so a stream is fine. The
	## 10 s samples go to tracking.csv -- every stream row rewrites the YAML.
	exp.new_measurementstream("ntp",
		monitors=["leap", "nas_leap"],
		measurements=["offset_s", "peer_delay_s", "peer_dispersion_s",
					  "nas_stratum", "nas_root_delay_s", "nas_root_dispersion_s",
					  "poll_s", "clock_offset_s", "root_delay_s",
					  "root_dispersion_s", "freq_ppm", "skew_ppm", "max_error_s"])
	populate_exp()
	check_requirements()


def record_sensor():
	"""Scheduled job -- must never raise; ExpScheduler.loop has no try/except."""
	try:
		try:
			value = ScopeAssembly.current.tandh.read()
		except Exception:
			value = {"temp": 0, "humidity": 0}
		Experiment.current.mstreams["tandh"](**value).panel()
	except Exception as e:
		log.error(f"record_sensor failed: {e}")


def record_setup(phase, lane, have_sudo):
	"""One `setup` row: what this scope is synced to, read live."""
	ok, r = verify_setup(lane)
	tr = read_tracking() or {}
	nd = read_ntpdata(lane["server"]) if have_sudo else None
	sign = sign_check({**nd, "server": lane["server"]}, read_sources() or []) \
		if nd else "unchecked (ntpdata needs sudo)"
	row = dict(phase=phase, iface=lane["iface"], local_addr=lane["addr"],
			   server=lane["server"], route_dev=r["route_dev"],
			   chrony_version=r["chrony_version"], chrony_active=r["chrony_active"],
			   timesyncd=r["timesyncd"], sources=",".join(r["sources"]),
			   ntp_synchronized=r["ntp_synchronized"],
			   nas_leap=(nd or {}).get("nas_leap", ""),
			   rx_timestamping=(nd or {}).get("rx_timestamping", ""),
			   sign_check=sign, n_sources=len(r["sources"]),
			   nas_stratum=(nd or {}).get("nas_stratum"),
			   clock_offset_s=tr.get("clock_offset_s"),
			   max_error_s=tr.get("max_error_s"))
	Experiment.current.mstreams["setup"](**row).panel()
	Experiment.current.log_event("clock_check", attribs={"ok": ok, **row})
	return ok, row


def _wait_until(hhmm):
	"""Sleep until today's HH:MM (local). False if that time has passed."""
	h, m = (int(x) for x in hhmm.split(":"))
	target = datetime.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
	wait = (target - datetime.datetime.now()).total_seconds()
	if wait < -60:
		return False
	print(f"Starting at {hhmm} ({max(wait, 0):.0f} s from now)...")
	time.sleep(max(wait, 0))
	return True


TRACKING_COLS = ["wall", "ref_id", "stratum", "leap", "clock_offset_s",
				 "last_offset_s", "rms_offset_s", "freq_ppm", "skew_ppm",
				 "root_delay_s", "root_dispersion_s", "update_interval_s",
				 "max_error_s"]


def start_acq_blocking():
	global exp
	exp = Experiment.current
	a = exp.attribs

	lane = find_lane(a.get("lane_servers", LANE_SERVERS))
	if not lane["server"]:
		print(Panel(f"[red]{lane['why']}", title="refused"))
		return
	if shutil.which("chronyc") is None:
		print(Panel("[red]chrony is not installed. Run install_requirements().",
					title="refused"))
		return
	ok, r = verify_setup(lane)
	if not ok:
		print(Panel(Pretty(r), title="[red]refused: the NAS is not the only "
					"source -- run install_requirements()"))
		return

	tr = read_tracking() or {}
	print(Panel(f"Recommended: make sure the NTP server these scopes follow "
				f"(the NAS, {lane['server']}) is itself well synchronised before "
				f"you start.\nChrony on this scope reports stratum "
				f"{tr.get('stratum')} and leap status '{tr.get('leap')}'.",
				title="[yellow]before you start"))

	have_sudo = sudo_session("`chronyc ntpdata` (the per-exchange `ntp` stream)")
	if not have_sudo:
		print("[yellow]Without sudo only tracking.csv is recorded.")

	if a.get("start_at") and not _wait_until(a["start_at"]):
		print(Panel(f"[red]start_at {a['start_at']} has passed.", title="refused"))
		sudo_end()
		return

	exp.schedule.clear()
	record_sensor()
	exp.schedule.every(a["tandh_sampling_period_minutes"]).minutes \
		.until(timedelta(hours=a["duration_h"] + 1)).do(record_sensor)

	record_setup("start", lane, have_sudo)
	path = exp.newfile("tracking.csv", abspath=False)
	period = a["tracking_period_s"]
	end = time.time() + a["duration_h"] * 3600
	errors, last_rx, last_ref, n_ntp = [], None, None, 0
	print(f"[green]Recording until "
		  f"{datetime.datetime.fromtimestamp(end):%H:%M}. Ctrl-C stops early.")
	try:
		with open(path, "w", newline="") as f:
			w = csv.writer(f)
			w.writerow(TRACKING_COLS)
			while time.time() < end:
				## Tick on whole multiples of the period, so every scope samples
				## at the same wall-clock seconds.
				time.sleep(max(0.0, (math.floor(time.time() / period) + 1) * period
								   - time.time()))
				wall = time.time()
				t = read_tracking()
				if t is None:
					log.error("chronyc tracking failed")
					continue
				w.writerow([f"{wall:.6f}"] + [t[k] for k in TRACKING_COLS[1:]])
				f.flush()
				if t["max_error_s"] is not None:
					errors.append(t["max_error_s"])
				## ntpdata needs sudo, and every sudo call is logged; ask only
				## when chrony has made a new clock update.
				nd = None
				if have_sudo and t["ref_time"] != last_ref:
					last_ref = t["ref_time"]
					nd = read_ntpdata(lane["server"])
				if nd and nd["valid_rx"] != last_rx:
					if last_rx is not None:       # skip the exchange from before the run
						exp.mstreams["ntp"](leap=t["leap"], **{k: nd[k] for k in
							("nas_leap", "offset_s", "peer_delay_s",
							 "peer_dispersion_s", "nas_stratum", "nas_root_delay_s",
							 "nas_root_dispersion_s", "poll_s")},
							**{k: t[k] for k in ("clock_offset_s", "root_delay_s",
							 "root_dispersion_s", "freq_ppm", "skew_ppm",
							 "max_error_s")})
						n_ntp += 1
						print(f"{datetime.datetime.now():%H:%M:%S}  offset "
							  f"{nd['offset_s'] * 1e6:+8.1f} us  delay "
							  f"{nd['peer_delay_s'] * 1e6:7.1f} us  max error "
							  f"{(t['max_error_s'] or 0) * 1e3:6.3f} ms")
					last_rx = nd["valid_rx"]
	except KeyboardInterrupt:
		print("\n[yellow]Stopped early.")
	finally:
		try:
			record_setup("end", lane, have_sudo)
		except Exception as e:
			log.error(f"end setup row failed: {e}")
		sudo_end()

	summary = {"tracking_rows": len(errors), "ntp_rows": n_ntp}
	if errors:
		errors.sort()
		summary.update(max_error_ms_median=round(statistics.median(errors) * 1e3, 3),
					   max_error_ms_p99=round(errors[int(0.99 * (len(errors) - 1))] * 1e3, 3),
					   max_error_ms_max=round(errors[-1] * 1e3, 3))
	exp.log_event("clock_summary", attribs=summary)
	print(Panel(Pretty(summary), title="fleet clock synchronisation"))
	cleanup(summary)


def cleanup(summary=None):
	"""Save, offload, stop the schedule. Does NOT close -- exp.close() joins
	the scheduler thread. Type exp.close() afterwards."""
	global exp
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True
	try:
		shutil.copy(CHRONY_CONF, "chrony.conf")       # the config this run used
	except OSError as e:
		log.error(f"chrony.conf not copied: {e}")
	exp.__save__()
	exp.sync_dir()
	exp.note(f"Fleet clock synchronisation run complete on "
			 f"{socket.gethostname()}: {summary}")
	print(Panel("[yellow]Done. The experiment is still OPEN -- type "
				"[bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel("install_requirements()   # once per scope\n"
				"create_exp() -> start_acq_blocking()\n\n"
				"Measures this scope's clock against the lane NAS.",
				title="fleet_clock_synchronization"))
	check_requirements()
