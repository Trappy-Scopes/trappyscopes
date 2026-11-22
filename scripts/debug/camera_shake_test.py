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

Does shaking crash the camera only while the preview is on?

The camera has died with libcamera's "Camera frontend has timed out ... check
that your camera sensor connector is attached securely" when a scope was
shaken with the preview on. That message means frames stopped arriving from
the CSI receiver; it does not test the cable. This script repeats the same
shake, cued by the script, with and without the preview, and records what the
camera, the CSI receiver and the kernel do around each one. After a crash it
brings the camera back, preview included, and records whether that worked.

Two conditions, alternated in random order:

    none   the camera with Picamera2's null preview. Every run without a
           preview already uses it: start() runs a null preview whenever no
           other preview is running. So "no preview" and "null preview" are
           the same thing.
    drm    the framework's preview to the monitor (scope.cam.preview_type,
           Preview.DRM, with scope.cam.preview_options).

The encoder runs throughout (MJPEG, red channel, per-frame RGB means kept),
into a null sink: no video reaches the disk, so storage is not tested.

Each trial lasts 2 min: switch to the condition, settle, a 5 s countdown,
SHAKE (10 s, beacon on), then watch. A crash is cam.frames standing still for
stall_s. Recovery level 1 restarts the recording and keeps the preview; level
2 rebuilds the Picamera2 object and starts the preview again. Every camera
call has a timeout: in the real crashes the script hung inside the camera
stack, and a test that hangs the same way records nothing.

    create_exp()
    start()          # ~40 min; Ctrl-C stops cleanly. Saves and syncs at the end.
    exp.close()

Output, inside the experiment folder:

    <eid>_intensities.csv   t_ns, r, g, b: one row per frame, sensor time
    <eid>_telemetry.csv     10 Hz: frames, CSI interrupts, CPU, CMA,
                            temperature, throttle flags, trial, phase
    kernel.log              dmesg, followed for the whole run
    libcamera.log           libcamera's messages (all of stderr), written live
    crash_<n>.txt           machine state at each crash
    trials stream           one row per trial
    events                  shake_protocol, camera_settings, camera_crash,
                            camera_recovery, shake_summary

libcamera.log and kernel.log come from detectors/cameras/camlogs.py.
libcamera writes to stderr, which is copied into libcamera.log while still
reaching the terminal, so nothing has to be exported before launching.
"""

import os

import collections
import csv
import datetime
import logging as log
import math
import random
import re
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from picamera2.outputs import Output

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from detectors.cameras.rpi_hq_picam2 import JpegEncoderRedWithBGStats
from detectors.cameras.camlogs import CameraLogs, csi_irq


__description__ = \
"""Shake the scope on cue, with and without the preview, and record whether
and how the camera crashes. create_exp() then start()."""


## --------------------------------------------------------------------------
##  Experiment
## --------------------------------------------------------------------------

def populate_exp():
	a = Experiment.current.attribs
	a["conditions"] = ("none", "drm")
	a["shakes_per_condition"] = 10
	a["seed"] = int(time.time()) % 100000   # rebuilds the trial order
	## One trial: settle, countdown, shake, watch -- 2 min in all.
	a["settle_s"] = 50
	a["countdown_s"] = 5
	a["shake_s"] = 10
	a["watch_s"] = 55
	a["light"] = (0.5, 0, 0)
	a["quality"] = 100
	a["num_threads"] = 3
	a["channels"] = ("r", "g", "b")
	a["flush_interval_s"] = 10
	a["poll_s"] = 0.1               # telemetry and stall check
	## cam.frames still for this long = crash. Above libcamera's own ~1 s
	## dequeue timeout, so libcamera has already given up when this fires.
	a["stall_s"] = 2.0
	a["cam_call_timeout_s"] = 15    # a camera call taking longer has hung
	a["max_recovery_attempts"] = 2
	a["preview_type"] = str(scope.cam.preview_type)
	a["preview_options"] = dict(scope.cam.preview_options)
	a["sync_files"] = False
	print(Panel(Pretty(a), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["camera_shake"])
	exp.new_measurementstream("trials",
		monitors=["trial", "block", "condition"],
		measurements=["crashed", "n_crashes", "crash_after_s", "reason",
					  "csi_irq_during_stall", "recover_level", "recover_s",
					  "recovered", "frames_missing", "gaps_over_100ms", "max_gap_ms",
					  "shake_strength", "libcamera_errors", "kernel_lines"])
	populate_exp()


## --------------------------------------------------------------------------
##  Calls that can hang
## --------------------------------------------------------------------------

class CallHung(Exception):
	"""A call did not return within its timeout."""


class CameraLost(Exception):
	"""The camera could not be brought back."""


def _guarded(fn, what, timeout=None):
	"""Run fn in a thread; raise CallHung if it does not return in time."""
	timeout = timeout or Experiment.current.attribs["cam_call_timeout_s"]
	box = {}

	def run():
		try:
			box["value"] = fn()
		except BaseException as e:
			box["error"] = e

	t = threading.Thread(target=run, daemon=True)
	t.start()
	t.join(timeout)
	if t.is_alive():
		raise CallHung(what)
	if "error" in box:
		raise box["error"]
	return box.get("value")


global _pico_stuck
_pico_stuck = False


def _pico(fn, what):
	"""Lights and beacon go through the Pico, whose serial exec has no
	timeout. Once it fails to answer, it is left alone for the rest of the run."""
	global _pico_stuck
	if _pico_stuck:
		return False
	try:
		_guarded(fn, what, timeout=10)
		return True
	except CallHung:
		_pico_stuck = True
		log.error(f"Pico: no reply to {what}; no further Pico calls this run")
		print(Panel(f"[red]The Pico did not answer {what}. Shake cues continue "
					f"in the terminal only.", title="pico"))
	except Exception as e:
		log.error(f"{what} failed: {type(e).__name__}: {e}")
	return False


## --------------------------------------------------------------------------
##  Output sinks
## --------------------------------------------------------------------------

class NullOutput(Output):
	"""Accepts encoded frames and discards them, counting them."""

	def __init__(self):
		super().__init__()
		self.frames = 0

	def outputframe(self, frame, keyframe=True, timestamp=None, packet=None,
					audio=False):
		if self.recording:
			self.frames += 1


global csv_lock, intens_path, telem_path, _recent, encoder, sink
encoder = sink = None
csv_lock = threading.Lock()
intens_path = telem_path = None
_recent = collections.deque(maxlen=25 * 300)     # (t_ns, r), last ~5 min


def _write_intensities(records):
	"""flush_fn: append a batch to intensities.csv. Runs on an encoder thread,
	so it stays cheap and never raises."""
	if not records:
		return
	try:
		with csv_lock:
			with open(intens_path, "a", newline="") as f:
				w = csv.writer(f)
				for r in records:
					w.writerow([r["t_ns"], f'{r.get("r", float("nan")):.4f}',
								f'{r.get("g", float("nan")):.4f}',
								f'{r.get("b", float("nan")):.4f}'])
			_recent.extend((r["t_ns"], r.get("r", float("nan"))) for r in records)
	except Exception as e:
		log.error(f"intensity flush failed: {type(e).__name__}: {e}")


## --------------------------------------------------------------------------
##  Camera
## --------------------------------------------------------------------------

def _cam_cycle():
	"""close -> open -> configure. Camera.open() replaces self.cam without
	closing the old one and does not apply the config, so close first and
	configure explicitly."""
	for stop in (lambda: scope.cam.cam.stop_recording(),
				 lambda: scope.cam.cam.stop(),
				 lambda: scope.cam.cam.stop_preview()):
		try:
			stop()
		except Exception:
			pass
	scope.cam.close()
	scope.cam.open()
	scope.cam.configure()
	scope.cam.cam.pre_callback = None
	scope.cam.cam.post_callback = None


def _new_encoder():
	a = Experiment.current.attribs
	return (JpegEncoderRedWithBGStats(q=a["quality"], num_threads=a["num_threads"],
									  intensity_channels=tuple(a["channels"]),
									  flush_fn=_write_intensities,
									  flush_interval_s=a["flush_interval_s"]),
			NullOutput())


def start_recording(condition):
	"""Start this condition's preview, then record into the null sink. With
	no preview started, Picamera2's start() runs its null preview."""
	global encoder, sink
	cam = scope.cam.cam
	if condition == "drm":
		_guarded(lambda: cam.start_preview(scope.cam.preview_type,
										   **scope.cam.preview_options),
				 "start_preview")
	encoder, sink = _new_encoder()
	_guarded(lambda: cam.start_recording(encoder, sink), "start_recording")


def _drain():
	"""Hand the encoder's per-frame tail to flush_fn."""
	if encoder is None:
		return
	try:
		encoder.drain()
	except Exception as e:
		log.error(f"drain failed: {type(e).__name__}: {e}")


def stop_recording():
	"""Stop the recording, keep its tail, stop the preview."""
	cam = scope.cam.cam
	try:
		_guarded(cam.stop_recording, "stop_recording")
	except CallHung:
		raise
	except Exception as e:
		log.error(f"stop_recording: {type(e).__name__}: {e}")
	_drain()
	try:
		_guarded(cam.stop_preview, "stop_preview")
	except CallHung:
		raise
	except Exception:
		pass                          # no preview was running


def _frames_advance(timeout_s=4.0):
	"""True once the camera delivers a frame. Reads scope.cam.cam afresh:
	level 2 replaces the Picamera2 object and its frame counter."""
	try:
		start = scope.cam.cam.frames
	except Exception:
		return False
	deadline = time.monotonic() + timeout_s
	while time.monotonic() < deadline:
		time.sleep(0.1)
		try:
			if scope.cam.cam.frames > start:
				return True
		except Exception:
			return False
	return False


def recover(condition):
	"""Bring the camera back. Returns (level, ok); raises CallHung if a
	camera call hangs. Level 1 restarts the recording and leaves the preview
	running; level 2 rebuilds the Picamera2 object and starts the preview
	again."""
	global encoder, sink
	try:
		cam = scope.cam.cam
		try:
			_guarded(cam.stop_recording, "stop_recording (recovery)")
		except CallHung:
			raise
		except Exception as e:
			log.error(f"stop_recording during recovery: {e}")
		_drain()
		encoder, sink = _new_encoder()
		_guarded(lambda: cam.start_recording(encoder, sink),
				 "start_recording (recovery)")
		if _frames_advance():
			return 1, True
		log.error("level 1 recovery: frames did not resume")
	except CallHung:
		raise
	except Exception as e:
		log.error(f"level 1 recovery failed: {type(e).__name__}: {e}")
	try:
		_guarded(_cam_cycle, "cam_cycle (recovery)")
		start_recording(condition)
		return 2, _frames_advance()
	except CallHung:
		raise
	except Exception as e:
		log.error(f"level 2 recovery failed: {type(e).__name__}: {e}")
		return 2, False


## --------------------------------------------------------------------------
##  Evidence
## --------------------------------------------------------------------------

def _run(cmd, timeout=10):
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		return p.stdout.decode("utf-8", "replace")
	except Exception as e:
		return f"<{type(e).__name__}: {e}>"


def _boot_ns():
	"""CLOCK_BOOTTIME, the clock SensorTimestamp (t_ns) is on."""
	try:
		return time.clock_gettime_ns(time.CLOCK_BOOTTIME)
	except (AttributeError, OSError):
		return time.monotonic_ns()


global _cpu_prev, _thr, _thr_at
_cpu_prev = None
_thr, _thr_at = "", 0.0


def _cpu_pct():
	global _cpu_prev
	try:
		with open("/proc/stat") as f:
			v = [int(x) for x in f.readline().split()[1:]]
		idle, total = v[3] + v[4], sum(v)
		prev, _cpu_prev = _cpu_prev, (idle, total)
		if prev is None or total == prev[1]:
			return ""
		return round(100.0 * (1 - (idle - prev[0]) / (total - prev[1])), 1)
	except Exception:
		return ""


def _throttled():
	"""vcgencmd forks, so at most once a second."""
	global _thr, _thr_at
	if time.monotonic() - _thr_at >= 1.0:
		m = re.search(r"throttled=(0x[0-9a-fA-F]+)", _run("vcgencmd get_throttled", 5))
		_thr, _thr_at = (m.group(1) if m else "?"), time.monotonic()
	return _thr


def _meminfo(key):
	try:
		with open("/proc/meminfo") as f:
			for line in f:
				if line.startswith(key + ":"):
					return round(int(line.split()[1]) / 1024.0, 1)
	except Exception:
		pass
	return ""


def _temp_c():
	try:
		with open("/sys/class/thermal/thermal_zone0/temp") as f:
			return round(int(f.read()) / 1000.0, 1)
	except Exception:
		return ""


TELEMETRY = ["wall", "boot_ns", "trial", "condition", "phase", "cam_frames",
			 "sink_frames", "queue", "csi_irq", "cpu_pct", "cma_free_mb",
			 "temp_c", "throttled"]


def _telemetry(w, state):
	try:
		cam = scope.cam.cam
		irq = csi_irq()
		state["irq"].append((time.monotonic(), irq))
		w.writerow([round(time.time(), 3), _boot_ns(), state["trial"],
					state["condition"], state["phase"], cam.frames,
					getattr(sink, "frames", ""),
					getattr(getattr(encoder, "tasks", None), "qsize", lambda: "")(),
					irq, _cpu_pct(), _meminfo("CmaFree"), _temp_c(), _throttled()])
	except Exception as e:
		log.error(f"telemetry row failed: {type(e).__name__}: {e}")


def _log_offsets():
	"""Current sizes of the libcamera and kernel logs, to count new lines."""
	out = {}
	for key, path in (("libcamera", _logs.libcamera_path),
					  ("kernel", "kernel.log")):
		try:
			out[key] = (path, os.path.getsize(path))
		except Exception:
			out[key] = (path, None)
	return out


def _new_lines(offsets):
	"""(libcamera ERROR/WARN lines, kernel lines) written since offsets."""
	counts = {}
	for key, (path, start) in offsets.items():
		try:
			with open(path, errors="replace") as f:
				f.seek(start or 0)
				lines = f.read().splitlines()
			counts[key] = (sum(bool(re.search(r"\b(ERROR|WARN)\b", l)) for l in lines)
						   if key == "libcamera" else len(lines))
		except Exception:
			counts[key] = None
	return counts["libcamera"], counts["kernel"]


## --------------------------------------------------------------------------
##  Crash handling
## --------------------------------------------------------------------------

global crashes
crashes = 0


def _irq_since(state, t):
	"""CSI interrupts counted since monotonic time t."""
	hist = [(tt, n) for tt, n in state["irq"] if n >= 0]
	if not hist:
		return None
	before = [n for tt, n in hist if tt <= t]
	return hist[-1][1] - (before[-1] if before else hist[0][1])


def _crash(state):
	"""Record a crash, recover, and put the result on the trial. Raises
	CallHung if a camera call hangs, CameraLost if recovery fails."""
	global crashes
	exp = Experiment.current
	a = exp.attribs
	crashes += 1
	state["n_crashes"] += 1
	after = round(state["last_t"] - state["shake_t"], 2)   # last frame vs shake start
	irq = _irq_since(state, state["last_t"])
	reason, tail = _logs.reason(since=state["log_offset"])
	snap = _logs.snapshot(f"crash_{crashes:03d}.txt")
	log.error(f"CRASH #{crashes} in trial {state['trial']} ({state['condition']}, "
			  f"{state['phase']}): {reason}")
	print(Panel(f"[red]CRASH #{crashes}: {reason}\n"
				f"last frame {after:+.1f} s from the shake start, "
				f"CSI interrupts since then: {irq}\n{tail.strip()[-300:]}",
				title=f"trial {state['trial']} ({state['condition']})"))
	exp.log_event("camera_crash", attribs={
		"n": crashes, "trial": state["trial"], "condition": state["condition"],
		"phase": state["phase"], "crash_after_s": after, "reason": reason,
		"csi_irq_during_stall": irq, "snapshot": snap})

	phase, state["phase"] = state["phase"], "recover"
	t0 = time.monotonic()
	level, ok = 0, False
	for _ in range(a["max_recovery_attempts"]):
		level, ok = recover(state["condition"])
		if ok:
			break
	recover_s = round(time.monotonic() - t0, 2)
	exp.log_event("camera_recovery", attribs={
		"n": crashes, "trial": state["trial"], "condition": state["condition"],
		"level": level, "recovered": ok, "recover_s": recover_s})
	print(Panel(f"{'[green]Recovered' if ok else '[red]Not recovered'} at level "
				f"{level} in {recover_s} s"
				+ (" (preview restarted)" if ok and level == 2 and state['condition'] == 'drm' else ""),
				title="recovery"))
	if state["first"] is None:
		state["first"] = {"crash_after_s": after, "reason": reason,
						  "csi_irq_during_stall": irq, "recover_level": level,
						  "recover_s": recover_s, "recovered": ok}
	state["phase"] = phase
	if not ok:
		raise CameraLost(f"not recovered after crash #{crashes}")


def _watch(until, state, w, tele):
	"""Telemetry and the stall check every poll_s until `until` (monotonic).
	A crash is handled in place, and the clock keeps running through it."""
	a = Experiment.current.attribs
	while time.monotonic() < until:
		time.sleep(a["poll_s"])
		_telemetry(w, state)
		tele.flush()
		try:
			n = scope.cam.cam.frames
		except Exception:
			n = state["last_n"]
		now = time.monotonic()
		if n != state["last_n"]:
			state["last_n"], state["last_t"] = n, now
		elif now - state["last_t"] >= a["stall_s"]:
			_crash(state)
			state["last_n"], state["last_t"] = scope.cam.cam.frames, time.monotonic()


def _trial_stats(base, shake, trial):
	"""From the per-frame records: frames missing and gaps over 100 ms during
	the shake, the longest gap in the whole trial, and the shake strength --
	the spread of the red intensity during the shake over its spread while
	settling (1 = no visible shake). Gaps count the window edges, so a gap
	that starts before the shake and ends inside it is not missed."""
	with csv_lock:
		x = np.array(_recent, dtype=float)
	out = {"frames_missing": None, "gaps_over_100ms": None, "max_gap_ms": None,
		   "shake_strength": None}
	if x.size == 0:
		return out
	x = x[np.argsort(x[:, 0])]
	t, r = x[:, 0], x[:, 1]
	b = (t >= base[0]) & (t < base[1])
	s = (t >= shake[0]) & (t < shake[1])
	if b.sum() > 10:
		period = float(np.median(np.diff(t[b])))
		out["frames_missing"] = int(round((shake[1] - shake[0]) / period - s.sum()))
	edges = lambda lo, hi: np.diff(np.concatenate([[lo], t[(t >= lo) & (t < hi)], [hi]]))
	out["gaps_over_100ms"] = int((edges(*shake) > 100e6).sum())
	out["max_gap_ms"] = round(float(edges(*trial).max()) / 1e6, 1)
	if b.sum() > 10 and s.sum() > 10 and np.std(r[b]) > 0:
		out["shake_strength"] = round(float(np.std(r[s]) / np.std(r[b])), 2)
	return out


def _fisher(a, b, c, d):
	"""Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]]."""
	n, r1, c1 = a + b + c + d, a + b, a + c
	if n == 0:
		return None
	p = lambda k: math.comb(r1, k) * math.comb(n - r1, c1 - k) / math.comb(n, c1)
	obs = p(a)
	return round(min(1.0, sum(p(k) for k in range(max(0, c1 - n + r1), min(r1, c1) + 1)
							  if p(k) <= obs * (1 + 1e-9))), 4)


## --------------------------------------------------------------------------
##  Run
## --------------------------------------------------------------------------

def _schedule(a):
	"""Blocks of one trial per condition, each block in random order."""
	rng = random.Random(a["seed"])
	trials = []
	for block in range(a["shakes_per_condition"]):
		order = list(a["conditions"])
		rng.shuffle(order)
		trials += [(block + 1, c) for c in order]
	return trials


def _camera_settings():
	"""What the camera is really running at, from one frame's metadata."""
	try:
		md = _guarded(scope.cam.cam.capture_metadata, "capture_metadata", timeout=5)
		keep = ("ExposureTime", "FrameDuration", "AnalogueGain", "SensorTemperature")
		Experiment.current.log_event("camera_settings",
									 attribs={k: md.get(k) for k in keep})
	except Exception as e:
		log.error(f"camera settings not read: {type(e).__name__}: {e}")


def start():
	"""Run the shake protocol. Blocks ~40 min; Ctrl-C stops cleanly. Saves
	and syncs at the end (cleanup())."""
	global exp, scope, intens_path, telem_path
	exp = Experiment.current
	scope = ScopeAssembly.current
	a = exp.attribs
	intens_path = exp.newfile("intensities.csv", abspath=False)
	telem_path = exp.newfile("telemetry.csv", abspath=False)
	with open(intens_path, "w", newline="") as f:
		csv.writer(f).writerow(["t_ns", "r", "g", "b"])
	with open(telem_path, "w", newline="") as f:
		csv.writer(f).writerow(TELEMETRY)

	trials = _schedule(a)
	exp.log_event("shake_protocol", attribs={"order": [c for _, c in trials],
											 "seed": a["seed"]})
	global _logs
	_logs = CameraLogs().start()       # libcamera.log and kernel.log, live
	if not _pico(lambda: scope.lit.setVs(*a["light"]), "lights on"):
		_logs.stop()
		raise RuntimeError("The Pico did not set the light; nothing started.")
	_pico(scope.beacon.off, "beacon off")
	minutes = len(trials) * (a["settle_s"] + a["countdown_s"] + a["shake_s"]
							 + a["watch_s"]) / 60
	print(Panel(f"{len(trials)} trials, about {minutes:.0f} min. Shake only when "
				f"told: SHAKE NOW in the terminal, beacon on. Same gesture each "
				f"time. Ctrl-C stops cleanly.", title="camera_shake_test"))

	tele = open(telem_path, "a", newline="")
	w = csv.writer(tele)
	state = {"trial": 0, "condition": "", "phase": "setup", "irq": collections.deque(maxlen=600),
			 "last_n": 0, "last_t": time.monotonic(), "shake_t": time.monotonic(),
			 "n_crashes": 0, "first": None, "log_offset": 0}
	rows, current, stopped_by, hung = [], None, "completed", None
	try:
		_guarded(_cam_cycle, "cam_cycle")
		for i, (block, cond) in enumerate(trials, 1):
			state.update(trial=i, condition=cond, n_crashes=0, first=None)
			if cond != current:
				state["phase"] = "switch"
				if current is not None:
					stop_recording()
				start_recording(cond)
				if not _frames_advance() and not recover(cond)[1]:
					raise CameraLost(f"no frames after switching to {cond}")
				if current is None:
					_camera_settings()
				current = cond
			state["last_n"], state["last_t"] = scope.cam.cam.frames, time.monotonic()

			t0 = time.monotonic()
			state["shake_t"] = shake_t = t0 + a["settle_s"] + a["countdown_s"]
			offsets = _log_offsets()
			state["log_offset"] = _logs.size()
			b0 = _boot_ns()
			print(Panel(f"Trial {i}/{len(trials)}: [bold]{cond}[/bold]. Hands off; "
						f"settling {a['settle_s']} s.", title="trial"))
			state["phase"] = "settle"
			_watch(t0 + a["settle_s"], state, w, tele)
			b1 = _boot_ns()
			state["phase"] = "countdown"
			for k in range(a["countdown_s"], 0, -1):
				print(f"[yellow]  shake in {k}")
				_watch(shake_t - k + 1, state, w, tele)
			s0 = _boot_ns()
			state["phase"] = "shake"
			_pico(scope.beacon.on, "beacon on")
			sys.stdout.write("\a")
			print(Panel(f"[bold red]SHAKE NOW ({a['shake_s']} s)", title=f"trial {i}"))
			_watch(shake_t + a["shake_s"], state, w, tele)
			s1 = _boot_ns()
			_pico(scope.beacon.off, "beacon off")
			print(Panel("[bold green]STOP. Hands off.", title=f"trial {i}"))
			state["phase"] = "watch"
			_watch(shake_t + a["shake_s"] + a["watch_s"], state, w, tele)

			_drain()
			lib, kern = _new_lines(offsets)
			first = state["first"] or {}
			row = dict(trial=i, block=block, condition=cond,
					   crashed=state["n_crashes"] > 0, n_crashes=state["n_crashes"],
					   crash_after_s=first.get("crash_after_s"),
					   reason=first.get("reason"),
					   csi_irq_during_stall=first.get("csi_irq_during_stall"),
					   recover_level=first.get("recover_level"),
					   recover_s=first.get("recover_s"),
					   recovered=first.get("recovered"),
					   libcamera_errors=lib, kernel_lines=kern,
					   **_trial_stats((b0, b1), (s0, s1), (b0, _boot_ns())))
			exp.mstreams["trials"](**row)
			rows.append(row)
			print(f"  trial {i}: {'CRASHED' if row['crashed'] else 'no crash'}, "
				  f"shake strength {row['shake_strength']}, "
				  f"frames missing {row['frames_missing']}")
	except KeyboardInterrupt:
		stopped_by = "ctrl_c"
		print("\n[yellow]Interrupted. Finishing cleanly...")
	except CallHung as e:
		stopped_by, hung = "camera_hung", str(e)
		log.error(f"camera call hung: {e}")
		exp.log_event("camera_hung", attribs={"call": hung, "trial": state["trial"],
											  "condition": state["condition"]})
		print(Panel(f"[red]The camera stack hung in {hung} -- the failure seen in "
					f"the real crashes. Recorded; the run stops here. Restart the "
					f"framework before using the camera again.", title="camera hung"))
	except CameraLost as e:
		stopped_by = "camera_lost"
		log.error(str(e))
		print(Panel(f"[red]{e}. The run stops here.", title="camera lost"))
	except Exception as e:
		stopped_by = f"error: {type(e).__name__}: {e}"
		log.error(f"shake test stopped: {stopped_by}")
		print(Panel(f"[red]{stopped_by}", title="camera_shake_test"))
	finally:
		try:
			tele.close()
		except Exception:
			pass
		_logs.stop()
		if hung is None:                # a hung camera stack would hang these too
			try:
				stop_recording()
				_guarded(scope.cam.close, "camera close")
			except Exception as e:
				log.error(f"camera shutdown: {type(e).__name__}: {e}")
		_pico(scope.beacon.off, "beacon off")
		_pico(lambda: scope.lit.setVs(0, 0, 0), "lights off")

	summary = {"stopped_by": stopped_by, "trials_done": len(rows), "crashes": crashes}
	for c in a["conditions"]:
		r = [x for x in rows if x["condition"] == c]
		summary[f"{c}_crashed"] = sum(x["crashed"] for x in r)
		summary[f"{c}_trials"] = len(r)
	if len(a["conditions"]) == 2:
		(c1, c2) = a["conditions"]
		summary["fisher_p"] = _fisher(summary[f"{c2}_crashed"],
									  summary[f"{c2}_trials"] - summary[f"{c2}_crashed"],
									  summary[f"{c1}_crashed"],
									  summary[f"{c1}_trials"] - summary[f"{c1}_crashed"])
	exp.log_event("shake_summary", attribs=summary)
	print(Panel(Pretty(summary), title="shake test"))
	cleanup()


def _step(what, fn):
	try:
		return fn()
	except Exception as e:
		log.error(f"cleanup: {what} failed: {type(e).__name__}: {e}")
		print(f"[red]cleanup: {what} failed: {type(e).__name__}: {e}")


def cleanup():
	"""Stop the schedule, save and sync. Called by
	start() at the end; call it yourself if start() did not get there. Does
	NOT close the experiment -- type exp.close() afterwards."""
	global exp
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True

	_step("note", lambda: exp.note("Camera shake test finished and offloaded."))
	_step("save", exp.__save__)
	_step("sync", exp.sync_dir)
	print(Panel("[yellow]Saved and offloaded. The experiment is still OPEN -- "
				"type [bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	scope = ScopeAssembly.current
	print(Panel("create_exp()\nstart()        # ~40 min, saves and syncs at the end\n"
				"exp.close()",
				title="camera_shake_test"))
