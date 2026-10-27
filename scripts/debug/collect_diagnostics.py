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
# | Date      : October 2026                                                   |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+

"""
AI Generated -- new file, Claude (Anthropic), 2026-10.

Collect Raspberry Pi system diagnostics into one bundle.

Run this ON THE SCOPE, after something went wrong -- a run that stopped, an
experiment that would not sync, a camera that would not open. It captures the
system-level evidence that is lost as soon as the machine is rebooted or the
journal rotates, writes a readable report, and tars the lot up for transfer.

    python3 scripts/debug/collect_diagnostics.py
    python3 scripts/debug/collect_diagnostics.py --exp-dir ~/data/M1__YB__... \\
                                                 --server slurmnas.igc.gulbenkian.pt

Output (under --out, default ~/diagnostics):

    diag_<scopeid-or-host>__<stamp>/
        REPORT.md          triage first, then every command with its output
        index.json         machine-readable: command, rc, duration, raw path
        raw/<slug>.txt     one file per command, untruncated
        config/            the scope's config, secrets redacted
    diag_<scopeid-or-host>__<stamp>.tar.gz

REPORT.md leads with a TRIAGE section: a short list of findings for the
problems this lab actually hits -- under-voltage, thermal throttling, ethernet
link drops, camera frontend timeouts, OOM kills, filesystem errors, a disk
close to full, TRIM that was never working. Each finding names the raw file it
came from, so nothing has to be taken on trust.

Design notes
------------
* **No framework imports.** Nothing from expframework/, hive/ or core/. This
  has to run when the framework is exactly what is broken, and on a scope where
  the repo is in an unknown state. Standard library only.
* **Nothing is fatal.** A missing binary, a denied permission or a command that
  hangs is recorded as such and the collection continues. A partial bundle is
  worth far more than a traceback.
* **Every command is timed out.** `ping`, `rclone` and `smartctl` can all block
  indefinitely against dead hardware or a dead link.
* **Configs are copied verbatim**, into `config/`, because almost every sync or
  device fault is explained by them. That includes the NetworkManager keyfiles,
  so the bundle contains the file-server password and the Wi-Fi PSK. It is an
  internal artefact; treat it as one. `--redact` replaces those values with
  whether they were set, for a bundle that has to leave the lab.
"""

import argparse
import datetime
import glob
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile

VERSION = "1.0"

## Commands needing elevated privileges on some images (kernel.dmesg_restrict,
## journal ACLs). Tried unprivileged first; `sudo -n` only as a fallback, so an
## unattended run can never block on a password prompt.
SUDO_FALLBACK = True


## ---------------------------------------------------------------------------
##  Check table
## ---------------------------------------------------------------------------
## (slug, title, command, inline)
##   inline = how many lines to reproduce in REPORT.md. 0 means the raw file is
##   referenced but not inlined -- for dmesg and the journal, which are large
##   enough to swamp the report (and anything reading it).

GROUPS = [

 ("system", "System identity and boot history", [
	("uname",            "Kernel",                     "uname -a", 5),
	("os_release",       "OS release",                 "cat /etc/os-release", 20),
	("model",            "Board model",                "tr -d '\\0' < /proc/device-tree/model; echo", 3),
	("firmware",         "VideoCore firmware",         "vcgencmd version", 10),
	("uptime",           "Uptime and load",            "uptime", 5),
	("timedatectl",      "Clock and NTP sync",         "timedatectl", 15),
	("meminfo",          "Memory",                     "free -h", 8),
	("cmdline",          "Kernel command line",        "cat /proc/cmdline", 3),
	("config_txt",       "Boot config",                "cat /boot/firmware/config.txt 2>/dev/null || cat /boot/config.txt", 60),
	("boots",            "Boot history",               "journalctl --list-boots --no-pager 2>/dev/null | tail -20", 25),
	("reboots",          "Reboot/shutdown record",     "last -x reboot shutdown 2>/dev/null | head -20", 22),
	("failed_units",     "Failed systemd units",       "systemctl --failed --no-pager", 25),
 ]),

 ("power", "Power supply and throttling", [
	("throttled",        "Throttle flags",             "vcgencmd get_throttled", 3),
	("volts_core",       "Core voltage",               "vcgencmd measure_volts core", 3),
	("volts_sdram",      "SDRAM voltage",              "vcgencmd measure_volts sdram_c", 3),
	("pmic",             "PMIC rails (Pi 5)",          "vcgencmd pmic_read_adc", 40),
	("dmesg_voltage",    "Kernel voltage messages",    "dmesg -T 2>/dev/null | grep -iE 'voltage|under-volt' | tail -50", 50),
 ]),

 ("thermal", "Temperature and clocks", [
	("temp",             "SoC temperature",            "vcgencmd measure_temp", 3),
	("thermal_zone",     "Thermal zone (millidegC)",   "cat /sys/class/thermal/thermal_zone0/temp", 3),
	("clock_arm",        "ARM clock",                  "vcgencmd measure_clock arm", 3),
 ]),

 ("storage", "Filesystems and the data drive", [
	("df",               "Free space",                 "df -hP", 25),
	("df_inodes",        "Free inodes",                "df -i", 25),
	("lsblk",            "Block devices",              "lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TRAN,MODEL", 25),
	("lsblk_discard",    "TRIM/discard support",       "lsblk --discard", 25),
	("mounts",           "Mounted filesystems",        "findmnt -t ext4,exfat,vfat,xfs,btrfs -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null || mount", 30),
	("fstrim_timer",     "fstrim timer",               "systemctl status fstrim.timer --no-pager 2>&1 | head -20", 20),
	("fstrim_last",      "Last fstrim run",            "journalctl -u fstrim.service --no-pager -n 20 2>/dev/null", 20),
	("smart",            "SMART attributes",           "for d in /dev/sd? /dev/nvme?n?; do [ -e \"$d\" ] && echo \"== $d\" && smartctl -A \"$d\" 2>&1; done", 50),
	("fstab",            "fstab",                      "cat /etc/fstab", 40),
	("mount_units",      "systemd mount/automount units",
	 "systemctl list-units --type=mount --type=automount --all --no-pager 2>&1 | head -30", 30),
	("mnt_dirs",         "Mountpoint dirs (ghost-mount check)",
	 'for p in /mnt/* /media/* /media/*/*; do [ -d "$p" ] || continue; '
	 'if mountpoint -q "$p" 2>/dev/null; then echo "MOUNTED      -      $p"; '
	 'else echo "NOT-MOUNTED  $(du -sh "$p" 2>/dev/null | cut -f1)  $p"; fi; done; '
	 'echo "== loose files directly in /mnt =="; '
	 'find /mnt -maxdepth 1 -type f 2>/dev/null | head -20', 30),
	("dmesg_storage",    "Kernel storage errors",      "dmesg -T 2>/dev/null | grep -iE 'EXT4-fs|I/O error|uas_|usb [0-9-]+: reset|sd [a-z]:|nvme' | tail -80", 60),
 ]),

 ("network", "Link, addressing and NetworkManager", [
	("nmcli_con",        "Connection profiles",        "nmcli -f NAME,DEVICE,AUTOCONNECT,AUTOCONNECT-PRIORITY con show", 30),
	("nmcli_dev",        "Device status",              "nmcli device status", 20),
	## FILENAME is the field that settles "my static IP does not survive a
	## reboot": a profile stored under /run is on tmpfs and is gone at boot.
	("nmcli_files",      "Where profiles are stored",  "nmcli -f NAME,UUID,TYPE,FILENAME con show", 30),
	("nm_keyfile_dir",   "NM profile directory",       "ls -la /etc/NetworkManager/system-connections/ /run/NetworkManager/system-connections/ 2>&1", 30),
	("ip_addr",          "Addresses",                  "ip -br addr", 20),
	("ip_route",         "Routes",                     "ip route", 20),
	("carrier",          "Link carrier state",         "for i in /sys/class/net/*/; do n=$(basename $i); [ \"$n\" = lo ] && continue; echo \"$n carrier=$(cat $i/carrier 2>/dev/null) operstate=$(cat $i/operstate 2>/dev/null)\"; done", 15),
	("ethtool",          "Ethernet link detail",       "ethtool eth0 2>&1 | head -30", 30),
	("wifi_link",        "Wi-Fi link",                 "iw dev wlan0 link 2>&1", 15),
	("link_stats",       "Interface error/drop counters", "ip -s link", 40),
	("ethtool_stats",    "PHY error counters",
	 "ethtool -S eth0 2>&1 | grep -iE 'err|crc|drop|collision|carrier' | head -30", 30),
	("ethtool_eee",      "Energy-Efficient Ethernet",   "ethtool --show-eee eth0 2>&1 | head -12", 12),
	("resolv",           "DNS configuration",          "cat /etc/resolv.conf", 15),
	("socket_summary",   "Socket summary",             "ss -s", 15),
	("nm_journal",       "NetworkManager this boot",   "journalctl -u NetworkManager -b --no-pager 2>/dev/null | tail -60", 60),
	("dmesg_net",        "Kernel link messages",       "dmesg -T 2>/dev/null | grep -iE 'eth0|genet|link is|link down|link up|wlan0|brcmfmac' | tail -80", 60),
 ]),

 ("sync", "Offload path (rclone to the file server)", [
	("rclone_version",   "rclone",                     "command -v rclone && rclone version 2>&1 | head -8", 12),
	("rclone_remotes",   "rclone remotes configured",  "rclone listremotes 2>&1", 10),
 ]),

 ("camera", "Camera stack", [
	("get_camera",       "Firmware camera detect",     "vcgencmd get_camera", 3),
	("list_cameras",     "libcamera enumeration",      "rpicam-hello --list-cameras 2>&1 || libcamera-hello --list-cameras 2>&1", 40),
	("video_devices",    "Video device nodes",         "ls -l /dev/video* /dev/media* 2>&1", 30),
	("v4l2",             "V4L2 devices",               "v4l2-ctl --list-devices 2>&1", 30),
	("cma",              "CMA allocation",             "vcgencmd get_mem cma 2>&1; grep -i cma /proc/meminfo", 10),
	("tuning_file",      "Scientific tuning file",     "ls -l /usr/share/libcamera/ipa/rpi/vc4/imx477_scientific.json 2>&1", 5),
	("rpi_apps_yaml",    "libcamera pipeline config",  "cat /usr/share/libcamera/pipeline/rpi/vc4/rpi_apps.yaml 2>&1", 40),
	("dmesg_camera",     "Kernel camera messages",     "dmesg -T 2>/dev/null | grep -iE 'imx|unicam|csi|rp1-cfe|vc_sm|cma alloc|i2c' | tail -100", 60),
	("journal_camera",   "libcamera errors (journal)", "journalctl -b --no-pager 2>/dev/null | grep -iE 'frontend has timed out|Dequeue timer|attached securely|vc_sm_cma|v4l2_m2m' | tail -60", 60),
 ]),

 ("processes", "Processes and memory pressure", [
	("ps",               "Top processes by memory",    "ps -eo pid,ppid,nlwp,pcpu,pmem,rss,etime,comm --sort=-rss 2>/dev/null | head -25", 25),
	("python_procs",     "Python processes",           "ps -eo pid,etime,pcpu,pmem,rss,args 2>/dev/null | grep -i [p]ython | head -20", 20),
	("dmesg_oom",        "OOM killer",                 "dmesg -T 2>/dev/null | grep -iE 'out of memory|killed process|oom-kill' | tail -40", 40),
 ]),

 ("kernel", "Full kernel ring buffer and journal (not inlined)", [
	("dmesg_full",       "Complete dmesg",             "dmesg -T", 0),
	("journal_this",     "Journal, this boot",         "journalctl -b --no-pager", 0),
	("journal_prev",     "Journal, previous boot",     "journalctl -b -1 --no-pager", 0),
 ]),
]


## ---------------------------------------------------------------------------
##  Running commands
## ---------------------------------------------------------------------------

def run(cmd, timeout=30):
	"""Run `cmd` through the shell. Never raises.

	Returns a dict with rc, stdout+stderr combined, seconds taken and how it
	was run. A non-zero rc is normal and informative here (a `grep` that
	matched nothing exits 1), so nothing is treated as an error except the
	collection itself failing.
	"""
	started = datetime.datetime.now()
	note = None
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		rc, out = p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired as e:
		partial = (e.stdout or b"").decode("utf-8", "replace")
		rc, out, note = None, partial, f"TIMED OUT after {timeout}s"
	except Exception as e:
		rc, out, note = None, "", f"{type(e).__name__}: {e}"

	## Permission-denied on dmesg/journalctl is common and silently produces an
	## empty bundle section. Retry once, non-interactively, so an unattended run
	## cannot block on a password prompt.
	if (SUDO_FALLBACK and shutil.which("sudo")
			and _looks_denied(out)
			and not cmd.lstrip().startswith("sudo")):
		try:
			p = subprocess.run(f"sudo -n {cmd}", shell=True, timeout=timeout,
							   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			if p.returncode == 0:
				rc, out, note = 0, p.stdout.decode("utf-8", "replace"), "ran via sudo -n"
			else:
				## Keep the ORIGINAL output. Only rc==0 is accepted, because
				## `sudo -n` without cached credentials exits 1 with "a password
				## is required" -- accepting that would overwrite the real result.
				note = "needs root; sudo -n unavailable (section may be empty)"
		except Exception:
			pass

	return {"cmd": cmd, "rc": rc, "out": out, "note": note,
			"seconds": round((datetime.datetime.now() - started).total_seconds(), 2)}


def _looks_denied(text):
	return bool(re.search(r"permission denied|operation not permitted|are you root",
						  text, re.I))


## ---------------------------------------------------------------------------
##  Triage
## ---------------------------------------------------------------------------
## Findings are (level, title, detail, slug). `slug` names the raw file the
## finding came from, so every line in the triage section is checkable.

THROTTLE_BITS = [
	(0,  "Under-voltage detected",            "CRITICAL", "right now"),
	(1,  "ARM frequency capped",              "WARN",     "right now"),
	(2,  "Currently throttled",               "WARN",     "right now"),
	(3,  "Soft temperature limit active",     "WARN",     "right now"),
	(16, "Under-voltage has occurred",        "CRITICAL", "since boot"),
	(17, "ARM frequency capping has occurred","WARN",     "since boot"),
	(18, "Throttling has occurred",           "WARN",     "since boot"),
	(19, "Soft temperature limit has occurred","WARN",    "since boot"),
]


def triage(results):
	"""Read the collected output and report on the failures this lab hits."""
	F = []
	def get(slug):
		return (results.get(slug) or {}).get("out", "") or ""

	## -- power -------------------------------------------------------------
	m = re.search(r"throttled=0x([0-9a-fA-F]+)", get("throttled"))
	if m:
		bits = int(m.group(1), 16)
		hits = [(lvl, f"{name} ({when})") for b, name, lvl, when in THROTTLE_BITS
				if bits & (1 << b)]
		if hits:
			for lvl, name in hits:
				F.append((lvl, name,
						  f"vcgencmd get_throttled = 0x{bits:x}. Check the PSU and "
						  f"the USB-C cable before suspecting software.", "throttled"))
		else:
			F.append(("OK", "No throttling or under-voltage flags",
					  f"vcgencmd get_throttled = 0x{bits:x}", "throttled"))
	else:
		F.append(("UNKNOWN", "Throttle flags unreadable",
				  "vcgencmd produced no parseable output.", "throttled"))

	n = _count(get("dmesg_voltage"), r"under-volt")
	if n:
		F.append(("CRITICAL", f"{n} under-voltage message(s) in dmesg",
				  "The kernel logged a supply dip. These correlate with SD/USB "
				  "corruption and spontaneous camera failures.", "dmesg_voltage"))

	## -- memory ------------------------------------------------------------
	n = _count(get("dmesg_oom"), r"killed process|out of memory")
	if n:
		F.append(("CRITICAL", f"{n} OOM-killer event(s)",
				  "A process was killed for memory. For an acquisition run this "
				  "is usually an encoder output thread that died, leaving its "
				  "frame queue to grow unbounded.", "dmesg_oom"))

	## -- storage -----------------------------------------------------------
	for line in get("df").splitlines()[1:]:
		## `df -hP` guarantees six columns: source, size, used, avail, use%,
		## mountpoint. Parsing positionally rather than by regex, because macOS
		## `df -h` also emits %iused and "the percent before the mountpoint" is
		## then the wrong column.
		parts = line.split(None, 5)
		if len(parts) < 6 or not parts[4].endswith("%"):
			continue
		try:
			pct = int(parts[4].rstrip("%"))
		except ValueError:
			continue
		src, mount = parts[0], parts[5].strip()
		## Pseudo filesystems sit at or near 100% by construction. Reporting
		## them was a guaranteed false CRITICAL on every machine, which would
		## have trained the reader to ignore the section.
		if src in ("devfs", "tmpfs", "devtmpfs", "overlay", "squashfs", "none"):
			continue
		if mount.startswith(("/dev", "/run", "/sys", "/proc", "/System/Volumes")):
			continue
		if pct >= 85:
			F.append(("CRITICAL" if pct >= 95 else "WARN",
					  f"{mount} is {pct}% full",
					  "Dynamic SLC cache shrinks sharply above ~80% fill, and a "
					  "full disk stops the experiment YAML being written.", "df"))

	disc = get("lsblk_discard").splitlines()
	if disc:
		## Column positions are read from the header rather than assumed:
		## lsblk emits NAME DISC-ALN DISC-GRAN DISC-MAX DISC-ZERO, so a fixed
		## index silently reads DISC-ALN and never fires.
		hdr = disc[0].split()
		gi = hdr.index("DISC-GRAN") if "DISC-GRAN" in hdr else None
		mi = hdr.index("DISC-MAX") if "DISC-MAX" in hdr else None
		if gi is not None and mi is not None:
			for line in disc[1:]:
				parts = line.split()
				if (len(parts) > max(gi, mi)
						and parts[gi] == "0B" and parts[mi] == "0B"):
					F.append(("WARN", f"{parts[0]} does not accept discards",
							  "DISC-GRAN and DISC-MAX are zero, so every fstrim "
							  "since deployment has been a no-op. On a USB "
							  "bridge, set provisioning_mode to unmap.",
							  "lsblk_discard"))

	## A directory under /mnt or /media that holds data but is NOT a mountpoint
	## means the writes went to the root filesystem instead of the drive that
	## should have been mounted there.
	for line in get("mnt_dirs").splitlines():
		if not line.startswith("NOT-MOUNTED"):
			continue
		parts = line.split()
		m = re.match(r"([\d.]+)([KMGT])", parts[1]) if len(parts) >= 3 else None
		if not m:
			continue
		nbytes = float(m.group(1)) * {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)]
		if nbytes >= 100e6:
			F.append(("CRITICAL",
					  f"{parts[-1]} holds {parts[1]} but is NOT a mountpoint",
					  "Data was written into a directory that should have had a "
					  "filesystem mounted on it, so it landed on the root "
					  "filesystem instead. This is how / fills while the drive "
					  "that should have received the data stays nearly empty.",
					  "mnt_dirs"))

	n = _count(get("dmesg_storage"), r"EXT4-fs error|I/O error|uas_eh|reset (high|super)speed")
	if n:
		F.append(("CRITICAL", f"{n} storage error/reset message(s)",
				  "Filesystem errors or USB resets under load. A USB-SATA bridge "
				  "that resets mid-write will stall the acquisition's output "
				  "thread.", "dmesg_storage"))

	## -- network -----------------------------------------------------------
	## "Link is Down" is what bcmgenet actually logs -- matching "link down"
	## never fired. One is the normal boot transition; repeats are the signal.
	n = _count(get("dmesg_net"), r"link is down|link is not ready|carrier lost")
	if n > 1:
		F.append(("WARN", f"{n} ethernet link-down event(s)",
				  "The link dropped repeatedly this boot. A drop during "
				  "sync_dir() leaves the experiment unsynced with no error in "
				  "the experiment log.", "dmesg_net"))
	elif n == 1:
		F.append(("OK", "One ethernet link-down event",
				  "A single transition, consistent with the normal bring-up at "
				  "boot.", "dmesg_net"))

	## A flapping or marginal PHY shows up here long before it shows up as a
	## failed sync. Zero counters on a healthy link.
	bad_counters = [l.strip() for l in get("ethtool_stats").splitlines()
					if re.search(r":\s*[1-9]\d*\s*$", l)]
	if bad_counters:
		F.append(("WARN", f"{len(bad_counters)} non-zero PHY error counter(s)",
				  "; ".join(bad_counters[:4]) + ". CRC or carrier errors mean a "
				  "marginal cable or port, not a configuration fault.",
				  "ethtool_stats"))

	## A network mount without nofail blocks boot; one without x-systemd
	## automount leaves a plain directory that writes fall into when the share
	## is unreachable -- the ghost mount.
	for line in get("fstab").splitlines():
		line = line.strip()
		if not line or line.startswith("#"):
			continue
		if re.search(r"\b(cifs|nfs4?|smb3?)\b", line) and "nofail" not in line:
			F.append(("WARN", "Network mount in fstab without nofail",
					  f"`{line[:70]}`. Without nofail a dead share delays boot, "
					  "and with no automount the mountpoint stays a plain "
					  "directory that writes land in.", "fstab"))

	carrier = get("carrier")
	for line in carrier.splitlines():
		m = re.match(r"(\S+)\s+carrier=(\S*)\s+operstate=(\S*)", line)
		if m and m.group(2) == "0":
			F.append(("WARN", f"{m.group(1)} has no carrier right now",
					  f"operstate={m.group(3)}. Nothing will sync over this "
					  f"interface.", "carrier"))

	## A profile under /run is volatile -- it does not survive a reboot, which
	## is the classic "the static IP will not stick" report.
	for line in get("nmcli_files").splitlines()[1:]:
		if "/run/" in line:
			F.append(("CRITICAL", f"Profile '{line.split()[0]}' is stored under /run",
					  "/run is tmpfs. This profile is lost on reboot, so the "
					  "setting appears to save and then vanishes. It belongs in "
					  "/etc/NetworkManager/system-connections/.", "nmcli_files"))

	if re.search(r"\bconnecting\b|\bunavailable\b|\bdisconnected\b", get("nmcli_dev"), re.I):
		F.append(("WARN", "A NetworkManager device is not connected",
				  "See the device status table.", "nmcli_dev"))

	## -- camera ------------------------------------------------------------
	n = _count(get("journal_camera"), r"frontend has timed out")
	if n:
		F.append(("CRITICAL", f"{n} libcamera frontend timeout(s)",
				  "libcamera stopped the streams and cancelled the outstanding "
				  "requests. Until the application calls stop()/start() the "
				  "camera delivers no further frames, which presents as a "
				  "recording that stops mid-split and then hangs.",
				  "journal_camera"))

	n = _count(get("journal_camera"), r"Dequeue timer")
	if n:
		F.append(("WARN", f"{n} dequeue-timer expiry message(s)",
				  "Frames stopped arriving for longer than the timeout. Usually "
				  "precedes a frontend timeout; often mechanical (CSI ribbon).",
				  "journal_camera"))

	n = _count(get("journal_camera") + get("dmesg_camera"), r"vc_sm_cma|cma alloc")
	if n:
		F.append(("WARN", f"{n} CMA allocation message(s)",
				  "Contiguous memory pressure. Consider lowering buffer_count or "
				  "raising the CMA reservation.", "dmesg_camera"))

	cam = get("list_cameras")
	if re.search(r"no cameras available", cam, re.I):
		F.append(("CRITICAL", "libcamera reports no cameras available",
				  "Check the CSI ribbon at both ends and camera_auto_detect in "
				  "the boot config.", "list_cameras"))
	elif re.search(r"imx\d+", cam, re.I):
		F.append(("OK", "Camera enumerated",
				  re.search(r"imx\d+", cam, re.I).group(0), "list_cameras"))

	if "No such file" in get("tuning_file"):
		F.append(("CRITICAL", "imx477_scientific.json is missing",
				  "The camera driver names this tuning file explicitly; without "
				  "it Picamera2 will fail to construct.", "tuning_file"))

	## -- clock -------------------------------------------------------------
	td = get("timedatectl")
	if re.search(r"(System clock synchronized|NTP service):\s*(no|inactive)", td, re.I):
		F.append(("WARN", "Clock is not NTP-synchronised",
				  "Scheduled jobs and event timestamps across scopes will drift "
				  "apart.", "timedatectl"))

	## -- units -------------------------------------------------------------
	m = re.search(r"(\d+)\s+loaded units listed", get("failed_units"))
	if m and int(m.group(1)) > 0:
		F.append(("WARN", f"{m.group(1)} failed systemd unit(s)",
				  "See the unit list.", "failed_units"))

	order = {"CRITICAL": 0, "WARN": 1, "UNKNOWN": 2, "OK": 3}
	F.sort(key=lambda f: order.get(f[0], 9))
	return F


def _count(text, pattern):
	"""Matching LINES, not regex matches.

	Counting matches double-reports a line that satisfies two alternatives of
	the same pattern -- "Out of memory: Killed process ..." hits both `out of
	memory` and `killed process` and was reported as two events.
	"""
	rx = re.compile(pattern, re.I)
	return sum(1 for line in (text or "").splitlines() if rx.search(line))


## ---------------------------------------------------------------------------
##  Extra, argument-driven checks
## ---------------------------------------------------------------------------

def server_checks(server):
	"""Reachability of the offload target. Only the hostname is ever used or
	recorded -- credentials from the config are neither read nor written."""
	q = shlex.quote(server)
	return [
		("dns",        f"DNS resolution of {server}",   f"getent hosts {q}", 10),
		("ping",       f"ICMP to {server}",             f"ping -c 3 -W 2 {q}", 20),
		("route_to",   f"Route to {server}",            f"ip route get $(getent hosts {q} | awk '{{print $1}}' | head -1) 2>&1", 10),
	]


def exp_checks(exp_dir):
	"""Evidence from one experiment directory about why it did not offload."""
	q = shlex.quote(exp_dir)
	return [
		("exp_listing",  "Experiment directory",        f"ls -la {q} | head -40", 40),
		("exp_sizes",    "Directory size",              f"du -sh {q} 2>/dev/null; du -sh {q}/* 2>/dev/null | sort -h | tail -15", 20),
		("exp_policies", "Policy markers",              f"ls -la {q}/.policy.* 2>&1", 10),
		("exp_rclone",   "rclone log tail",             f"tail -60 {q}/rclone.log 2>&1", 60),
		("exp_syncyaml", "Sync ledger tail",            f"tail -60 {q}/sync.yaml 2>&1", 60),
	]


CONFIG_PATHS = ["~/trappyverse/trappyconfig.yaml",   ## TrappyConfig.default_paths[0]
				"~/trappyconfig.yaml",               ## TrappyConfig.default_paths[1]
				"core/permaconfig/default_config.yaml"]  ## template; placeholders only

## Copied redacted as well. NM keyfiles carry the Wi-Fi PSK, so they can never
## go through run() -- that writes raw output to raw/.
CONFIG_GLOBS = ["/etc/NetworkManager/system-connections/*",
				"/etc/NetworkManager/conf.d/*"]


def _config_scan(pattern):
	"""First capture of `pattern` across the known config files, or None.

	Deliberately a line-scan rather than a YAML parse: the config holds the
	file-server password, and loading it into memory alongside a bundle writer
	is a way to leak one by accident. Only the matched value is ever touched,
	and placeholders (`<like-this>`) are rejected.
	"""
	rx = re.compile(pattern)
	for path in CONFIG_PATHS:
		path = os.path.expanduser(path)
		if not os.path.exists(path):
			continue
		try:
			with open(path, errors="replace") as f:
				for line in f:
					m = rx.match(line)
					if m and not m.group(1).startswith("<"):
						return m.group(1).strip("\"'")
		except Exception:
			continue
	return None


def discover_server():
	"""Hostname of the configured file server, or None."""
	return _config_scan(r"\s*server\s*:\s*([^\s#]+)")


def discover_scopeid():
	"""The scope name (M1..M8), or None.

	Anchored at column 0: `name:` is the top-level scope name, but the same key
	appears indented under every device in the assembly, so an unanchored match
	would return `pico`.
	"""
	return _config_scan(r"^name\s*:\s*([^\s#]+)")


## ---------------------------------------------------------------------------
##  Configuration copies
## ---------------------------------------------------------------------------

## Keys whose VALUE is redacted before a config is copied into the bundle. The
## bundle gets attached to tickets and chats, so a verbatim copy would publish
## the file-server password. Matched on the key name, so a value that merely
## looks secret is left alone.
## The separator is [:=], not just ":" -- YAML configs use `key: value` but
## NetworkManager keyfiles are INI, `key=value`. A colon-only pattern silently
## let `psk=<wifi password>` through into the bundle.
SECRET_KEY = re.compile(
	r"^(\s*-?\s*)([A-Za-z0-9_.-]*"
	r"(?:password|passwd|psk|secret|token|credential"
	r"|api[_-]?key|access[_-]?key|wep[_-]?key\d*|private[_-]?key|secret[_-]?key)"
	r"[A-Za-z0-9_.-]*)(\s*[:=]\s*)(.*)$", re.I)

EXTRA_CONFIGS = ["~/.config/rclone/rclone.conf", "~/.rclone.conf"]


def redact_line(line):
	"""Return (line, was_redacted). The value is replaced by a description of
	itself -- whether it was set at all is the diagnostic fact ("is the password
	even configured?"), and that survives redaction. The value does not."""
	m = SECRET_KEY.match(line.rstrip("\n"))
	if not m:
		return line, False
	raw = m.group(4).strip().strip("\"'")
	if not raw:
		return line, False          ## block header, not an assignment
	if raw.startswith("<") and raw.endswith(">"):
		state = "<redacted-placeholder-never-configured>"
	else:
		state = "<redacted-set>"
	return f"{m.group(1)}{m.group(2)}{m.group(3)}{state}\n", True


def _read_text(path):
	"""(text, note). Falls back to `sudo -n cat` for root-only files such as
	the NetworkManager keyfiles, which are 0600."""
	try:
		with open(path, errors="replace") as f:
			return f.read(), None
	except PermissionError:
		try:
			p = subprocess.run(f"sudo -n cat {shlex.quote(path)}", shell=True,
							   timeout=10, stdout=subprocess.PIPE,
							   stderr=subprocess.STDOUT)
			if p.returncode == 0:
				return p.stdout.decode("utf-8", "replace"), "read via sudo -n"
		except Exception:
			pass
		return None, "permission denied; sudo -n unavailable"
	except Exception as e:
		return None, f"{type(e).__name__}: {e}"


def copy_configs(root, redact=True):
	"""Copy the scope's configuration into the bundle, with secrets redacted.

	Worth having: almost every sync or device fault is explained by the config,
	and a bundle collected weeks ago is useless if the config has since been
	edited. Never copied verbatim -- see SECRET_KEY.
	"""
	dest = os.path.join(root, "config")
	os.makedirs(dest, exist_ok=True)
	copied = []
	paths = [os.path.expanduser(p) for p in CONFIG_PATHS + EXTRA_CONFIGS]
	for pattern in CONFIG_GLOBS:
		paths.extend(sorted(glob.glob(os.path.expanduser(pattern))))
	for path in paths:
		if not os.path.isfile(path):
			continue
		out_name = path.lstrip("/").replace("/", "__")
		text, note = _read_text(path)
		if text is None:
			copied.append({"source": path, "file": None, "redacted": 0,
						   "error": note})
			continue
		n_red, lines = 0, []
		for line in text.splitlines(keepends=True):
			if redact:
				line, red = redact_line(line)
				n_red += red
			lines.append(line)
		try:
			with open(os.path.join(dest, out_name), "w") as f:
				f.write(f"## source: {path}"
						f"{' (' + note + ')' if note else ''}\n")
				f.write(f"## {n_red} value(s) redacted by collect_diagnostics.py\n"
						if redact else
						"## verbatim copy -- secrets NOT redacted (--redact to redact)\n")
				f.writelines(lines)
			copied.append({"source": path, "file": f"config/{out_name}",
						   "redacted": n_red, "error": None})
		except Exception as e:
			copied.append({"source": path, "file": None, "redacted": 0,
						   "error": f"{type(e).__name__}: {e}"})
	return copied


## ---------------------------------------------------------------------------
##  Report
## ---------------------------------------------------------------------------

BADGE = {"CRITICAL": "[CRITICAL]", "WARN": "[WARN]    ",
		 "UNKNOWN": "[UNKNOWN] ", "OK": "[ok]      "}


def write_report(path, meta, groups, results, findings):
	w = []
	w.append(f"# Scope diagnostics -- {meta.get('scopeid') or meta['host']}")
	w.append("")
	w.append(f"- **Collected** {meta['stamp_human']}")
	w.append(f"- **Scope** `{meta.get('scopeid') or 'unknown'}`  "
			 f"**Host** `{meta['host']}`  **Model** {meta['model']}")
	w.append(f"- **Kernel** {meta['kernel']}")
	w.append(f"- **Collector** `collect_diagnostics.py` v{VERSION}")
	if meta.get("server"):
		w.append(f"- **File server tested** `{meta['server']}`")
	if meta.get("exp_dir"):
		w.append(f"- **Experiment inspected** `{meta['exp_dir']}`")
	w.append("")
	w.append("Raw, untruncated output for every command is in `raw/<slug>.txt`. "
			 "`index.json` has the same data machine-readably. Each triage line "
			 "names the raw file it came from.")
	w.append("")

	## -- triage ------------------------------------------------------------
	w.append("## Triage")
	w.append("")
	if not findings:
		w.append("No checks produced a finding, which usually means the "
				 "diagnostic commands themselves did not run. Check `index.json` "
				 "for non-zero return codes before concluding the scope is well.")
	else:
		counts = {}
		for lvl, *_ in findings:
			counts[lvl] = counts.get(lvl, 0) + 1
		w.append("  ".join(f"**{k}**: {v}" for k, v in sorted(counts.items())))
		w.append("")
		w.append("```")
		for lvl, title, detail, slug in findings:
			w.append(f"{BADGE.get(lvl, '[?]       ')} {title}")
			for line in _wrap(detail, 74):
				w.append(f"            {line}")
			w.append(f"            -> raw/{slug}.txt")
			w.append("")
		w.append("```")
	w.append("")

	## -- configuration -----------------------------------------------------
	w.append("## Configuration")
	w.append("")
	configs = meta.get("configs") or []
	if not configs:
		w.append("*No configuration file was found at any known path.*")
	else:
		w.append("Copied into this bundle with secrets redacted by key name. "
				 "Values are replaced by whether they were set, which is the "
				 "diagnostic fact; the values themselves are not in the bundle.")
		w.append("")
		for c in configs:
			if c["error"]:
				w.append(f"- `{c['source']}` -- **not copied**: {c['error']}")
			else:
				w.append(f"- `{c['source']}` -> `{c['file']}` "
						 f"({c['redacted']} value(s) redacted)")
	w.append("")

	## -- detail ------------------------------------------------------------
	for gslug, gtitle, checks in groups:
		w.append(f"## {gtitle}")
		w.append("")
		for slug, title, cmd, inline in checks:
			r = results.get(slug)
			if r is None:
				continue
			rc = "timeout/err" if r["rc"] is None else r["rc"]
			w.append(f"### {title}")
			w.append("")
			w.append(f"`{cmd}`")
			note = f" -- {r['note']}" if r.get("note") else ""
			w.append(f"<sub>rc={rc} &middot; {r['seconds']}s &middot; "
					 f"`raw/{slug}.txt`{note}</sub>")
			w.append("")
			body = (r["out"] or "").rstrip()
			if inline == 0:
				n = len(body.splitlines())
				w.append(f"*Not inlined ({n} lines). See `raw/{slug}.txt`.*")
			elif not body:
				w.append("*(no output)*")
			else:
				lines = body.splitlines()
				clipped = lines[:inline]
				w.append("```")
				w.extend(clipped)
				if len(lines) > inline:
					w.append(f"... {len(lines) - inline} more lines in raw/{slug}.txt")
				w.append("```")
			w.append("")
	with open(path, "w") as f:
		f.write("\n".join(w) + "\n")


def _wrap(text, width):
	out, line = [], ""
	for word in (text or "").split():
		if len(line) + len(word) + 1 > width:
			out.append(line)
			line = word
		else:
			line = f"{line} {word}".strip()
	if line:
		out.append(line)
	return out or [""]


## ---------------------------------------------------------------------------
##  Main
## ---------------------------------------------------------------------------

def main():
	ap = argparse.ArgumentParser(
		description="Collect Raspberry Pi system diagnostics into one bundle.")
	ap.add_argument("--out", default="~/diagnostics",
					help="parent directory for the bundle (default: ~/diagnostics). "
						 "Absolute on purpose: an open Experiment chdirs into its "
						 "own directory, so a relative default would drop the "
						 "bundle inside the experiment. Pass --out . if that is "
						 "what you want.")
	ap.add_argument("--exp-dir", default=None,
					help="an experiment directory to inspect (sync evidence)")
	ap.add_argument("--server", default=None,
					help="file server hostname to test; discovered from config "
						 "if omitted")
	ap.add_argument("--no-server", action="store_true",
					help="skip all network reachability tests")
	ap.add_argument("--redact", action="store_true",
					help="replace password/psk/token/key VALUES in the copied "
						 "configs with whether they were set. Off by default: "
						 "the bundle is an internal artefact and the real values "
						 "are usually what you need. Turn it on before sending a "
						 "bundle outside the lab.")
	ap.add_argument("--no-tar", action="store_true", help="do not write the tarball")
	ap.add_argument("--timeout", type=int, default=30,
					help="per-command timeout in seconds (default: 30)")
	args = ap.parse_args()

	if platform.system() != "Linux":
		print(f"[warn] this collects Linux/Raspberry Pi diagnostics; "
			  f"running on {platform.system()}. Most checks will be empty.",
			  file=sys.stderr)

	host = socket.gethostname()
	scopeid = discover_scopeid()
	now = datetime.datetime.now()
	stamp = now.strftime("%Y_%m_%d__%Hhh_%Mmm_%Ss")
	name = f"diag_{scopeid or host}__{stamp}"
	root = os.path.abspath(os.path.join(os.path.expanduser(args.out), name))
	raw = os.path.join(root, "raw")
	os.makedirs(raw, exist_ok=True)

	groups = [list(g) for g in GROUPS]

	server = args.server
	if not server and not args.no_server:
		server = discover_server()
	if server and not args.no_server:
		for g in groups:
			if g[0] == "sync":
				g[2] = g[2] + server_checks(server)

	if args.exp_dir:
		exp_dir = os.path.expanduser(args.exp_dir)
		for g in groups:
			if g[0] == "sync":
				g[2] = g[2] + exp_checks(exp_dir)
	else:
		exp_dir = None

	total = sum(len(g[2]) for g in groups)
	print(f"Collecting {total} checks into {root}")
	print(f"  scope: {scopeid or '(scopeid not in config)'}   host: {host}")

	results, done = {}, 0
	for gslug, gtitle, checks in groups:
		for slug, title, cmd, _inline in checks:
			done += 1
			print(f"  [{done:2d}/{total}] {gslug}/{slug} ... ", end="", flush=True)
			r = run(cmd, timeout=args.timeout)
			results[slug] = r
			with open(os.path.join(raw, f"{slug}.txt"), "w") as f:
				f.write(f"$ {cmd}\n")
				f.write(f"# rc={r['rc']} seconds={r['seconds']}"
						f"{' note=' + r['note'] if r.get('note') else ''}\n")
				f.write("#" + "-" * 70 + "\n")
				f.write(r["out"] or "")
			flag = r["note"] or (f"rc={r['rc']}" if r["rc"] not in (0, 1) else "ok")
			print(flag)

	meta = {
		"host": host,
		"scopeid": scopeid,
		"stamp": stamp,
		"stamp_human": now.strftime("%Y-%m-%d %H:%M:%S"),
		"kernel": (results.get("uname") or {}).get("out", "").strip(),
		"model": (results.get("model") or {}).get("out", "").strip() or "unknown",
		"collector_version": VERSION,
		"server": server if not args.no_server else None,
		"exp_dir": exp_dir,
	}

	try:
		meta["configs"] = copy_configs(root, redact=args.redact)
	except Exception as e:
		## Never lose a bundle over the config copy: 58 checks are already on
		## disk by this point.
		log = f"{type(e).__name__}: {e}"
		print(f"  [warn] config copy failed: {log}")
		meta["configs"] = [{"source": "(all)", "file": None, "redacted": 0,
							"error": log}]
	findings = triage(results)

	with open(os.path.join(root, "index.json"), "w") as f:
		json.dump({"meta": meta,
				   "findings": [{"level": l, "title": t, "detail": d, "raw": f"raw/{s}.txt"}
								for l, t, d, s in findings],
				   "checks": {slug: {"cmd": r["cmd"], "rc": r["rc"],
									 "seconds": r["seconds"], "note": r["note"],
									 "raw": f"raw/{slug}.txt",
									 "lines": len((r["out"] or "").splitlines())}
							  for slug, r in results.items()}},
				  f, indent=2)

	write_report(os.path.join(root, "REPORT.md"), meta, groups, results, findings)

	archive = None
	if not args.no_tar:
		archive = root + ".tar.gz"
		with tarfile.open(archive, "w:gz") as tar:
			tar.add(root, arcname=name)

	print()
	for lvl, title, _detail, slug in findings:
		if lvl in ("CRITICAL", "WARN"):
			print(f"  {BADGE[lvl]} {title}   (raw/{slug}.txt)")
	if not any(l in ("CRITICAL", "WARN") for l, *_ in findings):
		print("  no critical or warning findings")
	print()
	print(f"Report  : {os.path.join(root, 'REPORT.md')}")
	print(f"Index   : {os.path.join(root, 'index.json')}")
	if archive:
		size = os.path.getsize(archive) / 1e6
		print(f"Bundle  : {archive}  ({size:.1f} MB)")


if __name__ == "__main__":
	main()
