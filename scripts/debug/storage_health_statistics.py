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

Storage health experiment. Characterises, by default, the two drives that
matter on a scope:

    1. the SD card the OS runs from (resolved from `/`, so its device name does
       not matter -- it is mmcblk0 on most scopes but need not be), and
    2. the drive holding the experiment directory (the SSD, here).

If both resolve to the same device it is characterised once.

    install_requirements()   # once per scope -- see REQUIREMENTS below
    create_exp()
    start_acq_blocking()     # blocks, cleans up and exits on its own

Do NOT run this during an acquisition. The write test competes for the drive,
and querying SMART on a busy USB-attached drive has been reported to hang a Pi
4's USB controller. A running acquisition is detected and refused.

What it measures, per drive
---------------------------
Identity and transport; SMART before and after (SSD; idle only); discard
geometry and provisioning mode; partition alignment; filesystem features and
fragmentation; block-queue tunables; then a WRITE WORKLOAD with per-chunk
latency, a READ-BACK that verifies every chunk's checksum, and 1 Hz telemetry
throughout (I/O pressure, device utilisation, dirty/writeback pages, iowait,
temperature). Kernel messages are streamed to kernel.log for the whole run.

The SSD workload mirrors mjpeg_continuous_autosplit: N files of one real
10-minute split each (9.45 GB at the measured 15.7 MB/s), all held until the
end, so the drive fills progressively and its pseudo-SLC cache is exhausted. A
single small file would measure only that cache -- the steady state, which is
what a 13.5 h acquisition actually runs in, starts tens to hundreds of
gigabytes later.

The SD card gets a SMALL write only. It holds the OS, has a fraction of the
endurance, and on some scopes is nearly full; filling it would be both
impossible and harmful.

Every test file is deleted on every exit path -- success, error, Ctrl-C,
SIGTERM -- and, critically, BEFORE the experiment is synced, so no test data
is ever offloaded.
"""

import atexit
import csv
import datetime
import importlib.util
import json
import logging as log
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import zlib
from datetime import timedelta

from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from expframework.protocol import Protocol
from hive.assembly import ScopeAssembly


__description__ = \
"""Storage health experiment -- SD card + experiment drive.

install_requirements() once per scope, then create_exp() and
start_acq_blocking(). Runs, cleans up and exits on its own.
"""


## ==========================================================================
##  REQUIREMENTS
## ==========================================================================
## Declared here, read by check_requirements() and install_requirements().
##
##   pip              Python distribution -> the module it provides. Installed
##                    with this interpreter's pip, so it lands in the same
##                    environment the framework runs in. Empty: everything this
##                    script imports is either stdlib or already a framework
##                    dependency.
##   apt              system package -> the executable that proves it is there.
##                    pip cannot install system binaries, so these stay with apt.
##   disable_services installed alongside an apt package, unwanted on a scope.
##
## smartd ships enabled with smartmontools. It polls drives in the background,
## and on a Pi with USB storage that has been reported to time out at boot and
## to hang the USB controller when it queries a busy drive -- exactly what must
## not happen during a 13.5 h acquisition. smartctl, the CLI, is all this needs.

REQUIREMENTS = {
	"pip": {},
	"apt": {
		"smartmontools": "smartctl",
		"parted": "parted",
	},
	"disable_services": ["smartd"],
}


def check_requirements(verbose=True):
	"""Return (missing_pip, missing_apt)."""
	missing_pip = [dist for dist, mod in REQUIREMENTS["pip"].items()
				   if importlib.util.find_spec(mod) is None]
	missing_apt = [pkg for pkg, exe in REQUIREMENTS["apt"].items()
				   if shutil.which(exe) is None]
	if verbose:
		if missing_pip or missing_apt:
			lines = []
			if missing_pip:
				lines.append(f"  {sys.executable} -m pip install {' '.join(missing_pip)}")
			if missing_apt:
				lines.append(f"  sudo apt-get install -y {' '.join(missing_apt)}")
			print(Panel("[yellow]Missing requirements.\n"
						"Run [bold]install_requirements()[/bold], or by hand:\n"
						+ "\n".join(lines) +
						"\nSections that need them will be recorded as unavailable.",
						title="requirements"))
		else:
			print("[green]Requirements present.")
	return missing_pip, missing_apt


def install_requirements():
	"""Install what REQUIREMENTS declares, then disable the services it lists.

	Explicit by design: this changes the system, so it never runs implicitly.
	No reboot is needed -- pip, apt and `systemctl --now` all take effect
	immediately. apt uses `sudo -n`, so it fails fast instead of hanging if
	sudo wants a password.
	"""
	ok = True
	if REQUIREMENTS["pip"]:
		dists = " ".join(REQUIREMENTS["pip"])
		print(f"pip: {dists}")
		rc, out = _run(f'"{sys.executable}" -m pip install {dists}', timeout=900)
		if rc != 0:
			print(Panel(f"[red]pip failed (rc={rc}).\n{out[-600:]}", title="install"))
			ok = False

	pkgs = " ".join(REQUIREMENTS["apt"])
	print(f"apt: {pkgs}")
	rc, out = _run(f"sudo -n apt-get install -y {pkgs}", timeout=900)
	if rc != 0:
		## Stale package lists are the usual cause; refresh once and retry.
		print("[yellow]apt failed; refreshing package lists and retrying...")
		_run("sudo -n apt-get update", timeout=900)
		rc, out = _run(f"sudo -n apt-get install -y {pkgs}", timeout=900)
	if rc != 0:
		print(Panel(f"[red]apt failed (rc={rc}).\n{out[-800:]}", title="install"))
		ok = False

	for svc in REQUIREMENTS["disable_services"]:
		_run(f"sudo -n systemctl disable --now {svc}", timeout=60)
		print(f"  {svc}: {_run(f'systemctl is-active {svc}', timeout=10)[1].strip()}")

	mp, ma = check_requirements(verbose=False)
	if mp or ma:
		print(f"[red]Still missing: {mp + ma}")
		return False
	print("[green]Requirements installed.")
	return ok


## ==========================================================================
##  Experiment
## ==========================================================================

def populate_exp():
	exp = Experiment.current
	## SSD workload: one real 10-minute split per file, held until the end.
	exp.attribs["file_gb"] = 9.45
	exp.attribs["n_files"] = 20                 # ~189 GB: past the SLC cache
	exp.attribs["chunk_mb"] = 64
	## "flat_out" measures capacity and the worst case; "paced" writes at the
	## acquisition rate, which leaves the drive idle time to garbage-collect --
	## closer to reality, and 189 GB at 15.7 MB/s takes ~3.4 h.
	exp.attribs["mode"] = "flat_out"
	exp.attribs["paced_mb_s"] = 15.7
	exp.attribs["required_mb_s"] = 15.7
	## Never leave the SSD fuller than this during the workload.
	exp.attribs["min_free_fraction"] = 0.15
	## SD card: small and bounded, never more than this fraction of free space.
	exp.attribs["sd_write_gb"] = 1.0
	exp.attribs["sd_max_free_fraction"] = 0.10
	exp.attribs["telemetry_period_s"] = 1.0
	exp.attribs["idle_before_smart_s"] = 30
	exp.attribs["tandh_sampling_period_minutes"] = 5
	exp.attribs["sync_files"] = False
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["storage_health"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("devices",
		monitors=["role", "disk", "kind", "model", "transport", "bridge",
				  "fstype", "mountpoint"],
		measurements=["size_gb", "used_pct"])
	exp.new_measurementstream("smart",
		monitors=["phase", "disk", "health"],
		measurements=["pct_used", "power_on_h", "realloc", "pending",
					  "crc_errors", "cmd_timeout", "lbas_written", "temp_c"])
	exp.new_measurementstream("files",
		monitors=["disk", "n"],
		measurements=["gb", "seconds", "mean_mb_s", "chunk_ms_p50",
					  "chunk_ms_p99", "chunk_ms_max", "chunks_over_1s",
					  "chunks_over_5s", "fill_pct_after"])
	exp.new_measurementstream("verify",
		monitors=["disk", "n"],
		measurements=["read_mb_s", "chunks_ok", "chunks_bad"])

	populate_exp()
	check_requirements()

	os.makedirs("protocols", exist_ok=True)
	for src in ("experiments/masterprotocols/masterprotocol_June26.md",):
		try:
			Protocol(src).write(os.path.join("protocols", os.path.basename(src)))
		except Exception as e:
			print(Panel(f"[red]Protocol not loaded: {src}\n{e}", title="protocol"))


## ==========================================================================
##  Shell
## ==========================================================================

def _run(cmd, timeout=60):
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return None, f"<timed out after {timeout}s>"
	except Exception as e:
		return None, f"<{type(e).__name__}: {e}>"


def _sh(cmd, timeout=60):
	return _run(cmd, timeout)[1]


## ==========================================================================
##  Test-file bookkeeping -- deleted on every exit path
## ==========================================================================

global TEST_DIRS
TEST_DIRS = []


def _delete_test_dirs(*_a):
	"""Remove every test directory. Idempotent; safe from any handler."""
	global TEST_DIRS
	for d in list(TEST_DIRS):
		try:
			if os.path.isdir(d):
				shutil.rmtree(d)
				print(f"  [cleanup] removed {d}")
		except Exception as e:
			print(f"  [cleanup] FAILED to remove {d}: {e}", file=sys.stderr)
	TEST_DIRS = []


atexit.register(_delete_test_dirs)


def _on_signal(signum, frame):
	_delete_test_dirs()
	raise KeyboardInterrupt


for _sig in (signal.SIGTERM, signal.SIGHUP):
	try:
		signal.signal(_sig, _on_signal)
	except Exception:
		pass


def _test_dir_on(dev):
	"""A writable directory guaranteed to be ON this device.

	Checked by st_dev rather than assumed from the path: `/` is not writable
	by the scope user, $HOME may or may not be on the SD card, and writing the
	test to the wrong device would silently characterise the wrong drive.
	"""
	try:
		target = os.stat(dev["mountpoint"]).st_dev
	except Exception:
		return None
	for base in (dev["mountpoint"], os.path.expanduser("~"), "/var/tmp", "/tmp"):
		try:
			if os.stat(base).st_dev != target or not os.access(base, os.W_OK):
				continue
			d = os.path.join(base, f".ts_storage_test_{os.getpid()}")
			os.makedirs(d, exist_ok=True)
			TEST_DIRS.append(d)
			return d
		except Exception:
			continue
	return None


## ==========================================================================
##  Device discovery and static characterisation
## ==========================================================================

def resolve_device(path, role):
	"""path -> description of the filesystem and the disk beneath it."""
	info = {"role": role, "path": os.path.abspath(path)}
	out = _sh(f"findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS --target {shlex.quote(path)}")
	parts = out.split(None, 3)
	if len(parts) >= 3:
		info["mountpoint"], info["source"], info["fstype"] = parts[:3]
		info["options"] = parts[3].strip() if len(parts) > 3 else ""
	src = info.get("source", "")
	if src.startswith("/dev/"):
		info["part"] = src
		pk = _sh(f"lsblk -no pkname {shlex.quote(src)}").strip().splitlines()
		info["disk"] = f"/dev/{pk[0].strip()}" if pk and pk[0].strip() else src
	name = os.path.basename(info.get("disk", ""))
	info["kind"] = "sd" if name.startswith("mmcblk") else "ssd"
	return info


def identity(dev):
	"""Model/size/transport, and for an SD card its CID fields from sysfs --
	SD cards have no SMART, so this is most of what can be known about one."""
	name = os.path.basename(dev.get("disk", ""))
	ident = {}
	row = _sh(f"lsblk -dno SIZE,MODEL,TRAN,SERIAL /dev/{name}").split(None, 3)
	if row:
		ident["size"] = row[0]
		ident["transport"] = row[2] if len(row) > 2 else ""
	ident["model"] = _sh(f"lsblk -dno MODEL /dev/{name}").strip()
	if dev["kind"] == "sd":
		base = f"/sys/block/{name}/device"
		for f in ("name", "manfid", "oemid", "date", "serial", "fwrev", "hwrev",
				  "type", "erase_size", "preferred_erase_size", "life_time"):
			v = _sh(f"cat {base}/{f} 2>/dev/null").strip()
			if v:
				ident[f"sd_{f}"] = v
		ident["model"] = ident.get("sd_name", ident["model"])
		ident["transport"] = "mmc"
	else:
		ident.update(usb_topology(dev.get("disk", "")))
	return ident


def usb_topology(disk):
	"""Bridge ID and the driver actually bound to it -- read from the system,
	not inferred from cmdline.txt, which on this fleet names a bridge that is
	not attached to any scope."""
	out = {}
	name = os.path.basename(disk)
	syspath = _sh(f"readlink -f /sys/block/{name} 2>/dev/null").strip()
	drv = _sh(f"readlink -f /sys/block/{name}/device/../../../driver 2>/dev/null")
	out["driver"] = "uas" if "uas" in syspath + drv else "usb-storage"
	m = re.search(r"/(\d+-[\d.]+)/\d+-[\d.]+:", syspath)
	if m:
		dev = m.group(1)
		vid = _sh(f"cat /sys/bus/usb/devices/{dev}/idVendor 2>/dev/null").strip()
		pid = _sh(f"cat /sys/bus/usb/devices/{dev}/idProduct 2>/dev/null").strip()
		prod = _sh(f"cat /sys/bus/usb/devices/{dev}/product 2>/dev/null").strip()
		if vid and pid:
			out["bridge"] = f"{vid}:{pid}"
			out["bridge_product"] = prod
	out["quirks"] = " ".join(re.findall(r"usb-storage\.quirks=\S+",
										_sh("cat /proc/cmdline"))) or ""
	return out


STATIC = [
	("df",             "df -hP {mp}"),
	("df_inodes",      "df -iP {mp}"),
	("lsblk",          "lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TRAN,MODEL,SERIAL,REV {disk}"),
	("lsblk_discard",  "lsblk --discard {disk}"),
	("partitions",     "sudo -n parted -s {disk} unit s print 2>&1"),
	("tune2fs",        "sudo -n tune2fs -l {part} 2>&1"),
	("frag_score",     "sudo -n e4defrag -c {mp} 2>&1 | tail -15"),
	("queue",          "for f in scheduler rotational nr_requests read_ahead_kb "
					   "discard_max_bytes discard_granularity max_sectors_kb "
					   "write_cache; do printf '%-22s ' $f; "
					   "cat /sys/block/{name}/queue/$f 2>/dev/null || echo -; done"),
	("provisioning",   "for f in /sys/class/scsi_disk/*/provisioning_mode; do "
					   "printf '%s = ' $f; cat $f; done 2>/dev/null"),
	("mount",          "findmnt --target {mp} -o TARGET,SOURCE,FSTYPE,OPTIONS"),
	("fstrim_timer",   "systemctl status fstrim.timer --no-pager 2>&1 | head -12"),
]


def static_collect(dev, outdir):
	name = os.path.basename(dev.get("disk", ""))
	fmt = {"mp": shlex.quote(dev.get("mountpoint", "/")), "disk": dev.get("disk", ""),
		   "part": dev.get("part", ""), "name": name}
	res = {}
	d = os.path.join(outdir, "raw", name)
	os.makedirs(d, exist_ok=True)
	for slug, tmpl in STATIC:
		cmd = tmpl.format(**fmt)
		rc, text = _run(cmd, timeout=120)
		res[slug] = text
		with open(os.path.join(d, f"{slug}.txt"), "w") as f:
			f.write(f"$ {cmd}\n# rc={rc}\n{'#' * 60}\n{text}")
	return res


## ==========================================================================
##  SMART  (SSD only, drive idle only)
## ==========================================================================

SMART_KEYS = [
	("pct_used",     r"Percentage Used:\s*(\d+)"),
	("power_on_h",   r"Power_On_Hours.*?(\d+)\s*$"),
	("realloc",      r"Reallocated_Sector_Ct.*?(\d+)\s*$"),
	("pending",      r"Current_Pending_Sector.*?(\d+)\s*$"),
	("crc_errors",   r"UDMA_CRC_Error_Count.*?(\d+)\s*$"),
	("cmd_timeout",  r"Command_Timeout.*?(\d+)\s*$"),
	("lbas_written", r"Total_LBAs_Written.*?(\d+)\s*$"),
	("temp_c",       r"Temperature_Celsius.*?(\d+)"),
]


def smart_read(dev, outdir, phase):
	"""SMART through a USB bridge needs an explicit device type, so try the
	ones these bridges may need. Returns {} if nothing usable came back."""
	if dev["kind"] != "ssd" or not shutil.which("smartctl"):
		return {}
	disk = dev["disk"]
	for t in ("", "-d sat", "-d sat,12", "-d sntasmedia", "-d usbjmicron", "-d scsi"):
		rc, out = _run(f"sudo -n smartctl {t} -a {shlex.quote(disk)}", timeout=60)
		if re.search(r"SMART overall-health|ID#|Percentage Used", out or ""):
			name = os.path.basename(disk)
			with open(os.path.join(outdir, "raw", name, f"smart_{phase}.txt"), "w") as f:
				f.write(f"# device type: {t or '(auto)'}\n{out}")
			attrs = {"device_type": t or "(auto)"}
			for k, pat in SMART_KEYS:
				m = re.search(pat, out, re.M)
				if m:
					attrs[k] = int(m.group(1))
			m = re.search(r"self-assessment test result:\s*(\S+)", out)
			attrs["health"] = m.group(1) if m else "?"
			return attrs
	return {}


## ==========================================================================
##  Telemetry -- 1 Hz, background thread
## ==========================================================================

global PHASE, _telemetry_stop
PHASE = "idle"
_telemetry_stop = threading.Event()


def _diskstats(name):
	try:
		with open("/proc/diskstats") as f:
			for line in f:
				p = line.split()
				if len(p) > 13 and p[2] == name:
					## sectors are 512 B; ms_doing_io and weighted ms per kernel docs
					return {"rd_sec": int(p[5]), "wr_sec": int(p[9]),
							"io_ms": int(p[12]), "wt_ms": int(p[13])}
	except Exception:
		pass
	return None


def _psi():
	out = {"some": -1.0, "full": -1.0}
	try:
		with open("/proc/pressure/io") as f:
			for line in f:
				m = re.match(r"(some|full) avg10=([\d.]+)", line)
				if m:
					out[m.group(1)] = float(m.group(2))
	except Exception:
		pass
	return out


def _meminfo_mb(*keys):
	out = {k: -1.0 for k in keys}
	try:
		with open("/proc/meminfo") as f:
			for line in f:
				k = line.split(":")[0]
				if k in out:
					out[k] = round(int(line.split()[1]) / 1024.0, 1)
	except Exception:
		pass
	return out


def _cpu_times():
	try:
		with open("/proc/stat") as f:
			p = f.readline().split()[1:]
		v = [int(x) for x in p]
		return sum(v), v[4]          # total, iowait
	except Exception:
		return None


def _soc_temp():
	try:
		with open("/sys/class/thermal/thermal_zone0/temp") as f:
			return round(int(f.read().strip()) / 1000.0, 1)
	except Exception:
		return -1.0


def telemetry_thread(devs, path, period):
	"""One row per device per tick. Long format, so any number of devices fits
	the same columns."""
	t0 = time.monotonic()
	prev = {d["name"]: _diskstats(d["name"]) for d in devs}
	prev_cpu = _cpu_times()
	prev_t = time.monotonic()
	with open(path, "w", newline="") as f:
		w = csv.writer(f)
		w.writerow(["wall", "elapsed_s", "phase", "disk", "write_mb_s", "read_mb_s",
					"util_pct", "avg_wait_ms", "psi_some", "psi_full", "dirty_mb",
					"writeback_mb", "iowait_pct", "soc_temp_c"])
		while not _telemetry_stop.wait(period):
			now = time.monotonic()
			dt = max(now - prev_t, 1e-3)
			psi = _psi()
			mem = _meminfo_mb("Dirty", "Writeback")
			cpu = _cpu_times()
			iow = -1.0
			if cpu and prev_cpu and cpu[0] > prev_cpu[0]:
				iow = round(100.0 * (cpu[1] - prev_cpu[1]) / (cpu[0] - prev_cpu[0]), 2)
			for d in devs:
				cur = _diskstats(d["name"])
				p = prev.get(d["name"])
				if cur and p:
					wr = (cur["wr_sec"] - p["wr_sec"]) * 512 / 1e6 / dt
					rd = (cur["rd_sec"] - p["rd_sec"]) * 512 / 1e6 / dt
					util = min(100.0, 100.0 * (cur["io_ms"] - p["io_ms"]) / (dt * 1000))
					wait = (cur["wt_ms"] - p["wt_ms"]) / max(dt, 1e-3) / 1000.0
				else:
					wr = rd = util = wait = -1.0
				w.writerow([round(time.time(), 3), round(now - t0, 2), PHASE, d["name"],
							round(wr, 2), round(rd, 2), round(util, 1), round(wait, 3),
							psi["some"], psi["full"], mem["Dirty"], mem["Writeback"],
							iow, _soc_temp()])
				prev[d["name"]] = cur
			f.flush()
			prev_cpu, prev_t = cpu, now


## ==========================================================================
##  Workload
## ==========================================================================

_POOL = None


def _buffer(i, chunk_bytes):
	"""Distinct content for every chunk without paying os.urandom per chunk.

	A small pool of random buffers is generated once and the chunk index is
	stamped into the first eight bytes, so no two chunks are identical -- a
	deduplicating or compressing controller cannot flatter the result -- while
	the cost stays near zero on a Pi 4, which has no crypto extensions to make
	per-chunk randomness or SHA-256 cheap.
	"""
	global _POOL
	if _POOL is None or len(_POOL[0]) != chunk_bytes:
		_POOL = [bytearray(os.urandom(chunk_bytes)) for _ in range(8)]
	b = _POOL[i % len(_POOL)]
	b[:8] = i.to_bytes(8, "little")
	return b


_sync = getattr(os, "fdatasync", os.fsync)


def write_file(path, gb, chunk_mb, seq0, paced_mb_s=None):
	"""Write one file chunk by chunk, syncing and timing each.

	Sync per chunk because the question is how long one write takes to reach
	the drive -- what the encoder's output thread experiences -- not how fast
	the page cache accepts data. Returns (latencies_ms, crcs, seconds).
	"""
	cb = chunk_mb << 20
	n = max(1, int(round(gb * 1024 / chunk_mb)))
	lat, crcs = [], []
	t_start = time.monotonic()
	fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	try:
		for i in range(n):
			buf = _buffer(seq0 + i, cb)
			t0 = time.monotonic()
			os.write(fd, buf)
			_sync(fd)
			lat.append((time.monotonic() - t0) * 1000.0)
			crcs.append(zlib.crc32(buf))
			if paced_mb_s:
				## Hold the average at the acquisition rate, so the drive gets
				## the idle time a real recording would give it.
				target = (i + 1) * chunk_mb / paced_mb_s
				lag = target - (time.monotonic() - t_start)
				if lag > 0:
					time.sleep(lag)
		## Drop this file from the page cache, or the read-back would come
		## from RAM and verify nothing about the drive.
		if hasattr(os, "posix_fadvise"):
			os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
	finally:
		os.close(fd)
	return lat, crcs, time.monotonic() - t_start


def verify_file(path, chunk_mb, crcs):
	"""Read back and check every chunk. A write that succeeds and reads back
	wrong is a worse fault than a slow one, and it is invisible otherwise."""
	cb = chunk_mb << 20
	ok = bad = 0
	t0 = time.monotonic()
	with open(path, "rb", buffering=0) as f:
		for want in crcs:
			got = f.read(cb)
			if zlib.crc32(got) == want and len(got) == cb:
				ok += 1
			else:
				bad += 1
	secs = time.monotonic() - t0
	return ok, bad, (len(crcs) * chunk_mb) / max(secs, 1e-6)


def _pct(xs, q):
	s = sorted(xs)
	return s[min(len(s) - 1, int(len(s) * q))] if s else 0.0


def _fill_pct(mp):
	u = shutil.disk_usage(mp)
	return round(100.0 * (u.total - u.free) / u.total, 1)


def plan_files(dev, a, usage):
	"""How many files, of what size, for this device. Pure -- unit-testable.

	SSD: up to n_files of file_gb, capped so the drive never drops below
	min_free_fraction free. SD: one small file, at most sd_max_free_fraction
	of what is free, skipped entirely below 100 MB.
	"""
	if dev["kind"] == "sd":
		gb = min(a["sd_write_gb"], usage.free * a["sd_max_free_fraction"] / 2**30)
		if gb < 0.1:
			return [], f"only {usage.free / 1e9:.2f} GB free on the SD card"
		return [(1, gb)], None
	budget = usage.free - usage.total * a["min_free_fraction"]
	n = min(a["n_files"], int(max(budget, 0) // (a["file_gb"] * 2**30)))
	if n <= 0:
		return [], f"not enough free space for even one {a['file_gb']} GB file"
	return [(i + 1, a["file_gb"]) for i in range(n)], None


def workload(dev, a):
	"""Run the workload appropriate to the device. Returns per-file results."""
	global PHASE
	name = os.path.basename(dev["disk"])
	d = _test_dir_on(dev)
	if d is None:
		print(f"[red]{name}: no writable directory on this device -- skipping writes.")
		return {"skipped": "no writable directory on device"}

	plan, why = plan_files(dev, a, shutil.disk_usage(dev["mountpoint"]))
	if not plan:
		print(f"[red]{name}: {why} -- skipping writes.")
		return {"skipped": why}
	if dev["kind"] == "ssd" and len(plan) < a["n_files"]:
		print(f"[yellow]{name}: capped at {len(plan)} files to keep "
			  f"{a['min_free_fraction']:.0%} free.")

	paced = a["paced_mb_s"] if a["mode"] == "paced" else None
	print(Panel(f"{name} ({dev['kind']}): {len(plan)} file(s) x "
				f"{plan[0][1]:.2f} GB in {d}\nmode: {a['mode']}",
				title="workload"))
	results, seq = [], 0
	written = []
	for n, gb in plan:
		path = os.path.join(d, f"split_{n:03d}.bin")
		PHASE = f"write_{name}_{n:03d}"
		lat, crcs, secs = write_file(path, gb, a["chunk_mb"], seq, paced)
		seq += len(crcs)
		written.append((path, crcs))
		r = {"n": n, "gb": round(gb, 2), "seconds": round(secs, 1),
			 "mean_mb_s": round(len(crcs) * a["chunk_mb"] / secs, 1),
			 "chunk_ms_p50": round(_pct(lat, 0.50), 1),
			 "chunk_ms_p99": round(_pct(lat, 0.99), 1),
			 "chunk_ms_max": round(max(lat), 1),
			 "chunks_over_1s": sum(1 for x in lat if x > 1000),
			 "chunks_over_5s": sum(1 for x in lat if x > 5000),
			 "fill_pct_after": _fill_pct(dev["mountpoint"])}
		results.append(r)
		try:
			Experiment.current.mstreams["files"](disk=name, **r).panel()
		except Exception as e:
			log.error(f"files stream: {e}")

	## Verify only after everything is written: by then the early files have
	## long left any cache, and the drive is at its fullest.
	for (path, crcs), r in zip(written, results):
		PHASE = f"verify_{name}_{r['n']:03d}"
		ok, bad, mb_s = verify_file(path, a["chunk_mb"], crcs)
		r.update({"read_mb_s": round(mb_s, 1), "chunks_ok": ok, "chunks_bad": bad})
		try:
			Experiment.current.mstreams["verify"](disk=name, n=r["n"],
				read_mb_s=r["read_mb_s"], chunks_ok=ok, chunks_bad=bad)
		except Exception as e:
			log.error(f"verify stream: {e}")
	PHASE = "idle"
	return {"files": results}


## ==========================================================================
##  Kernel message stream  (same pattern as intensity_continuous)
## ==========================================================================

global _dmesg_proc
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
			with open("kernel.log", errors="replace") as r:
				tail = r.read()[-400:]
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


## ==========================================================================
##  Findings
## ==========================================================================

def findings_for(dev, ident, static, before, after, wl, required):
	F = []

	if dev["kind"] == "ssd":
		if not before:
			F.append(("WARN", "SMART unavailable",
					  "smartctl missing, or the bridge does not pass SMART through."))
		else:
			if before.get("health") not in ("PASSED", "?"):
				F.append(("CRITICAL", f"SMART health {before['health']}", ""))
			for k, lvl, why in (("realloc", "CRITICAL", "failing NAND"),
								("pending", "CRITICAL", "sectors awaiting reallocation"),
								("crc_errors", "WARN", "link CRC errors: cable or bridge, not NAND"),
								("cmd_timeout", "WARN", "drive failed to answer in time")):
				if before.get(k):
					F.append((lvl, f"{k} = {before[k]}", why))
				if after and before.get(k) is not None and after.get(k, 0) > before[k]:
					F.append(("CRITICAL", f"{k} rose during the test "
							  f"({before[k]} -> {after[k]})", why))
			if after and before.get("lbas_written") is not None \
					and after.get("lbas_written") is not None:
				d = after["lbas_written"] - before["lbas_written"]
				F.append(("OK", f"Total_LBAs_Written advanced by {d}",
						  "Confirms the writes reached the drive."))

		bridge = (ident.get("bridge") or "").lower()
		qids = re.findall(r"([0-9a-f]{4}:[0-9a-f]{4}):", (ident.get("quirks") or "").lower())
		if qids and bridge and bridge not in qids:
			F.append(("WARN", f"usb-storage quirk is inert here ({', '.join(qids)})",
					  f"It targets a device that is not attached (bridge is {bridge}). "
					  f"Safe to remove from cmdline.txt; changes nothing for this drive."))

	disc = static.get("lsblk_discard", "").splitlines()
	if len(disc) > 1:
		hdr, row = disc[0].split(), disc[1].split()
		try:
			gi, mi = hdr.index("DISC-GRAN"), hdr.index("DISC-MAX")
			if row[gi] == "0B" and row[mi] == "0B":
				F.append(("WARN", f"Discard unavailable ({ident.get('bridge', dev['kind'])})",
						  "Every fstrim is a no-op on this device."))
		except (ValueError, IndexError):
			pass

	files = (wl or {}).get("files", [])
	if (wl or {}).get("skipped"):
		F.append(("WARN" if dev["kind"] == "ssd" else "CRITICAL",
				  f"Write test skipped: {wl['skipped']}", ""))
	if files:
		bad = sum(f.get("chunks_bad", 0) for f in files)
		if bad:
			F.append(("CRITICAL", f"{bad} chunk(s) read back WRONG",
					  "Silent corruption: the write reported success."))
		worst = min(f["mean_mb_s"] for f in files)
		first, last = files[0]["mean_mb_s"], files[-1]["mean_mb_s"]
		if worst / required < 3:
			F.append(("CRITICAL", f"Slowest file {worst} MB/s -- under 3x the "
					  f"{required} MB/s an acquisition needs", ""))
		if len(files) > 2 and last < 0.5 * first:
			F.append(("WARN", f"Throughput fell {first} -> {last} MB/s across the run",
					  "The pseudo-SLC cache ran out; the later figure is the "
					  "steady state an acquisition actually runs in."))
		s5 = sum(f["chunks_over_5s"] for f in files)
		s1 = sum(f["chunks_over_1s"] for f in files)
		if s5:
			F.append(("CRITICAL", f"{s5} write(s) over 5 s",
					  "Enough to back up the encoder's unbounded queue."))
		elif s1:
			F.append(("WARN", f"{s1} write(s) over 1 s", ""))
	order = {"CRITICAL": 0, "WARN": 1, "OK": 2}
	F.sort(key=lambda x: order.get(x[0], 9))
	return F


## ==========================================================================
##  Sensors
## ==========================================================================

def record_sensor():
	"""Scheduled job -- must never raise; ExpScheduler.loop has no try/except."""
	try:
		scope = ScopeAssembly.current
		tandh = Experiment.current.mstreams["tandh"]
		try:
			value = scope.tandh.read()
		except Exception:
			value = {"temp": 0, "humidity": 0}
		tandh(**value).panel()
	except Exception as e:
		log.error(f"record_sensor failed: {e}")


## ==========================================================================
##  Run
## ==========================================================================

def _acquisition_running():
	rc, out = _run("pgrep -af 'mjpeg_continuous|intensity_continuous|"
				   "mjpeg_sampling|light_perturbation|sampling_record' | "
				   "grep -v pgrep", timeout=5)
	return out.strip() if rc == 0 and out.strip() else ""


def start_acq_blocking():
	global exp, scope, PHASE
	exp = Experiment.current
	scope = ScopeAssembly.current
	a = exp.attribs

	busy = _acquisition_running()
	if busy:
		print(Panel(f"[red]An acquisition appears to be running:\n{busy}\n\n"
					f"Refusing: the write test would compete with it, and SMART "
					f"on a busy USB drive can hang the controller.", title="refused"))
		return

	exp.schedule.clear()
	record_sensor()
	exp.schedule.every(a["tandh_sampling_period_minutes"]).minutes \
		.until(timedelta(hours=12)).do(record_sensor)

	outdir = os.getcwd()
	targets = [resolve_device("/", "os_sd"),
			   resolve_device(exp.exp_dir, "exp_dir")]
	seen, devs = set(), []
	for t in targets:
		if t.get("disk") and t["disk"] not in seen:
			seen.add(t["disk"])
			t["name"] = os.path.basename(t["disk"])
			devs.append(t)
		elif t.get("disk"):
			print(f"[yellow]{t['role']} is on {t['disk']}, already covered.")

	start_kernel_log()
	_telemetry_stop.clear()
	tel = threading.Thread(target=telemetry_thread,
						   args=(devs, os.path.join(outdir, "telemetry.csv"),
								 a["telemetry_period_s"]), daemon=True)
	tel.start()

	report = {"started": str(datetime.datetime.now()), "devices": []}
	try:
		## Phase 1: who, and SMART at rest.
		info = {}
		for dev in devs:
			PHASE = f"static_{dev['name']}"
			ident = identity(dev)
			static = static_collect(dev, outdir)
			before = smart_read(dev, outdir, "before")
			info[dev["name"]] = (ident, static, before)
			exp.mstreams["devices"](role=dev["role"], disk=dev["disk"], kind=dev["kind"],
				model=ident.get("model", ""), transport=ident.get("transport", ""),
				bridge=ident.get("bridge", ""), fstype=dev.get("fstype", ""),
				mountpoint=dev.get("mountpoint", ""),
				size_gb=round(shutil.disk_usage(dev["mountpoint"]).total / 1e9, 1),
				used_pct=_fill_pct(dev["mountpoint"])).panel()
			if before:
				exp.mstreams["smart"](phase="before", disk=dev["disk"],
					health=before.get("health", "?"),
					**{k: before[k] for k, _ in SMART_KEYS if k in before})

		## Phase 2: the workload.
		wls = {dev["name"]: workload(dev, a) for dev in devs}

		## Phase 3: let the drives settle, then SMART again.
		PHASE = "idle_settle"
		time.sleep(a["idle_before_smart_s"])
		for dev in devs:
			PHASE = f"smart_after_{dev['name']}"
			after = smart_read(dev, outdir, "after")
			if after:
				exp.mstreams["smart"](phase="after", disk=dev["disk"],
					health=after.get("health", "?"),
					**{k: after[k] for k, _ in SMART_KEYS if k in after})
			ident, static, before = info[dev["name"]]
			F = findings_for(dev, ident, static, before, after, wls[dev["name"]],
							 a["required_mb_s"])
			report["devices"].append({"device": dev, "identity": ident,
									  "smart_before": before, "smart_after": after,
									  "workload": wls[dev["name"]],
									  "findings": [{"level": l, "title": t, "detail": d}
												   for l, t, d in F]})
	except KeyboardInterrupt:
		print("\n[yellow]Interrupted. Cleaning up...")
	finally:
		PHASE = "cleanup"
		_delete_test_dirs()                     # BEFORE anything is synced
		for dev in devs:
			mp = dev.get("mountpoint")
			report.setdefault("fstrim", {})[dev["name"]] = \
				_sh(f"sudo -n fstrim -v {shlex.quote(mp)} 2>&1", timeout=300).strip()
		_telemetry_stop.set()
		tel.join(timeout=5)
		stop_kernel_log()

	report["finished"] = str(datetime.datetime.now())
	with open("storage_health.json", "w") as f:
		json.dump(report, f, indent=2, default=str)
	_write_report(report)
	for d in report["devices"]:
		for fnd in d["findings"]:
			exp.log_event("storage_finding", attribs={"disk": d["device"]["disk"], **fnd})
	cleanup()


def _write_report(report):
	L = [f"# Storage health -- {os.uname().nodename}", "",
		 f"- **Started** {report['started']}", f"- **Finished** {report.get('finished')}", ""]
	for d in report["devices"]:
		dev, ident = d["device"], d["identity"]
		L += [f"## {dev['disk']} -- {dev['role']} ({dev['kind']})", "",
			  f"- **Model** {ident.get('model', '?')}  **Transport** "
			  f"{ident.get('transport', '?')}  **Bridge** {ident.get('bridge', '-')}",
			  f"- **Filesystem** {dev.get('source')} ({dev.get('fstype')}) on "
			  f"`{dev.get('mountpoint')}`", "", "### Findings", ""]
		L += [f"- **[{x['level']}] {x['title']}**{(' -- ' + x['detail']) if x['detail'] else ''}"
			  for x in d["findings"]] or ["- none"]
		files = (d["workload"] or {}).get("files", [])
		if files:
			L += ["", "### Files", "",
				  "| n | GB | MB/s | p50 ms | p99 ms | max ms | >1 s | read MB/s | bad | fill % |",
				  "|---|---|---|---|---|---|---|---|---|---|"]
			L += [f"| {f['n']} | {f['gb']} | {f['mean_mb_s']} | {f['chunk_ms_p50']} | "
				  f"{f['chunk_ms_p99']} | {f['chunk_ms_max']} | {f['chunks_over_1s']} | "
				  f"{f.get('read_mb_s', '-')} | {f.get('chunks_bad', '-')} | "
				  f"{f['fill_pct_after']} |" for f in files]
		L.append("")
	L += ["## fstrim", ""] + [f"- `{k}`: {v}" for k, v in report.get("fstrim", {}).items()]
	L += ["", "Raw command output in `raw/<disk>/`; 1 Hz telemetry in "
		  "`telemetry.csv`; kernel messages in `kernel.log`."]
	with open("REPORT.md", "w") as f:
		f.write("\n".join(L) + "\n")


def cleanup():
	"""Save, offload, stop the schedule. Does NOT close -- exp.close() joins
	the scheduler thread. Type exp.close() afterwards."""
	global exp
	exp = Experiment.current
	_delete_test_dirs()                         # belt and braces before sync
	exp.schedule.clear()
	exp.schedule.end_thread = True
	exp.__save__()
	try:
		print(exp.mstreams["files"].tabulate("disk", "n", "mean_mb_s",
											 "chunk_ms_p99", "chunks_over_1s"))
	except Exception:
		pass
	exp.sync_dir()
	exp.note("Storage health run complete; test files removed before sync.")
	print(Panel("[yellow]Done. The experiment is still OPEN -- type "
				"[bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel("install_requirements()   # once per scope\n"
				"create_exp() -> start_acq_blocking()\n\n"
				"Characterises the OS SD card and the experiment drive.",
				title="storage_health_statistics"))
	check_requirements()
