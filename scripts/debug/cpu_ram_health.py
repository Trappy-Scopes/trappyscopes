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

CPU and RAM health. A standard two-hour test of a scope's processor, memory,
power supply and cooling: does this board need replacing? The same protocol
on every scope, so the scopes can be compared with each other.

	install_requirements()   # once per scope: stress-ng, sysbench, smartmontools (apt)
	create_exp()
	start()                  # asks for sudo once; ~2 h 8 min, then saves, offloads and stops

The run, in order (protocol cpu_ram_health/2)
---------------------------------------------
1. Checks    tools present, no acquisition running, enough free RAM.
2. Settle    60 s idle. Refused if something else uses more than 10% of the
             CPU meanwhile: it would skew the speed numbers.
3. Speed     sysbench, 3 repeats of 20 s: CPU on 1 thread, CPU on 4 threads,
             RAM write and RAM read (4 threads, 16 MiB blocks -- larger than
             the 1 MiB L2 cache, so the RAM is measured, not the cache).
4. Stress    stress-ng, 120 min: 4 CPU workers cycling through every CPU
             method, plus 1 memory worker cycling through every memory
             pattern on a fixed 5 GiB. --verify checks results against the
             known answer. Only computation and memory stressors: the others
             deliberately provoke faults, which would hide real ones in the
             kernel log.
5. Cooldown  2 min idle: how fast the board cools.
Throughout: telemetry.csv at 1 Hz (clock, temperature, throttle flags, fan,
CPU use, memory, swap, SSD temperature) and kernel.log.

Protocol history: /1 (2026-11-22) had a 60 min stress phase and no SSD
temperature. /2 doubles the stress phase and adds the SSD temperature.

SSD temperature
---------------
The test does not use the SSD; the drive only sits near a hot board. Its own
sensor is read over SMART (`smartctl -A`, needs sudo: asked once at the start)
every ssd_period_s, in its own thread, and lands in telemetry.csv on the next
row. The experiment directory's drive is the one read. Some drives report a
fixed value instead of a live reading (the NTech MX600s always say 40 C); a
drive that never changes is reported as such. After 3 failed reads in a row
the reading stops, so a struggling USB bridge is not pushed further. The
camera sensor's temperature is not logged: reading it needs the camera
running.

Standard
--------
Same tools (Debian 12 packages, versions recorded), same parameters (STANDARD
below), same checks and order on every scope. A parameter changed in
exp.attribs is recorded as a deviation and the run is marked non-standard, so
a shortened run is never mistaken for a standard one. Change STANDARD itself
only together with a new PROTOCOL version.

Verdict (health.yaml and the health_verdict event)
--------------------------------------------------
FAIL        a wrong result (stress-ng exit 2, a "fail:" line or "failed: N"
            in its summary), or a kernel error during the run (oops,
            segfault, lockup, RCU stall, SError). A board fault: replace it,
            or retest to confirm.
INCOMPLETE  stopped early, out of memory, or a tool did not finish. Rerun.
WARN        under-voltage (check the power supply and cable first),
            frequency capping or throttling, SoC at 80 C or more, clock below
            arm_freq under load, kernel log not captured.
PASS        none of the above.
Speed has no pass mark: identical boards should agree within a few percent,
so it is judged across the fleet. SSD temperature and swap are reported, not
judged. Holding 5 GiB makes the kernel swap briefly on healthy boards too
(protocol /1 counted swap as WARN, and all 8 scopes got it).

Throttle flags: `vcgencmd get_throttled` keeps "has happened since boot" bits,
so an event between samples is still caught -- unless the same bit was already
set before the run (reported as before_run); then only the 5 s samples see it.

Requirements -- installed by install_requirements()
---------------------------------------------------
stress-ng (0.15.06), sysbench (1.0.20) and smartmontools from Debian 12 via
apt, plus any of their libraries not already installed. stress-ng and
sysbench are command-line programs only. smartmontools also ships smartd, a
background service that polls drives; on a Pi with USB storage that has been
reported to hang the USB controller, so install_requirements() disables it
(as storage_health_statistics does). Only the smartctl command is used.
Undo: sudo apt-get remove stress-ng sysbench (smartmontools is shared with
storage_health_statistics; leave it).

Side effects of a run
---------------------
- 2 h at full load: the SoC runs hot, the fan runs, power draw rises.
- 5 GiB of RAM held for 2 h. Refused if that would leave less than 1 GiB.
- One SMART read of the SSD every minute (sudo smartctl -A).
- The scope cannot record meanwhile. Refused if an acquisition is running;
  do not start one during the test.
- No disk load: only the logs are written (a few MB).
- A faulty board may freeze or reboot. That is itself the finding; telemetry
  and the kernel log up to that moment are on disk.
- The Pico is used only to read T&H, at the start and at the end.
"""

import atexit
import csv
import datetime
import glob
import importlib.util
import logging as log
import math
import os
import re
import shlex
import shutil
import signal
import socket
import statistics
import subprocess
import threading
import time

import yaml
from rich import print
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


__description__ = \
"""CPU and RAM health -- standard 2 h stress test with a pass/fail verdict.

install_requirements() once per scope, then create_exp() and
start(). Runs ~2 h 8 min, offloads and stops on its own.
"""

PROTOCOL = "cpu_ram_health/2"

## The standard. populate_exp() copies it into exp.attribs; any value changed
## there is recorded as a deviation. Change these only with a new PROTOCOL.
STANDARD = {
	"settle_s": 60,
	"max_background_busy_pct": 10,
	"speed_repeats": 3,
	"speed_s": 20,
	"cpu_max_prime": 10000,
	"mem_block": "16M",
	"stress_min": 120,
	"cpu_workers": 4,
	"cpu_method": "all",
	"vm_workers": 1,
	"vm_gib": 5.0,          # fixed size, not a percentage: same work on every scope
	"vm_method": "all",
	"min_free_gib": 1.0,
	"cooldown_s": 120,
	"vcgencmd_period_s": 5,
	"ssd_period_s": 60,     # SMART read of the SSD's temperature
	"hot_c": 80,            # the Pi 4 starts throttling at 80 C
}


## ==========================================================================
##  REQUIREMENTS
## ==========================================================================

REQUIREMENTS = {
	"pip": {},
	"apt": {"stress-ng": "stress-ng", "sysbench": "sysbench",
			"smartmontools": "smartctl"},
	## Ships enabled with smartmontools; unwanted on a scope (see the docstring).
	"disable_services": ["smartd"],
}


def _service_on(svc):
	return any(_run(f"systemctl {q} {svc}", timeout=10)[1].strip() == want
			   for q, want in (("is-enabled", "enabled"), ("is-active", "active")))


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


def install_requirements():
	"""Install stress-ng, sysbench and smartmontools with apt, then disable
	smartd if it is on.

	Explicit by design: this changes the system, so it never runs implicitly.
	No reboot needed. Leaves nothing running in the background.
	"""
	_, missing = check_requirements(verbose=False)
	services = [s for s in REQUIREMENTS["disable_services"] if _service_on(s)]
	if not missing and not services:
		print(Panel(Pretty(tool_versions()), title="[green]already installed"))
		return True
	print(Panel((f"apt-get install -y {' '.join(missing)}\n" if missing else "")
				+ (f"systemctl disable --now {' '.join(services)}\n" if services else "")
				+ "\nNothing is left running in the background.\n"
				"Undo: sudo apt-get remove stress-ng sysbench", title="install"))
	if not sudo_session("apt and systemctl"):
		print("[red]Needs sudo; nothing installed.")
		return False
	try:
		if missing:
			cmd = f"sudo -n apt-get install -y {' '.join(missing)}"
			rc, out = _run(cmd, timeout=900)
			if rc != 0:
				## Stale package lists are the usual cause; refresh once and retry.
				print("[yellow]apt failed; refreshing package lists and retrying...")
				_run("sudo -n apt-get update", timeout=900)
				rc, out = _run(cmd, timeout=900)
			if rc != 0:
				print(Panel(f"[red]apt failed (rc={rc}).\n{out[-800:]}", title="install"))
				return False
		## After apt: installing smartmontools is what turns smartd on.
		for svc in REQUIREMENTS["disable_services"]:
			if _service_on(svc):
				_run(f"sudo -n systemctl disable --now {svc}", timeout=60)
			print(f"  {svc}: {_run(f'systemctl is-active {svc}', timeout=10)[1].strip()}")
	finally:
		sudo_end()
	_, missing = check_requirements(verbose=False)
	if missing:
		print(f"[red]Still missing: {missing}")
		return False
	print(Panel(Pretty(tool_versions()), title="[green]installed"))
	return True


def tool_versions():
	return {"stress_ng": _run("stress-ng --version", timeout=10)[1].strip(),
			"sysbench": _run("sysbench --version", timeout=10)[1].strip(),
			"smartctl": _run("smartctl --version", timeout=10)[1].strip().split("\n")[0]}


## ==========================================================================
##  sudo -- authenticate once (same scheme as storage_health_statistics)
## ==========================================================================
## install_requirements() needs it, and start() for smartctl (asked once at
## the start, kept alive for the whole run). Every privileged call uses `sudo -n`,
## which never prompts. The password is typed into sudo itself (`sudo -v`
## reads /dev/tty) and never passes through this script. Never replace this
## with `sudo -S`.

_sudo_stop = threading.Event()
_sudo_owned = False


def sudo_session(why):
	"""Ensure sudo works for the rest of the call. Returns True if it does."""
	global _sudo_owned
	if _run("sudo -n true", timeout=5)[0] == 0:
		return True
	print(Panel(f"sudo is needed for {why}.\nYou will be asked for your password "
				"[bold]once[/bold].", title="sudo"))
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
##  Shell and system readers
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


def _read(path, default=""):
	try:
		with open(path, errors="replace") as f:
			return f.read().strip()
	except OSError:
		return default


def _write(path, text):
	with open(path, "w") as f:
		f.write(text)


def _int(s):
	try:
		return int(s)
	except (TypeError, ValueError):
		return None


def _grab(rx, text):
	m = re.search(rx, text, re.M)
	return m.group(1).strip() if m else None


def _hex(v):
	return f"0x{v:x}" if isinstance(v, int) else ""


def _meminfo():
	"""/proc/meminfo in MiB."""
	d = {}
	for line in _read("/proc/meminfo").splitlines():
		k, _, v = line.partition(":")
		n = _int(v.split()[0]) if v.split() else None
		if n is not None:
			d[k] = n / 1024
	return d


def _soc_temp():
	t = _int(_read("/sys/class/thermal/thermal_zone0/temp"))
	return round(t / 1000, 1) if t is not None else None


def _cpu_times():
	"""(total, idle) jiffies from the aggregate line of /proc/stat."""
	v = [int(x) for x in _read("/proc/stat").splitlines()[0].split()[1:9]]
	return sum(v), v[3] + v[4]                       # idle + iowait


def _busy_pct(a, b):
	dt = b[0] - a[0]
	return round(100 * (1 - (b[1] - a[1]) / dt), 1) if dt > 0 else None


def _fan_paths():
	"""cur_state of every fan cooling device (gpio-fan, pwm-fan)."""
	return [os.path.join(d, "cur_state")
			for d in sorted(glob.glob("/sys/class/thermal/cooling_device*"))
			if "fan" in _read(os.path.join(d, "type"))]


def _vc(cmd):
	"""One vcgencmd value: the text after '=' ('throttled=0x0' -> '0x0')."""
	out = _run(f"vcgencmd {cmd}", timeout=5)[1].strip()
	return out.partition("=")[2] if "=" in out else None


def _throttled():
	try:
		return int(_vc("get_throttled"), 16)
	except (TypeError, ValueError):
		return None


def _arm_mhz():
	"""The clock the ARM cores actually run at, from the firmware. cpufreq in
	sysfs shows only what Linux asked for, not what the firmware allowed."""
	hz = _int(_vc("measure_clock arm"))
	return round(hz / 1e6) if hz else None


## Bits of get_throttled: n = happening now, n + 16 = has happened since boot.
THROTTLE_NAMES = ["under-voltage", "frequency capped", "throttled",
				  "soft temperature limit"]


def _names(bits):
	return [n for i, n in enumerate(THROTTLE_NAMES) if bits & (1 << i)]


## T&H sits behind the Pico's serial link, which can hang. Read in a thread
## with a timeout; after one hang, do not try again.
_tandh_hung = False


def _tandh(timeout=10):
	global _tandh_hung
	if _tandh_hung:
		return None
	box = {}

	def _read_sensor():
		try:
			box["v"] = ScopeAssembly.current.tandh.read()
		except Exception as e:
			box["e"] = f"{type(e).__name__}: {e}"

	t = threading.Thread(target=_read_sensor, daemon=True, name="tandh-read")
	t.start()
	t.join(timeout)
	if t.is_alive():
		_tandh_hung = True
		log.error("tandh read timed out")
		return None
	v = box.get("v")
	## A reading of exactly 0 is never real.
	if isinstance(v, dict) and v.get("temp") and v.get("humidity"):
		return {"temp_c": round(float(v["temp"]), 2),
				"rh_pct": round(float(v["humidity"]), 1)}
	return None


def system_snapshot():
	"""What this board is and how it is configured. Raw copies in raw/."""
	cpuinfo = _read("/proc/cpuinfo")
	cfg_txt = _run("vcgencmd get_config int", timeout=10)[1]
	_write("raw/get_config.txt", cfg_txt)
	cfg = dict(re.findall(r"^(\w+)=(\S+)$", cfg_txt, re.M))
	for p in ("/boot/firmware/config.txt", "/boot/config.txt"):
		if os.path.exists(p):
			shutil.copy(p, "raw/config.txt")
			break
	mem = _meminfo()
	return {
		"hostname": socket.gethostname(),
		"model": _read("/proc/device-tree/model").rstrip("\x00"),
		"revision": _grab(r"^Revision\s*:\s*(.+)$", cpuinfo),
		"serial": _grab(r"^Serial\s*:\s*(.+)$", cpuinfo),
		"mem_total_mib": round(mem.get("MemTotal", 0)),
		"swap_total_mib": round(mem.get("SwapTotal", 0)),
		"kernel": os.uname().release,
		"os": _grab(r'^PRETTY_NAME="?([^"\n]+)', _read("/etc/os-release")),
		"firmware": " ".join(_run("vcgencmd version", timeout=10)[1].split()),
		"bootloader": " ".join(_run("vcgencmd bootloader_version", timeout=10)[1].split()),
		"arm_freq": _int(cfg.get("arm_freq")),
		"over_voltage": _int(cfg.get("over_voltage")),
		"temp_limit": _int(cfg.get("temp_limit")),
		"governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
		"fans": len(_fan_paths()),
		**tool_versions(),
	}


## ==========================================================================
##  SSD temperature -- SMART, own thread
## ==========================================================================

## Device types a USB bridge may need, tried in this order (as in
## storage_health_statistics.smart_read).
SMART_TYPES = ("", "-d sat", "-d sat,12", "-d sntasmedia", "-d usbjmicron", "-d scsi")
## The RAW_VALUE of ATA attribute 194, else 190 (Samsung reports only 190),
## else the NVMe health log. Same patterns as storage_health_statistics.
SMART_TEMP = (r"^\s*194\s+\S+\s+0x[0-9a-fA-F]+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)",
			  r"^\s*190\s+\S+\s+0x[0-9a-fA-F]+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)",
			  r"^Temperature:\s+(\d+)\s+Celsius")


def _smart_temp(disk, dtype, timeout=20):
	"""One temperature reading in C, or None. smartctl's exit code is a bit
	mask that is non-zero on healthy drives too, so only the output counts."""
	out = _run(f"sudo -n smartctl {dtype} -A {shlex.quote(disk)}", timeout=timeout)[1]
	for pat in SMART_TEMP:
		m = re.search(pat, out or "", re.M)
		if m:
			return int(m.group(1))
	return None


def ssd_setup(path, have_sudo):
	"""The drive under `path` and how to read its temperature. Saves the full
	SMART output once in raw/smart_start.txt."""
	info = {"available": False}
	src = _run(f"findmnt -no SOURCE --target {shlex.quote(path)}", timeout=10)[1].strip()
	pk = _run(f"lsblk -no PKNAME {shlex.quote(src)}", timeout=10)[1].strip().splitlines() \
		if src.startswith("/dev/") else []
	disk = f"/dev/{pk[0].strip()}" if pk and pk[0].strip() else src
	info["disk"] = disk
	model, _, tran = _run(f"lsblk -dno MODEL,TRAN {shlex.quote(disk)}",
						  timeout=10)[1].strip().rpartition(" ")
	info["model"], info["transport"] = model.strip(), tran
	if not disk.startswith("/dev/sd") and not disk.startswith("/dev/nvme"):
		info["why"] = f"the experiment directory is on {disk or '?'}, not an SSD"
	elif not shutil.which("smartctl"):
		info["why"] = "smartctl missing: run install_requirements()"
	elif not have_sudo:
		info["why"] = "no sudo: smartctl needs root"
	else:
		for t in SMART_TYPES:
			if _smart_temp(disk, t) is not None:
				info.update(available=True, device_type=t or "(auto)", dtype=t)
				_write("raw/smart_start.txt", _run(f"sudo -n smartctl {t} -a {shlex.quote(disk)}",
												   timeout=60)[1])
				break
		else:
			info["why"] = "no temperature in the SMART output with any device type"
	return info


class SSDTemp:
	"""Reads the SSD's temperature every `period` s in its own thread: smartctl
	through a USB bridge can take seconds, and must never stall the 1 Hz
	telemetry. take() hands each new reading over once. Stops for good after 3
	failed reads in a row."""

	def __init__(self, disk, dtype, period):
		self.disk, self.dtype, self.period = disk, dtype, period
		self.readings, self.failures, self.gave_up = [], 0, False
		self._new, self._lock, self._stop = None, threading.Lock(), threading.Event()
		self._t = threading.Thread(target=self._loop, daemon=True, name="ssd-temp")

	def start(self):
		self._t.start()

	def stop(self):
		self._stop.set()
		self._t.join(timeout=30)

	def take(self):
		with self._lock:
			v, self._new = self._new, None
		return v

	def _loop(self):
		wait = 0.0
		while not self._stop.wait(wait):
			wait = self.period
			v = _smart_temp(self.disk, self.dtype)
			if v is None:
				self.failures += 1
				log.error(f"SSD temperature read failed ({self.failures} in a row)")
				if self.failures >= 3:
					self.gave_up = True
					return
				continue
			self.failures = 0
			self.readings.append(v)
			with self._lock:
				self._new = v


## ==========================================================================
##  Telemetry -- 1 Hz, background thread
## ==========================================================================

TELEMETRY_COLS = ["wall", "elapsed_s", "phase", "arm_mhz", "throttled",
				  "soc_temp_c", "fan", "busy_pct", "load1", "mem_avail_mib",
				  "swap_used_mib", "ssd_temp_c"]


class Telemetry:
	"""One row a second, on whole wall-clock seconds. /proc and /sys are read
	every second; vcgencmd forks, so arm_mhz and throttled are read every
	vc_period seconds and left blank in between. ssd_temp_c is filled on the
	row after each SMART reading (every ssd_period_s) and blank otherwise."""

	def __init__(self, path, vc_period, ssd=None):
		self.path, self.vc_period, self.ssd = path, vc_period, ssd
		self.phase, self.rows = "start", []
		self._fans = _fan_paths()
		self._stop = threading.Event()
		self._t = threading.Thread(target=self._loop, daemon=True,
								   name="health-telemetry")

	def start(self):
		self._t.start()

	def stop(self):
		self._stop.set()
		self._t.join(timeout=10)

	def last(self, key):
		"""The latest non-blank value of a column."""
		return next((r[key] for r in reversed(self.rows) if r[key] is not None), None)

	def _loop(self):
		t0, prev, next_vc = time.time(), _cpu_times(), 0.0
		with open(self.path, "w", newline="") as f:
			w = csv.writer(f)
			w.writerow(TELEMETRY_COLS)
			while not self._stop.wait(max(0.0, math.floor(time.time()) + 1 - time.time())):
				try:
					wall = time.time()
					arm = thr = None
					if wall >= next_vc:
						next_vc = wall + self.vc_period - 0.5
						arm, thr = _arm_mhz(), _throttled()
					cur = _cpu_times()
					busy, prev = _busy_pct(prev, cur), cur
					mem = _meminfo()
					fans = [_int(_read(p)) for p in self._fans]
					fans = [x for x in fans if x is not None]
					row = {"wall": round(wall, 3), "elapsed_s": round(wall - t0, 1),
						   "phase": self.phase, "arm_mhz": arm, "throttled": thr,
						   "soc_temp_c": _soc_temp(), "fan": max(fans) if fans else None,
						   "busy_pct": busy,
						   "load1": float(_read("/proc/loadavg", "0").split()[0]),
						   "mem_avail_mib": round(mem.get("MemAvailable", 0)),
						   "swap_used_mib": round(mem.get("SwapTotal", 0)
												  - mem.get("SwapFree", 0)),
						   "ssd_temp_c": self.ssd.take() if self.ssd else None}
					self.rows.append(row)
					w.writerow([_hex(row[k]) if k == "throttled" else
								("" if row[k] is None else row[k]) for k in TELEMETRY_COLS])
					f.flush()
				except Exception as e:
					log.error(f"telemetry: {type(e).__name__}: {e}")


## ==========================================================================
##  Kernel message stream  (same pattern as storage_health_statistics)
## ==========================================================================

_dmesg_proc = None


def start_kernel_log():
	global _dmesg_proc
	for cmd in (["stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["sudo", "-n", "stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["dmesg", "--follow", "-T"]):
		f = None
		try:
			f = open("kernel.log", "a", buffering=1)
			_dmesg_proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
			time.sleep(0.8)
			tail = _read("kernel.log")[-400:]
			bad = re.search(r"operation not permitted|password is required|not found|"
							r"read kernel buffer failed|invalid option", tail, re.I)
			if _dmesg_proc.poll() is None and not bad:
				return True
			try:
				_dmesg_proc.terminate(); _dmesg_proc.wait(timeout=3)
			except Exception:
				pass
			_dmesg_proc = None
		except Exception as e:
			log.error(f"kernel log ({cmd[0]}): {e}")
		finally:
			if f is not None:
				try:
					f.close()
				except Exception:
					pass
	return False


def stop_kernel_log():
	global _dmesg_proc
	if _dmesg_proc is not None:
		try:
			_dmesg_proc.terminate(); _dmesg_proc.wait(timeout=5)
		except Exception:
			try:
				_dmesg_proc.kill()
			except Exception:
				pass
		_dmesg_proc = None


## Case-sensitive on purpose: "BUG:" must not match "debug:".
_KFAULT = re.compile(r"Internal error|Oops|\bBUG:|Unable to handle|SError|segfault|"
					 r"unhandled .*fault|Kernel panic|soft lockup|hard LOCKUP|"
					 r"rcu.*stall|EDAC|External Abort|Bus error")
_KOOM = re.compile(r"Out of memory|oom-kill|invoked oom-killer")
_KUV = re.compile(r"[Uu]nder-?voltage")


def kernel_check(offset):
	"""Kernel lines written after `offset` bytes, i.e. during the run.
	`dmesg --follow` first prints everything since boot; that part is skipped."""
	if offset is None:
		return {"captured": False}
	try:
		with open("kernel.log", errors="replace") as f:
			f.seek(offset)
			lines = f.read().splitlines()
	except OSError:
		return {"captured": False}
	return {"captured": True, "lines": len(lines),
			"faults": [l for l in lines if _KFAULT.search(l)][:20],
			"oom": [l for l in lines if _KOOM.search(l)][:5],
			"under_voltage": [l for l in lines if _KUV.search(l)][:5]}


## ==========================================================================
##  Speed -- sysbench
## ==========================================================================

_EVENTS = r"events per second:\s*([\d.]+)"
_MIBS = r"\(([\d.]+) MiB/sec\)"
_MEM = ("memory --memory-block-size={block} --memory-total-size=1000G "
		"--memory-access-mode=seq --threads=4 --memory-oper=")

SPEED_TESTS = [   # name, sysbench arguments, result regex, unit
	("cpu_1t", "cpu --cpu-max-prime={prime} --threads=1", _EVENTS, "events/s"),
	("cpu_4t", "cpu --cpu-max-prime={prime} --threads=4", _EVENTS, "events/s"),
	("mem_write_4t", _MEM + "write", _MIBS, "MiB/s"),
	("mem_read_4t", _MEM + "read", _MIBS, "MiB/s"),
]


def run_speed(a):
	out = {}
	for name, args, rx, unit in SPEED_TESTS:
		vals = []
		for rep in range(1, a["speed_repeats"] + 1):
			cmd = (f"sysbench {args.format(prime=a['cpu_max_prime'], block=a['mem_block'])} "
				   f"--time={a['speed_s']} run")
			rc, txt = _run(cmd, timeout=a["speed_s"] + 60)
			_write(f"raw/sysbench_{name}_{rep}.txt", f"$ {cmd}\n(rc={rc})\n{txt}")
			m = re.search(rx, txt) if rc == 0 else None
			v = float(m.group(1)) if m else None
			Experiment.current.mstreams["speed"](test=name, unit=unit, repeat=rep, value=v)
			print(f"  {name} #{rep}: {v} {unit}")
			vals.append(v)
		good = [v for v in vals if v is not None]
		med = statistics.median(good) if good else None
		out[name] = {"unit": unit, "values": vals, "median": med,
					 "spread_pct": round(100 * (max(good) - min(good)) / med, 2)
								   if len(good) > 1 and med else None}
	return out


## ==========================================================================
##  Stress -- stress-ng
## ==========================================================================

STRESS_EXIT = {   # stress-ng(1), EXIT STATUS
	0: "success", 1: "bad options or harness error", 2: "a stressor failed",
	3: "not enough resources", 4: "not implemented", 5: "killed by a signal",
	6: "unexpected exit", 7: "bogo-ops metrics untrustworthy",
}

_stress_proc = None


def _kill_stress(wait_first=0):
	"""Stop stress-ng if it is still running: wait, then SIGINT (it cleans up),
	then SIGKILL. Idempotent; also runs at exit, so it never outlives us."""
	p = _stress_proc
	if p is None or p.poll() is not None:
		return
	for sig, wait in ((None, wait_first), (signal.SIGINT, 30), (signal.SIGKILL, 10)):
		try:
			if sig is not None:
				p.send_signal(sig)
			p.wait(timeout=wait)
			return
		except subprocess.TimeoutExpired:
			continue
		except Exception as e:
			log.error(f"stopping stress-ng: {e}")


atexit.register(_kill_stress)


def _stress_metrics(path):
	try:
		with open(path) as f:
			y = yaml.safe_load(f) or {}
	except Exception as e:
		return {"error": f"{type(e).__name__}: {e}"}
	return {m["stressor"]: {k: v for k, v in m.items() if k != "stressor"}
			for m in (y.get("metrics") or []) if isinstance(m, dict) and "stressor" in m}


def run_stress(a, tel):
	global _stress_proc
	secs = int(round(a["stress_min"] * 60))
	## A fixed size per worker: the man page is ambiguous about how a
	## percentage is split between workers. With the standard 1 worker, the
	## worker holds exactly vm_gib.
	per_worker_mib = int(a["vm_gib"] * 1024 / a["vm_workers"])
	cmd = ["stress-ng",
		   "--cpu", str(a["cpu_workers"]), "--cpu-method", a["cpu_method"],
		   "--vm", str(a["vm_workers"]), "--vm-bytes", f"{per_worker_mib}M",
		   "--vm-method", a["vm_method"],
		   ## No --vm-keep: remapping each loop lands on different physical
		   ## pages, so the hour covers more of the RAM.
		   "--verify", "--timeout", f"{secs}s", "--metrics-brief", "--tz",
		   "--log-file", "raw/stress-ng.log", "--yaml", "raw/stress-ng.yaml"]
	res = {"cmd": " ".join(cmd), "planned_s": secs, "interrupted": False, "hung": False}
	print(f"[green]{res['cmd']}")
	t0 = time.time()
	next_print = t0 + 300
	with open("raw/stress-ng.out", "w") as out:
		## Same process group: a Ctrl-C at the terminal reaches stress-ng too.
		_stress_proc = p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
											env={**os.environ, "LC_ALL": "C"})
		try:
			while p.poll() is None:
				time.sleep(1)
				now = time.time()
				if now >= next_print:
					next_print += 300
					print(f"{datetime.datetime.now():%H:%M}  stress "
						  f"{(now - t0) / 60:.0f}/{secs / 60:.0f} min   SoC "
						  f"{tel.last('soc_temp_c')} C   clock {tel.last('arm_mhz')} MHz   "
						  f"throttled {_hex(tel.last('throttled'))}")
				if now > t0 + secs + 300:
					res["hung"] = True
					break
		except KeyboardInterrupt:
			res["interrupted"] = True
		_kill_stress(wait_first=30 if res["interrupted"] else 0)
	res["ran_s"] = round(time.time() - t0, 1)
	res["exit_code"] = p.returncode
	res["exit_meaning"] = STRESS_EXIT.get(p.returncode, "killed")
	txt = _read("raw/stress-ng.log") or _read("raw/stress-ng.out")
	res["fail_lines"] = [l for l in txt.splitlines() if re.search(r"\bfail:", l)][:20]
	failed = _grab(r"\bfailed:\s*(\d+)", txt)
	res["failed_stressors"] = _int(failed)
	res["metrics"] = _stress_metrics("raw/stress-ng.yaml")
	return res


## ==========================================================================
##  Summary and verdict
## ==========================================================================

def summarise(rows, arm_freq):
	"""Per phase: temperature, clock, CPU use, fan, swap, SSD temperature."""
	out = {}
	for ph in ("settle", "speed", "stress", "cooldown"):
		r = [x for x in rows if x["phase"] == ph]
		if not r:
			continue
		col = lambda k: [x[k] for x in r if x[k] is not None]
		t, mhz, busy, fan = col("soc_temp_c"), col("arm_mhz"), col("busy_pct"), col("fan")
		s = {"seconds": len(r)}
		if t:
			s.update(soc_c_start=t[0], soc_c_mean=round(statistics.mean(t), 1),
					 soc_c_max=max(t), soc_c_end=t[-1])
		if mhz:
			s.update(arm_mhz_median=statistics.median(mhz), arm_mhz_min=min(mhz))
			if arm_freq:
				s["clock_held_pct"] = round(100 * sum(m >= 0.99 * arm_freq for m in mhz)
											/ len(mhz), 1)
		if busy:
			s["busy_pct_mean"] = round(statistics.mean(busy), 1)
		if fan:
			s["fan_on_pct"] = round(100 * sum(x > 0 for x in fan) / len(fan), 1)
		s["swap_used_mib_max"] = max(col("swap_used_mib") or [0])
		ssd = col("ssd_temp_c")
		if ssd:
			s.update(ssd_c_start=ssd[0], ssd_c_max=max(ssd), ssd_c_end=ssd[-1])
		out[ph] = s
	return out


def ssd_summary(info, ssd, rows):
	"""The SSD's temperature over the run: start (first reading), the plateau
	(mean over the last 10 min of stress), the highest, and the rise."""
	out = {k: v for k, v in info.items() if k != "dtype"}
	if ssd is None:
		return out
	vals = [x["ssd_temp_c"] for x in rows if x["ssd_temp_c"] is not None]
	stress = [x for x in rows if x["phase"] == "stress"]
	last = [x["ssd_temp_c"] for x in stress if x["ssd_temp_c"] is not None
			and x["wall"] >= stress[-1]["wall"] - 600] if stress else []
	out.update(readings=len(vals), failed_reads_in_a_row=ssd.failures, gave_up=ssd.gave_up)
	if vals:
		out.update(start_c=vals[0], max_c=max(vals), end_c=vals[-1],
				   plateau_c=round(statistics.mean(last), 1) if last else None,
				   constant=len(set(vals)) == 1 and len(vals) > 2)
		if last:
			out["rise_c"] = round(out["plateau_c"] - vals[0], 1)
	return out


def throttle_summary(thr0, rows, thr_end):
	samples = [x["throttled"] for x in rows if isinstance(x["throttled"], int)]
	samples += [thr_end] if isinstance(thr_end, int) else []
	seen = 0
	for s in samples:
		seen |= s
	before = ((thr0 or 0) >> 16) & 0xF
	during = (seen & 0xF) | (((seen >> 16) & 0xF) & ~before)
	return {"start": _hex(thr0), "end": _hex(thr_end), "samples": len(samples),
			"during": _names(during), "before_run": _names(before)}


def findings(res, a):
	F = []
	add = lambda level, title, detail="": F.append(
		{"level": level, "title": title, "detail": detail})
	st, k = res.get("stress") or {}, res.get("kernel") or {}
	ph = res.get("phases", {}).get("stress", {})

	if st.get("exit_code") == 2 or st.get("fail_lines") or (st.get("failed_stressors") or 0) > 0:
		add("FAIL", "stress-ng found a wrong result",
			f"exit {st.get('exit_code')}, {len(st.get('fail_lines') or [])} fail lines "
			f"(raw/stress-ng.log)")
	if k.get("faults"):
		add("FAIL", "kernel errors during the run", " | ".join(k["faults"][:3]))

	if res.get("stopped_early") or st.get("interrupted"):
		add("INCOMPLETE", "stopped early", f"stress ran {st.get('ran_s')} of "
			f"{st.get('planned_s')} s" if st else "before the stress phase")
	elif not st:
		add("INCOMPLETE", "the stress phase did not run")
	elif st.get("hung"):
		add("INCOMPLETE", "stress-ng did not stop on time", "stopped by the script")
	elif st.get("exit_code") not in (0, 2):
		add("INCOMPLETE", f"stress-ng exit {st.get('exit_code')}", st.get("exit_meaning"))
	elif st.get("ran_s", 0) < 0.95 * st.get("planned_s", 0):
		add("INCOMPLETE", "stress-ng ended early", f"{st['ran_s']} of {st['planned_s']} s")
	if res.get("error"):
		add("INCOMPLETE", "script error", res["error"])
	if k.get("oom"):
		add("INCOMPLETE", "out of memory during the run", " | ".join(k["oom"][:2]))
	if any(v["median"] is None for v in (res.get("speed") or {}).values()):
		add("INCOMPLETE", "a speed test gave no result", "raw/sysbench_*.txt")

	thr = res.get("throttle", {})
	if "under-voltage" in thr.get("during", []) or k.get("under_voltage"):
		add("WARN", "under-voltage during the run",
			"check the power supply and cable before blaming the board")
	if set(thr.get("during", [])) & {"frequency capped", "throttled", "soft temperature limit"}:
		add("WARN", "clock capped or throttled", ", ".join(thr["during"]))
	if (ph.get("soc_c_max") or 0) >= a["hot_c"]:
		add("WARN", f"SoC reached {ph['soc_c_max']} C", "check the fan and heatsink")
	if ph.get("clock_held_pct") is not None and ph["clock_held_pct"] < 99:
		add("WARN", "clock below arm_freq under load",
			f"at arm_freq {ph['clock_held_pct']}% of the time, min {ph.get('arm_mhz_min')} MHz")
	if not k.get("captured"):
		add("WARN", "kernel log not captured", "kernel errors were not checked")

	## Reported, not judged.
	swap0 = (res.get("phases", {}).get("settle") or {}).get("swap_used_mib_max", 0)
	if ph.get("swap_used_mib_max", 0) > swap0 + 64:
		add("INFO", "swap used during the stress phase",
			f"{swap0} -> {ph['swap_used_mib_max']} MiB; holding {a['vm_gib']} GiB makes "
			f"the kernel swap briefly on healthy boards too")
	ssd = res.get("ssd") or {}
	if not ssd.get("available"):
		add("INFO", "SSD temperature not read", ssd.get("why", ""))
	elif ssd.get("gave_up"):
		add("INFO", "SSD temperature reads stopped after 3 failures in a row",
			f"{ssd.get('readings')} readings before that")
	elif ssd.get("constant"):
		add("INFO", f"SSD reported {ssd.get('start_c')} C throughout",
			f"{ssd.get('model')}: probably a fixed value, not a live sensor")
	if res.get("deviations"):
		add("INFO", "non-standard parameters", str(res["deviations"]))
	if thr.get("before_run"):
		add("INFO", "throttle flags already set before the run (since boot)",
			", ".join(thr["before_run"]))
	return F


VERDICT_ORDER = ["FAIL", "INCOMPLETE", "WARN"]


## ==========================================================================
##  Experiment
## ==========================================================================

def populate_exp():
	exp = Experiment.current
	exp.attribs["protocol"] = PROTOCOL
	exp.attribs.update(STANDARD)
	## "HH:MM" (local) to start several scopes together, or None to start now.
	exp.attribs["start_at"] = None
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["cpu_ram_health"])
	exp.new_measurementstream("speed", monitors=["test", "unit"],
							  measurements=["repeat", "value"])
	populate_exp()
	check_requirements()


def _acquisition_running():
	rc, out = _run("pgrep -af 'mjpeg_continuous|intensity_continuous|"
				   "mjpeg_sampling|light_perturbation|sampling_record|"
				   "storage_health|stress-ng|sysbench' | grep -v pgrep", timeout=5)
	return out.strip() if rc == 0 and out.strip() else ""


def _refusal(a):
	_, missing = check_requirements(verbose=False)
	if missing:
		return f"Missing {' '.join(missing)}. Run install_requirements()."
	busy = _acquisition_running()
	if busy:
		return f"An acquisition or another test appears to be running:\n{busy}"
	avail = _meminfo().get("MemAvailable", 0) / 1024
	if avail < a["vm_gib"] + a["min_free_gib"]:
		return (f"{avail:.1f} GiB of RAM available; the memory test holds "
				f"{a['vm_gib']} GiB and must leave {a['min_free_gib']} GiB. "
				f"Close whatever holds memory.")
	return ""


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


class _Refused(Exception):
	pass


def start():
	global exp
	exp = Experiment.current
	a = exp.attribs
	## The framework writes attribs to experiment.yaml only on exp.close();
	## linked here, every save has them.
	exp.logs["attribs"] = a

	why = _refusal(a)
	if why:
		print(Panel(f"[red]{escape(why)}", title="refused"))
		return
	## Before any waiting, so nobody has to come back to type a password.
	## Without sudo the run goes ahead, without the SSD temperature.
	have_sudo = sudo_session("smartctl, to read the SSD's temperature every "
							 f"{a['ssd_period_s']} s")
	if a.get("start_at") and not _wait_until(a["start_at"]):
		print(Panel(f"[red]start_at {a['start_at']} has passed.", title="refused"))
		sudo_end()
		return

	exp.schedule.clear()                 # nothing scheduled: no Pico traffic
	os.makedirs("raw", exist_ok=True)
	deviations = {k: {"standard": v, "used": a.get(k)}
				  for k, v in STANDARD.items() if a.get(k) != v}
	if deviations:
		print(Panel(Pretty(deviations), title="[yellow]non-standard run"))
	res = {"protocol": PROTOCOL, "standard": not deviations, "deviations": deviations,
		   "started": datetime.datetime.now().isoformat(timespec="seconds"),
		   "system": system_snapshot(), "stopped_early": False}
	res["system"]["tandh_start"] = _tandh()
	thr0 = _throttled()

	k_offset = None
	if start_kernel_log():
		time.sleep(1)                    # let dmesg finish the since-boot part
		k_offset = os.path.getsize("kernel.log")
	ssd_info = ssd_setup(exp.exp_dir, have_sudo)
	ssd = SSDTemp(ssd_info["disk"], ssd_info["dtype"], a["ssd_period_s"]) \
		if ssd_info["available"] else None
	tel = Telemetry(exp.newfile("telemetry.csv", abspath=False), a["vcgencmd_period_s"], ssd)
	if ssd:
		ssd.start()
	tel.start()

	total_min = (a["settle_s"] + len(SPEED_TESTS) * a["speed_repeats"] * (a["speed_s"] + 1)
				 + a["stress_min"] * 60 + a["cooldown_s"]) / 60
	end = datetime.datetime.now() + datetime.timedelta(minutes=total_min)
	ssd_line = (f"SSD temperature: {ssd_info['disk']} ({ssd_info['model']}), every "
				f"{a['ssd_period_s']} s." if ssd else
				f"SSD temperature: not read ({ssd_info.get('why')}).")
	print(Panel(f"Protocol {PROTOCOL}: settle {a['settle_s']} s, speed "
				f"~{len(SPEED_TESTS) * a['speed_repeats'] * (a['speed_s'] + 1) / 60:.0f} min, "
				f"stress {a['stress_min']} min, cooldown {a['cooldown_s']} s.\n"
				f"{escape(ssd_line)}\n"
				f"Ends about {end:%H:%M}. Ctrl-C stops early.", title="cpu_ram_health"))
	try:
		tel.phase = "settle"
		c0 = _cpu_times()
		time.sleep(a["settle_s"])
		busy = _busy_pct(c0, _cpu_times())
		res["background_busy_pct"] = busy
		lim = a.get("max_background_busy_pct")
		if lim is not None and busy is not None and busy > lim:
			top = _run("ps -eo pcpu,pid,args --sort=-pcpu | head -8", timeout=10)[1]
			print(Panel(f"[red]{busy}% of the CPU busy while idle (limit {lim}%):\n"
						f"{escape(top)}\nStop these first. Raising the limit makes the run "
						f"non-standard.", title="refused"))
			raise _Refused(f"background load {busy}% > {lim}%")

		tel.phase = "speed"
		print("[green]Speed (sysbench)")
		res["speed"] = run_speed(a)

		tel.phase = "stress"
		res["stress"] = run_stress(a, tel)
		if res["stress"]["interrupted"]:
			raise KeyboardInterrupt

		tel.phase = "cooldown"
		print(f"Cooldown {a['cooldown_s']} s...")
		time.sleep(a["cooldown_s"])
	except KeyboardInterrupt:
		res["stopped_early"] = True
		print("\n[yellow]Stopped early.")
	except _Refused as e:
		res["refused"] = str(e)
	except Exception as e:
		## Still summarised and saved below; the verdict says INCOMPLETE.
		res["error"] = f"{type(e).__name__}: {e}"
		log.error(f"cpu_ram_health: {res['error']}")
		print(f"[red]{escape(res['error'])}")
	finally:
		_kill_stress()
		tel.stop()
		if ssd:
			ssd.stop()
			_step("SMART at the end", lambda: _write("raw/smart_end.txt", _run(
				f"sudo -n smartctl {ssd.dtype} -a {shlex.quote(ssd.disk)}", timeout=60)[1]))
		sudo_end()
		stop_kernel_log()

	res["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
	res["ssd"] = ssd_summary(ssd_info, ssd, tel.rows)
	thr_end = _throttled()
	if "refused" in res:
		exp.log_event("health_refused", attribs={"why": res["refused"]})
		_write_results(res)
		exp.__save__()
		return

	res["system"]["tandh_end"] = _tandh()
	res["phases"] = summarise(tel.rows, res["system"]["arm_freq"])
	res["throttle"] = throttle_summary(thr0, tel.rows, thr_end)
	res["kernel"] = kernel_check(k_offset)
	res["findings"] = findings(res, a)
	res["verdict"] = next((v for v in VERDICT_ORDER
						   if any(f["level"] == v for f in res["findings"])), "PASS")
	_write_results(res)
	_report(res)
	cleanup(res)


def _write_results(res):
	with open("health.yaml", "w") as f:
		yaml.safe_dump(res, f, sort_keys=False, width=100)


def _report(res):
	exp = Experiment.current
	st = res["phases"].get("stress", {})
	speed = {k: v["median"] for k, v in (res.get("speed") or {}).items()}
	exp.log_event("health_verdict", attribs={
		"verdict": res["verdict"], "standard": res["standard"], "protocol": PROTOCOL,
		"serial": res["system"].get("serial"), **{f"speed_{k}": v for k, v in speed.items()},
		"soc_c_max": st.get("soc_c_max"), "clock_held_pct": st.get("clock_held_pct"),
		"throttle_during": res["throttle"]["during"],
		"stress_exit": (res.get("stress") or {}).get("exit_code"),
		"ssd_c_start": res["ssd"].get("start_c"), "ssd_c_plateau": res["ssd"].get("plateau_c"),
		"ssd_constant": res["ssd"].get("constant")})
	for f in res["findings"]:
		exp.log_event("health_finding", attribs=f)

	colour = {"PASS": "green", "WARN": "yellow"}.get(res["verdict"], "red")
	lines = [f"[bold {colour}]{res['verdict']}[/]"
			 + ("" if res["standard"] else "  [yellow](non-standard run)[/]"), ""]
	lines += [escape(f"{f['level']}: {f['title']}" + (f" -- {f['detail']}" if f["detail"] else ""))
			  for f in res["findings"]] or ["No findings."]
	lines += ["", "Speed (median of repeats):"]
	lines += [f"  {k:13s} {v['median']} {v['unit']}  (spread {v['spread_pct']}%)"
			  for k, v in (res.get("speed") or {}).items()]
	lines += ["", f"Stress: SoC max {st.get('soc_c_max')} C, clock "
			  f"{st.get('arm_mhz_median')} MHz (held {st.get('clock_held_pct')}%), "
			  f"fan on {st.get('fan_on_pct')}%"]
	s = res["ssd"]
	lines += [escape(f"SSD ({s.get('model')}): {s.get('start_c')} C at the start, plateau "
					 f"{s.get('plateau_c')} C, max {s.get('max_c')} C"
					 + ("  (constant: not a live sensor?)" if s.get("constant") else ""))
			  if s.get("readings") else escape(f"SSD: not read ({s.get('why', 'no readings')})")]
	print(Panel("\n".join(lines), title="CPU and RAM health"))


def _step(what, fn):
	"""One cleanup step. A failure is logged and the next step still runs."""
	try:
		return fn()
	except Exception as e:
		log.error(f"cleanup: {what} failed: {type(e).__name__}: {e}")
		print(f"[red]cleanup: {what} failed: {type(e).__name__}: {e}")


def cleanup(res=None):
	"""Stop the schedule, save and offload. Does NOT close the experiment --
	type exp.close() afterwards."""
	global exp
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True
	_kill_stress()
	_step("note", lambda: exp.note(f"CPU and RAM health ({PROTOCOL}): "
								   f"{(res or {}).get('verdict', '?')}"))
	_step("save", exp.__save__)
	_step("sync", exp.sync_dir)
	print(Panel("[yellow]Done. The experiment is still OPEN -- type "
				"[bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel("install_requirements()   # once per scope\n"
				"create_exp() -> start()\n\n"
				f"Standard 1 h CPU and RAM health test ({PROTOCOL}).",
				title="cpu_ram_health"))
	check_requirements()
