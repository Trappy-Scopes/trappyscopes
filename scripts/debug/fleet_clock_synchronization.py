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
This is relative to the stratum-1 server the NTP server follows. Scope to
scope, the NTP server's own part is common to both and can be removed using
its root delay and dispersion (server_root_delay_s, server_root_dispersion_s in
the ntp stream); that is done in the calibration notebook
(trappyframe: calibrations/fleet_clock_synchronization.ipynb).

Sign convention: clock_offset_s and offset_s are positive when this scope's
clock is AHEAD (fast); freq_ppm is positive when it would run fast. The ntpdata
sign is checked live against `chronyc sources` (setup stream, sign_check).

RECOMMENDED: make sure the NTP server the scopes follow (here the NAS) is
itself well synchronised before the experiment starts. This is a suggestion;
the run warns but does not stop.

The Pico's clock (pico stream)
------------------------------
Nothing in trappyscopes or the Pico firmware sets the Pico's RTC (the
firmware's own NTP sync, DTSync, is commented out), so it keeps whatever time
it had since power-up. This run reads it over the existing serial link:
  as found   the first pico_set_after_min minutes, RTC untouched
  set        once, to this Pi's UTC, on a whole second
  after_set  the rest of the run: the drift, in ppm, is the slope
Method: Cristian's algorithm (NTP's request-response, over serial). The
MicroPython RTC counts whole seconds, so the Pico waits for its seconds to tick
over and reports when, in its microsecond ticks. The tick happened in this Pi's
time between t0 + wait and t1 - (Pico busy - wait), where t0 is when the
request was sent and t1 when the first reply byte arrived:
	offset_s = Pico time at the tick - this Pi's time at the tick (+ = Pico ahead)
	error_s  = (t1 - t0 - Pico busy) / 2  +  tick resolution
All Pico calls, T&H included, run one at a time from the main loop, with a
timeout: a hung Pico stops the Pico part only.

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
- start_acq_blocking() sets the Pico's RTC to UTC once (pico_set_after_min;
  None leaves it as found). Nothing else on the Pico is changed.
"""

import ast
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

from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


__description__ = \
"""Fleet clock synchronisation -- this scope's clock against the lane NAS, and
its Pico's clock against this scope.

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
		"server_leap": kv.get("Leap status", ""),
		"server_stratum": _num(kv.get("Stratum")),
		"server_root_delay_s": _num(kv.get("Root delay")),
		"server_root_dispersion_s": _num(kv.get("Root dispersion")),
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
##  The Pico's clock
## ==========================================================================

## Loaded onto the Pico once per run, into the raw REPL's globals.
##   _fcs_probe()  waits for the RTC seconds to tick over, then returns
##                 (q, p, e, busy) in us since it started, and the new datetime:
##                 the tick fell between q and e, best estimate p.
##   _fcs_set()    waits wait_us, then sets the RTC.
PICO_CODE = """
import machine, time, sys, os
def _fcs_probe():
    r = machine.RTC(); tu = time.ticks_us; td = time.ticks_diff
    a = tu(); s0 = r.datetime()[6]; q = p = a
    while True:
        q = p; p = tu(); d = r.datetime()
        if d[6] != s0:
            break
        if td(p, a) > 2000000:
            return None
    e = tu()
    return (td(q, a), td(p, a), td(e, a), td(tu(), a), d)
def _fcs_set(d, wait_us):
    a = time.ticks_us()
    while time.ticks_diff(time.ticks_us(), a) < wait_us:
        pass
    machine.RTC().datetime(d)
def _fcs_info():
    ns = []
    for _ in range(3):
        ns.append(time.time_ns() if hasattr(time, "time_ns") else None)
        time.sleep_ms(7)
    return (getattr(sys.implementation, "_machine", ""), os.uname().release,
            machine.RTC().datetime(), ns)
"""

PICO_TIMEOUT_S = 10.0
_pico_stuck = False


def _pico_call(fn, what):
	"""Run one Pico call with a timeout -> (ok, value).

	A serial exec to the Pico has no timeout of its own: if the Pico stops
	answering, the caller blocks for ever. So the call runs on a helper thread.
	After one hang the link is never used again -- a second exec on top of one
	still waiting would interleave on the wire."""
	global _pico_stuck
	if _pico_stuck:
		return False, None
	box = {}

	def run():
		try:
			box["value"] = fn()
		except Exception as e:
			box["err"] = f"{type(e).__name__}: {e}"

	t = threading.Thread(target=run, daemon=True, name="pico-call")
	t.start()
	t.join(PICO_TIMEOUT_S)
	if t.is_alive():
		_pico_stuck = True
		msg = (f"Pico serial: no reply to {what} for {PICO_TIMEOUT_S:.0f} s. No "
			   f"further Pico calls this run; the clock measurement continues.")
		log.error(msg)
		print(Panel(f"[red]{msg}", title="pico hang"))
		try:
			Experiment.current.log_event("pico_hang", attribs={"call": what})
			Experiment.current.note(msg)
		except Exception as e:
			log.error(f"pico_hang log failed: {e}")
		return False, None
	if "err" in box:
		log.error(f"{what} failed: {box['err']}")
		return False, None
	return True, box.get("value")


def _pico_eval(dev, expr):
	"""Evaluate expr on the Pico; its printed repr parsed back."""
	return ast.literal_eval(dev.device.exec_(f"print(repr({expr}))").decode().strip())


def _pico_epoch(d):
	"""MicroPython RTC datetime tuple -> seconds since 1970 (read as UTC)."""
	return datetime.datetime(d[0], d[1], d[2], d[4], d[5], d[6],
							 tzinfo=datetime.timezone.utc).timestamp()


def pico_start(name):
	"""The scope's Pico with the probe loaded, or None (no Pico part)."""
	dev = getattr(ScopeAssembly.current, name, None) if name else None
	if not getattr(dev, "connected", False) or getattr(dev, "device", None) is None:
		print(f"[yellow]No Pico '{name}' connected: its clock is not measured.")
		return None
	ok, _ = _pico_call(lambda: dev.device.exec_(PICO_CODE), "loading the clock probe")
	if not ok:
		return None
	ok, info = _pico_call(lambda: _pico_eval(dev, "_fcs_info()"), "_fcs_info()")
	if ok:
		machine, release, rtc, ns = info
		ns = [x for x in ns if x is not None]
		info = {"device": name, "machine": machine, "micropython": release,
				"rtc_as_found": list(rtc),
				"rtc_subseconds_field": rtc[7],
				"time_ns_subsecond": any(x % 1_000_000_000 for x in ns) if ns else None}
		Experiment.current.log_event("pico_check", attribs=info)
		print(Panel(Pretty(info), title="pico"))
	return dev


def pico_probe(dev):
	"""One clock reading, or None if the RTC did not tick within 2 s."""
	got, first = [], []

	def take(b):                       # pyboard calls this per byte, as it arrives
		if not first:
			first.append(time.time())
		got.append(b)

	t0 = time.time()
	_, err = dev.device.exec_raw("print(repr(_fcs_probe()))", timeout=5,
								 data_consumer=take)
	if err:
		raise RuntimeError(err.decode("utf-8", "replace").strip()[-300:])
	r = ast.literal_eval(b"".join(got).decode().strip("\x04\r\n "))
	if r is None:
		return None
	q, p, e, busy, d = r
	t1 = first[0]
	half = (t1 - t0 - busy * 1e-6) / 2           # half the time on the wire
	tick = t0 + p * 1e-6 + half                  # this Pi's time at the tick
	return {"pico_time": "%04d-%02d-%02dT%02d:%02d:%02d" % (d[0], d[1], d[2], d[4], d[5], d[6]),
			"offset_s": _pico_epoch(d) - tick,
			"error_s": half + max(p - q, e - p) * 1e-6,
			"wire_s": 2 * half, "wait_s": p * 1e-6, "tick": tick, "half_s": half}


def pico_set(dev, half_s):
	"""Set the Pico RTC to this Pi's UTC on a whole second. half_s is the
	estimated time from sending to the Pico starting (half the wire time)."""
	t0 = time.time()
	target = math.floor(t0) + 2                  # at least a second away
	d = datetime.datetime.fromtimestamp(target, datetime.timezone.utc)
	tup = (d.year, d.month, d.day, d.weekday(), d.hour, d.minute, d.second, 0)
	wait_us = int((target - t0 - half_s) * 1e6)
	dev.device.exec_(f"_fcs_set({tup}, {wait_us})")
	return {"target_utc": d.isoformat(), "wait_us": wait_us}


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
	## The Pico's clock: scope device name (None to skip), one reading per
	## period, and when to set it (minutes after the start; None = never).
	exp.attribs["pico_device"] = "pico"
	exp.attribs["pico_probe_period_s"] = 60
	exp.attribs["pico_set_after_min"] = 5
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["fleet_clock_sync"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("setup",
		monitors=["phase", "iface", "local_addr", "server", "route_dev",
				  "chrony_version", "chrony_active", "timesyncd", "sources",
				  "ntp_synchronized", "server_leap", "rx_timestamping", "sign_check"],
		measurements=["n_sources", "server_stratum", "clock_offset_s", "max_error_s"])
	## One row per clock update from the NAS: low-rate, so a stream is fine. The
	## 10 s samples go to tracking.csv -- every stream row rewrites the YAML.
	exp.new_measurementstream("ntp",
		monitors=["leap", "server_leap"],
		measurements=["offset_s", "peer_delay_s", "peer_dispersion_s",
					  "server_stratum", "server_root_delay_s", "server_root_dispersion_s",
					  "poll_s", "clock_offset_s", "root_delay_s",
					  "root_dispersion_s", "freq_ppm", "skew_ppm", "max_error_s"])
	## One row per Pico clock reading (about one a minute).
	exp.new_measurementstream("pico",
		monitors=["phase", "pico_time"],
		measurements=["offset_s", "error_s", "wire_s", "wait_s"])
	populate_exp()
	check_requirements()


def record_sensor():
	"""One T&H row. Called from the main loop, never from a second thread:
	the sensor sits behind the Pico's serial link. Must never raise."""
	try:
		ok, value = _pico_call(lambda: ScopeAssembly.current.tandh.read(), "tandh.read()")
		if not ok or not isinstance(value, dict):
			value = {"temp": 0, "humidity": 0}
		Experiment.current.mstreams["tandh"](**value).panel()
	except Exception as e:
		log.error(f"record_sensor failed: {e}")


def record_pico(dev, phase):
	"""One `pico` row. Returns the reading, or None."""
	ok, r = _pico_call(lambda: pico_probe(dev), "_fcs_probe()")
	if not ok or r is None:
		if ok:
			log.error("Pico RTC did not tick within 2 s")
		return None
	Experiment.current.mstreams["pico"](phase=phase, **{k: r[k] for k in
		("pico_time", "offset_s", "error_s", "wire_s", "wait_s")})
	print(f"{datetime.datetime.now():%H:%M:%S}  Pico clock {r['offset_s']:+.4f} s "
		  f"(+/- {r['error_s'] * 1e3:.1f} ms, {phase})")
	return r


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
			   server_leap=(nd or {}).get("server_leap", ""),
			   rx_timestamping=(nd or {}).get("rx_timestamping", ""),
			   sign_check=sign, n_sources=len(r["sources"]),
			   server_stratum=(nd or {}).get("server_stratum"),
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

	## No scheduler thread: T&H and the Pico clock share the Pico's serial
	## link, so both run from the loop below, one call at a time.
	exp.schedule.clear()
	global _pico_stuck
	_pico_stuck = False
	pico = pico_start(a.get("pico_device", "pico"))
	pico_period = a.get("pico_probe_period_s", 60)
	set_after = a.get("pico_set_after_min", 5)
	pico_phase, pico_rows, last_pico = "as_found", [], None

	record_setup("start", lane, have_sudo)
	path = exp.newfile("tracking.csv", abspath=False)
	period = a["tracking_period_s"]
	start = time.time()
	end = start + a["duration_h"] * 3600
	set_at = start + set_after * 60 if set_after is not None else None
	next_pico = next_tandh = start
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
							("server_leap", "offset_s", "peer_delay_s",
							 "peer_dispersion_s", "server_stratum", "server_root_delay_s",
							 "server_root_dispersion_s", "poll_s")},
							**{k: t[k] for k in ("clock_offset_s", "root_delay_s",
							 "root_dispersion_s", "freq_ppm", "skew_ppm",
							 "max_error_s")})
						n_ntp += 1
						print(f"{datetime.datetime.now():%H:%M:%S}  offset "
							  f"{nd['offset_s'] * 1e6:+8.1f} us  delay "
							  f"{nd['peer_delay_s'] * 1e6:7.1f} us  max error "
							  f"{(t['max_error_s'] or 0) * 1e3:6.3f} ms")
					last_rx = nd["valid_rx"]

				## The Pico, after the tracking sample (which is on the second).
				if pico is not None and not _pico_stuck and wall >= next_pico:
					next_pico += pico_period
					if set_at is not None and wall >= set_at and pico_phase == "as_found":
						half = last_pico["half_s"] if last_pico else 0.002
						ok, info = _pico_call(lambda: pico_set(pico, max(half, 0.0)),
											  "_fcs_set()")
						if ok:
							pico_phase = "after_set"
							exp.log_event("pico_rtc_set", attribs={
								**info, "offset_before_s": (last_pico or {}).get("offset_s")})
						set_at = None              # once, even if it failed
					r = record_pico(pico, pico_phase)
					if r:
						last_pico = r
						pico_rows.append((pico_phase, r["tick"], r["offset_s"]))
				if wall >= next_tandh:
					next_tandh += a["tandh_sampling_period_minutes"] * 60
					record_sensor()
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
	summary["pico_rows"] = len(pico_rows)
	if pico_rows:
		summary["pico_offset_as_found_s"] = round(pico_rows[0][2], 4)
		after = [(x, y) for ph, x, y in pico_rows if ph == "after_set"]
		if len(after) >= 3:
			mx = sum(x for x, _ in after) / len(after)
			my = sum(y for _, y in after) / len(after)
			slope = (sum((x - mx) * (y - my) for x, y in after)
					 / sum((x - mx) ** 2 for x, _ in after))
			summary["pico_drift_ppm"] = round(slope * 1e6, 2)
			summary["pico_offset_end_ms"] = round(after[-1][1] * 1e3, 1)
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
