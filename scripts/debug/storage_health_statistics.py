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

Everything knowable about the health of the drive the experiments are written
to, in one run.

Answers one question: can this drive sustain a 13.5 h acquisition at 15.7 MB/s
without stalling, and is it degrading? It resolves the device backing a given
path (the experiment directory by default), interrogates it, then measures it.

    python3 scripts/debug/storage_health_statistics.py
    python3 scripts/debug/storage_health_statistics.py --path ~/ssd --write-gb 8

Do NOT run this during an acquisition. The write benchmark competes for the
same drive, and querying SMART on a busy USB-attached drive has been reported
to hang the USB controller on a Pi 4.

The benchmark writes a temporary file and ALWAYS removes it -- on success, on
error, on Ctrl-C and on SIGTERM. The path is printed before it is created so a
stray file can be found by hand if the machine dies mid-test.

Why per-chunk latency and not just throughput
---------------------------------------------
A mean of "213 MB/s" hides the thing that actually breaks a recording. The
encoder's output thread blocks on one write; if a single write stalls for
seconds the frame queue backs up and memory grows. So each chunk is timed
individually and the distribution is reported. The tail is the measurement;
the mean is context.

No framework imports -- standard library only, like collect_diagnostics.py, so
this runs regardless of the state of the rest of the installation.
"""

import argparse
import atexit
import json
import os
import re
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import time

VERSION = "1.0"

## fdatasync skips the metadata flush, which is what we want per chunk -- but
## it is Linux-only, so fall back to fsync elsewhere. The Pi gets fdatasync;
## a laptop can still run the benchmark for testing.
_sync = getattr(os, "fdatasync", os.fsync)

## Removed by every exit path. Module-level so the atexit and signal handlers
## can see it even if main() never returns.
TESTFILE = None


def _cleanup_testfile(*_a):
	global TESTFILE
	if TESTFILE and os.path.exists(TESTFILE):
		try:
			os.remove(TESTFILE)
			print(f"  [cleanup] removed {TESTFILE}")
		except Exception as e:
			print(f"  [cleanup] FAILED to remove {TESTFILE}: {e}", file=sys.stderr)
	TESTFILE = None


atexit.register(_cleanup_testfile)
for _sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
	try:
		signal.signal(_sig, lambda s, f: (_cleanup_testfile(), sys.exit(130)))
	except Exception:
		pass


def run(cmd, timeout=60):
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return None, f"<timed out after {timeout}s>"
	except Exception as e:
		return None, f"<{type(e).__name__}: {e}>"


def sh(cmd, timeout=60):
	return run(cmd, timeout)[1]


## ---------------------------------------------------------------------------
##  Identify the device behind a path
## ---------------------------------------------------------------------------

def resolve_device(path):
	"""path -> {mountpoint, source, fstype, options, part, disk}.

	The partition is what the filesystem sits on; the parent disk is what SMART
	and the queue tunables live under. Both are needed and they are not the
	same thing.
	"""
	info = {"path": os.path.abspath(path)}
	out = sh(f"findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS --target {shlex.quote(path)}")
	parts = out.split(None, 3)
	if len(parts) >= 3:
		info["mountpoint"], info["source"], info["fstype"] = parts[:3]
		info["options"] = parts[3].strip() if len(parts) > 3 else ""
	src = info.get("source", "")
	if src.startswith("/dev/"):
		info["part"] = src
		## pkname gives the parent of a partition; for a whole disk it is empty.
		pk = sh(f"lsblk -no pkname {shlex.quote(src)}").strip().splitlines()
		info["disk"] = f"/dev/{pk[0].strip()}" if pk and pk[0].strip() else src
	return info


def usb_topology(disk):
	"""Bridge identity and whether it is running UAS or the slower BOT mode.

	This matters more than it looks: the usb-storage quirk `:u` disables UAS,
	and in BOT mode the bridge does not translate UNMAP -- which is a candidate
	explanation for discard being unavailable on most of the fleet.
	"""
	out = {}
	name = os.path.basename(disk)
	syspath = sh(f"readlink -f /sys/block/{name} 2>/dev/null").strip()
	out["sysfs"] = syspath
	out["driver"] = "uas" if "/uas/" in syspath or ":uas" in sh(
		f"ls -l /sys/block/{name}/device/driver 2>/dev/null") else "usb-storage (BOT)"
	m = re.search(r"usb[0-9]+/([0-9.-]+)/", syspath)
	if m:
		dev = m.group(1).split("/")[0]
		vid = sh(f"cat /sys/bus/usb/devices/{dev}/idVendor 2>/dev/null").strip()
		pid = sh(f"cat /sys/bus/usb/devices/{dev}/idProduct 2>/dev/null").strip()
		if vid and pid:
			out["bridge"] = f"{vid}:{pid}"
	out["quirks"] = " ".join(re.findall(r"usb-storage\.quirks=\S+",
										sh("cat /proc/cmdline"))) or "(none)"
	return out


def smart(disk):
	"""SMART, trying the device types a USB bridge may need.

	A plain `smartctl -a` usually fails through a USB enclosure: the bridge has
	to translate ATA commands, and smartctl has to be told how. The chain below
	covers the JMicron and ASMedia bridges in use here.
	"""
	attempts = ["", "-d sat", "-d sat,12", "-d usbjmicron", "-d sntasmedia", "-d scsi"]
	for d in attempts:
		rc, out = run(f"smartctl {d} -a {shlex.quote(disk)}", timeout=60)
		if rc is not None and re.search(r"SMART overall-health|ID#|Percentage Used", out):
			return {"device_type": d or "(auto)", "ok": True, "raw": out}
	return {"device_type": None, "ok": False,
			"raw": out if 'out' in dir() else "",
			"note": "SMART unavailable. Install smartmontools, and note that a "
					"bridge in BOT mode (usb-storage quirk ':u') often cannot "
					"pass SMART through at all."}


SMART_KEYS = [
	("Percentage Used", r"Percentage Used:\s*(\d+)"),
	("Power_On_Hours", r"Power_On_Hours.*?(\d+)\s*$"),
	("Reallocated_Sector_Ct", r"Reallocated_Sector_Ct.*?(\d+)\s*$"),
	("Current_Pending_Sector", r"Current_Pending_Sector.*?(\d+)\s*$"),
	("UDMA_CRC_Error_Count", r"UDMA_CRC_Error_Count.*?(\d+)\s*$"),
	("Command_Timeout", r"Command_Timeout.*?(\d+)\s*$"),
	("Wear_Leveling_Count", r"Wear_Leveling_Count.*?(\d+)\s*$"),
	("Total_LBAs_Written", r"Total_LBAs_Written.*?(\d+)\s*$"),
	("Temperature_Celsius", r"Temperature_Celsius.*?(\d+)"),
]


def smart_attrs(raw):
	found = {}
	for label, pat in SMART_KEYS:
		m = re.search(pat, raw, re.M)
		if m:
			found[label] = int(m.group(1))
	m = re.search(r"SMART overall-health self-assessment test result:\s*(\S+)", raw)
	if m:
		found["overall_health"] = m.group(1)
	return found


## ---------------------------------------------------------------------------
##  Write benchmark
## ---------------------------------------------------------------------------

def write_benchmark(target_dir, total_gb, chunk_mb=64, required_mb_s=15.7):
	"""Sequential write, timing every chunk separately.

	fdatasync after each chunk rather than once at the end, because the
	question is not how fast the page cache accepts data -- it is how long a
	single write takes to reach the drive. That is what the encoder's output
	thread experiences, and a single multi-second chunk is what backs its
	queue up.
	"""
	global TESTFILE
	res = {"requested_gb": total_gb, "chunk_mb": chunk_mb}

	free = shutil.disk_usage(target_dir).free
	need = total_gb * (1 << 30) * 1.1
	if free < need:
		res["skipped"] = (f"only {free / 1e9:.1f} GB free, need ~{need / 1e9:.1f} GB")
		return res

	TESTFILE = os.path.join(target_dir, f".storage_health_test_{os.getpid()}.tmp")
	print(f"  writing {total_gb} GB to {TESTFILE}")
	buf = os.urandom(chunk_mb << 20)        # not zeros: a compressing bridge would lie
	n = int(total_gb * 1024 / chunk_mb)
	lat = []
	t_start = time.monotonic()
	try:
		fd = os.open(TESTFILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		try:
			for i in range(n):
				t0 = time.monotonic()
				os.write(fd, buf)
				_sync(fd)
				lat.append((time.monotonic() - t0) * 1000.0)
				if i % 16 == 0:
					done = (i + 1) * chunk_mb / 1024.0
					print(f"    {done:5.1f} / {total_gb} GB", end="\r", flush=True)
		finally:
			os.close(fd)
		elapsed = time.monotonic() - t_start
		written_mb = n * chunk_mb
		lat.sort()
		res.update({
			"written_mb": written_mb,
			"elapsed_s": round(elapsed, 2),
			"mean_mb_s": round(written_mb / elapsed, 1),
			"chunk_ms_p50": round(lat[len(lat) // 2], 1),
			"chunk_ms_p99": round(lat[int(len(lat) * 0.99)], 1),
			"chunk_ms_max": round(lat[-1], 1),
			"chunks_over_1s": sum(1 for x in lat if x > 1000),
			"chunks_over_5s": sum(1 for x in lat if x > 5000),
			"worst_chunk_mb_s": round(chunk_mb / (lat[-1] / 1000.0), 1),
			"headroom_x": round((written_mb / elapsed) / required_mb_s, 1),
		})
		print(" " * 40, end="\r")

		## Read it back: a write that reports success and reads back wrong is a
		## different and worse fault than a slow one.
		t0 = time.monotonic()
		rc, _ = run(f"dd if={shlex.quote(TESTFILE)} of=/dev/null bs=64M "
					f"iflag=direct 2>/dev/null", timeout=600)
		if rc == 0:
			res["read_back_mb_s"] = round(written_mb / (time.monotonic() - t0), 1)
	except Exception as e:
		res["error"] = f"{type(e).__name__}: {e}"
	finally:
		_cleanup_testfile()
	return res


## ---------------------------------------------------------------------------
##  Static collection
## ---------------------------------------------------------------------------

def collect(dev, path):
	disk, part = dev.get("disk", ""), dev.get("part", "")
	name = os.path.basename(disk) if disk else ""
	q = f"/sys/block/{name}/queue"
	checks = [
		("findmnt",        f"findmnt --target {shlex.quote(path)} -o TARGET,SOURCE,FSTYPE,OPTIONS"),
		("df",             f"df -hP {shlex.quote(path)}"),
		("df_inodes",      f"df -iP {shlex.quote(path)}"),
		("lsblk",          f"lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TRAN,MODEL,SERIAL,REV {disk}"),
		("lsblk_discard",  f"lsblk --discard {disk}"),
		("partition_table", f"sudo -n parted -s {disk} unit s print 2>&1 || parted -s {disk} unit s print 2>&1"),
		("tune2fs",        f"sudo -n tune2fs -l {part} 2>&1 || tune2fs -l {part} 2>&1"),
		("frag_score",     f"sudo -n e4defrag -c {shlex.quote(path)} 2>&1 | tail -20"),
		("queue_tunables", f"for f in scheduler rotational nr_requests read_ahead_kb "
						   f"discard_max_bytes discard_granularity max_sectors_kb "
						   f"write_cache; do printf '%-22s ' $f; cat {q}/$f 2>/dev/null || echo '-'; done"),
		("provisioning",   "for f in /sys/class/scsi_disk/*/provisioning_mode; do "
						   "printf '%s = ' $f; cat $f; done 2>/dev/null"),
		("usb_tree",       "lsusb -t 2>&1"),
		("diskstats",      f"grep -E ' {name} | {os.path.basename(part)} ' /proc/diskstats"),
		("pressure_io",    "cat /proc/pressure/io 2>&1"),
		("meminfo_dirty",  "grep -E 'Dirty|Writeback' /proc/meminfo"),
		("vmstat_io",      "vmstat 1 3"),
		("mount_opts",     "mount | grep -E 'ext4|exfat|xfs|btrfs'"),
		("fstrim_timer",   "systemctl status fstrim.timer --no-pager 2>&1 | head -12"),
		("fstrim_last",    "journalctl -u fstrim.service --no-pager -n 10 2>/dev/null"),
		("dmesg_storage",  "dmesg -T 2>/dev/null | grep -iE 'EXT4-fs|I/O error|uas_|"
						   "usb [0-9-]+: reset|sd [a-z]:|timing out|task abort' | tail -60"),
		("smartd_state",   "systemctl is-enabled smartd 2>&1; systemctl is-active smartd 2>&1"),
	]
	out = {}
	for slug, cmd in checks:
		print(f"  [{slug}]", end="\r", flush=True)
		rc, text = run(cmd, timeout=90)
		out[slug] = {"cmd": cmd, "rc": rc, "out": text}
	print(" " * 40, end="\r")
	return out


## ---------------------------------------------------------------------------
##  Triage
## ---------------------------------------------------------------------------

def triage(dev, usb, sm, attrs, static, bench, required_mb_s):
	F = []
	g = lambda k: (static.get(k) or {}).get("out", "") or ""

	if not sm.get("ok"):
		F.append(("WARN", "SMART unavailable",
				  sm.get("note", "smartctl returned nothing usable.")))
	else:
		if attrs.get("overall_health") not in (None, "PASSED"):
			F.append(("CRITICAL", f"SMART health: {attrs['overall_health']}",
					  "The drive is reporting itself as failing."))
		for key, lvl, why in (
				("Reallocated_Sector_Ct", "CRITICAL", "Reallocated sectors: the NAND is failing."),
				("Current_Pending_Sector", "CRITICAL", "Pending sectors awaiting reallocation."),
				("UDMA_CRC_Error_Count", "WARN", "Link-level CRC errors -- a marginal cable or bridge, not the NAND."),
				("Command_Timeout", "WARN", "The drive failed to answer in time; this is what stalls a write.")):
			if attrs.get(key):
				F.append((lvl, f"{key} = {attrs[key]}", why))
		if attrs.get("Percentage Used", 0) >= 80:
			F.append(("WARN", f"Drive {attrs['Percentage Used']}% through rated life", ""))

	disc = g("lsblk_discard").splitlines()
	if len(disc) > 1 and re.search(r"\s0B\s+0B\s", disc[1]):
		F.append(("WARN", f"Discard unsupported via bridge {usb.get('bridge', '?')}",
				  "Every fstrim is a no-op. On this fleet (2026-11) the seven "
				  "scopes behind an ASMedia ASM1153 (174c:55aa) report no "
				  "discard, and the one behind a WD bridge (1058:266e) does -- "
				  "so it follows the bridge, not the quirk. Try "
				  "provisioning_mode=unmap; if that does not take, the "
				  "enclosure is the fix."))

	if "BOT" in usb.get("driver", ""):
		bridge = (usb.get("bridge") or "").lower()
		quirks = (usb.get("quirks") or "").lower()
		if bridge and bridge in quirks:
			F.append(("WARN", f"BOT mode forced by a quirk matching this bridge "
					  f"({bridge})",
					  "The ':u' quirk disables UAS for exactly the bridge that "
					  "is attached. That costs TRIM and usually SMART. If the "
					  "quirk was added for a cable or enclosure no longer in "
					  "use, removing it should restore both -- test one scope "
					  "under sustained write before changing the fleet."))
		elif bridge:
			F.append(("CRITICAL", f"BOT mode, but the quirk does NOT match this "
					  f"bridge ({bridge})",
					  f"quirks: {usb.get('quirks')}. The quirk targets a "
					  f"different device, so it is inert here and something "
					  f"else is keeping this drive out of UAS. Removing the "
					  f"quirk will not help this scope."))
		else:
			F.append(("WARN", "Drive is running in BOT mode, not UAS",
					  f"quirks: {usb.get('quirks')}. Costs TRIM and usually "
					  f"SMART. Bridge ID could not be read."))
	elif usb.get("driver"):
		F.append(("OK", f"Transport: {usb['driver']}", ""))

	qids = re.findall(r"([0-9a-f]{4}:[0-9a-f]{4}):", (usb.get("quirks") or "").lower())
	bridge = (usb.get("bridge") or "").lower()
	if qids and bridge and bridge not in qids:
		F.append(("WARN", f"usb-storage quirk is inert ({', '.join(qids)})",
				  f"It targets a device that is not attached; this drive's "
				  f"bridge is {bridge}. The quirk does nothing here and can be "
				  f"removed from cmdline.txt -- but doing so changes nothing "
				  f"about this drive's behaviour."))

	m = re.search(r"(\d+)%", g("df").splitlines()[-1] if g("df") else "")
	if m and int(m.group(1)) >= 85:
		F.append(("WARN", f"Filesystem {m.group(1)}% full",
				  "ext4 allocation degrades and SLC caches shrink near capacity."))

	if re.search(r"some avg10=([1-9]\d*\.\d+|\d+\.[1-9])", g("pressure_io")):
		F.append(("WARN", "I/O pressure is non-zero at rest",
				  g("pressure_io").strip()))

	n = len(re.findall(r"I/O error|uas_|reset (high|super)speed|task abort",
					   g("dmesg_storage"), re.I))
	if n:
		F.append(("CRITICAL", f"{n} storage error/reset line(s) in dmesg", ""))

	## Exact line match: `systemctl is-active` prints "inactive" when stopped,
	## and a substring test for "active" matches that too.
	if any(l.strip() == "active" for l in g("smartd_state").splitlines()):
		F.append(("WARN", "smartd is running",
				  "It polls the drive in the background. Reports exist of that "
				  "hanging a Pi's USB controller on a busy external drive. "
				  "Disable it: systemctl disable --now smartd"))

	if bench.get("skipped"):
		F.append(("WARN", "Write benchmark skipped", bench["skipped"]))
	elif bench.get("mean_mb_s"):
		if bench["headroom_x"] < 3:
			F.append(("CRITICAL", f"Only {bench['headroom_x']}x headroom over "
					  f"{required_mb_s} MB/s", "Too little margin to absorb a "
					  "garbage-collection pause during acquisition."))
		if bench.get("chunks_over_5s"):
			F.append(("CRITICAL", f"{bench['chunks_over_5s']} write(s) took over 5 s",
					  "A single stall like this backs up the encoder queue; the "
					  "queue is unbounded, so memory grows until the process dies."))
		elif bench.get("chunks_over_1s"):
			F.append(("WARN", f"{bench['chunks_over_1s']} write(s) took over 1 s",
					  f"worst chunk ran at {bench['worst_chunk_mb_s']} MB/s."))
	order = {"CRITICAL": 0, "WARN": 1, "OK": 2}
	F.sort(key=lambda x: order.get(x[0], 9))
	return F


## ---------------------------------------------------------------------------
##  Main
## ---------------------------------------------------------------------------

def main():
	ap = argparse.ArgumentParser(
		description="Collect every available storage-health statistic for the "
					"drive backing a path, then measure it.")
	ap.add_argument("--path", default=None,
					help="any path on the drive to test. Default: the experiment "
						 "directory if one is open, else the current directory.")
	ap.add_argument("--write-gb", type=float, default=8.0,
					help="size of the write benchmark (default 8). 0 disables it.")
	ap.add_argument("--chunk-mb", type=int, default=64)
	ap.add_argument("--required-mb-s", type=float, default=15.7,
					help="the rate an acquisition needs; headroom is reported "
						 "against this (default 15.7, measured).")
	ap.add_argument("--out", default="storage_health")
	args = ap.parse_args()

	path = args.path or os.environ.get("TS_EXP_DIR") or os.getcwd()
	path = os.path.abspath(os.path.expanduser(path))
	if not os.path.isdir(path):
		print(f"not a directory: {path}", file=sys.stderr)
		return 2

	stamp = time.strftime("%Y_%m_%d__%Hhh_%Mmm_%Ss")
	host = os.uname().nodename
	root = os.path.abspath(os.path.join(os.path.expanduser(args.out),
										f"storage_{host}__{stamp}"))
	os.makedirs(root, exist_ok=True)

	print(f"Storage health for {path}")
	dev = resolve_device(path)
	print(f"  filesystem : {dev.get('source','?')} ({dev.get('fstype','?')}) "
		  f"on {dev.get('mountpoint','?')}")
	print(f"  disk       : {dev.get('disk','?')}")
	usb = usb_topology(dev.get("disk", "")) if dev.get("disk") else {}
	if usb:
		print(f"  transport  : {usb.get('driver','?')}  bridge {usb.get('bridge','?')}")

	print("Collecting static state...")
	static = collect(dev, path)

	print("Reading SMART...")
	sm = smart(dev.get("disk", "")) if dev.get("disk") else {"ok": False}
	attrs = smart_attrs(sm.get("raw", "")) if sm.get("ok") else {}
	if attrs:
		print("  " + ", ".join(f"{k}={v}" for k, v in attrs.items()))

	bench = {}
	if args.write_gb > 0:
		print(f"Write benchmark ({args.write_gb} GB, {args.chunk_mb} MB chunks, "
			  f"fdatasync per chunk)...")
		bench = write_benchmark(dev.get("mountpoint") or path, args.write_gb,
								args.chunk_mb, args.required_mb_s)
		if bench.get("mean_mb_s"):
			print(f"  {bench['mean_mb_s']} MB/s mean | "
				  f"chunk p50 {bench['chunk_ms_p50']} ms, "
				  f"p99 {bench['chunk_ms_p99']} ms, max {bench['chunk_ms_max']} ms | "
				  f"{bench['headroom_x']}x headroom")

	findings = triage(dev, usb, sm, attrs, static, bench, args.required_mb_s)

	raw = os.path.join(root, "raw")
	os.makedirs(raw, exist_ok=True)
	for slug, r in static.items():
		with open(os.path.join(raw, f"{slug}.txt"), "w") as f:
			f.write(f"$ {r['cmd']}\n# rc={r['rc']}\n{'#' * 60}\n{r['out']}")
	if sm.get("raw"):
		with open(os.path.join(raw, "smartctl.txt"), "w") as f:
			f.write(sm["raw"])

	report = {"version": VERSION, "host": host, "stamp": stamp, "path": path,
			  "device": dev, "usb": usb,
			  "smart": {"available": sm.get("ok"), "device_type": sm.get("device_type"),
						"attributes": attrs},
			  "benchmark": bench,
			  "findings": [{"level": l, "title": t, "detail": d} for l, t, d in findings]}
	with open(os.path.join(root, "storage_health.json"), "w") as f:
		json.dump(report, f, indent=2)

	with open(os.path.join(root, "REPORT.md"), "w") as f:
		f.write(f"# Storage health -- {host}\n\n- **Path** `{path}`\n"
				f"- **Filesystem** `{dev.get('source')}` ({dev.get('fstype')}) "
				f"on `{dev.get('mountpoint')}`\n"
				f"- **Disk** `{dev.get('disk')}`\n"
				f"- **Transport** {usb.get('driver','?')}, bridge "
				f"{usb.get('bridge','?')}, quirks `{usb.get('quirks','?')}`\n"
				f"- **Collected** {stamp}\n\n## Findings\n\n")
		if not findings:
			f.write("No findings.\n")
		for l, t, d in findings:
			f.write(f"- **[{l}] {t}**{(' -- ' + d) if d else ''}\n")
		if attrs:
			f.write("\n## SMART\n\n| Attribute | Value |\n|---|---|\n")
			for k, v in attrs.items():
				f.write(f"| {k} | {v} |\n")
		if bench:
			f.write("\n## Write benchmark\n\n| Metric | Value |\n|---|---|\n")
			for k, v in bench.items():
				f.write(f"| {k} | {v} |\n")
		f.write(f"\nRaw command output in `raw/`.\n")

	print()
	for l, t, d in findings:
		print(f"  [{l:8}] {t}")
	if not findings:
		print("  no findings")
	print(f"\nReport : {os.path.join(root, 'REPORT.md')}")
	print(f"JSON   : {os.path.join(root, 'storage_health.json')}")
	if TESTFILE:
		print(f"[warn] test file may remain: {TESTFILE}", file=sys.stderr)
	return 0


if __name__ == "__main__":
	sys.exit(main())
