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

Long-term per-frame RGB intensity, recorded continuously, writing no video.

Same shape as mjpeg_continuous_autosplit.py -- one long continuous recording,
the same camera configuration, the same encoder -- with one difference: the
encoded frames are DISCARDED. Only the per-channel mean intensity of each frame
is kept. That makes a 14-20 h run cost a few tens of megabytes instead of
several hundred gigabytes, and it makes this script safe to run on a scope
whose SD card is already full.

Because the pipeline is otherwise identical to the recording script, the run
doubles as the camera-resilience test:

    A.  the intensity series itself, at the full 25 Hz frame rate
    B.  a measured rate of camera stalls over a long run
    C.  a place to provoke them -- shake the scope and the CSI link drops
    D.  a test of whether stop/start actually recovers a stalled recording

On a stall the script records WHY (libcamera's own log), recovers the camera,
and carries on, timing every step. The intensity series should be flat across a
shake; the camera is expected to stall. Both are the measurement.

    create_exp()            open the experiment
    start_acq_blocking()    run (blocks; Ctrl-C stops cleanly)
    mark("shake start")     timestamp anything, from the REPL, any time
    cleanup()               save, sync, stop the schedule

Why the frames are still JPEG-encoded
-------------------------------------
Discarding them after encoding looks wasteful, and it is -- deliberately. The
CPU load, thread pool and output path are then identical to the real recording
script, so a stall seen here is a stall that would have happened there. Skipping
the encode would make this cheaper and much less representative. The intensity
means are computed inside the encoder anyway (JpegEncoderGrayChannel), so the
encode is the thing that carries them.

Reading the libcamera log
-------------------------
LIBCAMERA_LOG_FILE must be set before libcamera is loaded, which happens the
moment hive.assembly builds the camera. It is set at the top of this module,
before that import. If the camera was already constructed in this interpreter,
the variable arrives too late -- export it in the shell before launching:

    export LIBCAMERA_LOG_FILE=~/libcamera.log
"""

import os

## MUST precede any import that pulls in picamera2/libcamera. Absolute path,
## because Experiment.__init__ chdirs into the experiment directory and a
## relative path would land somewhere different depending on when libcamera
## happened to open it. The file is copied into the experiment by cleanup().
LIBCAMERA_LOG = os.path.expanduser("~/libcamera.log")
os.environ.setdefault("LIBCAMERA_LOG_FILE", LIBCAMERA_LOG)
os.environ.setdefault("LIBCAMERA_LOG_LEVELS",
					  "RPI:INFO,Camera:INFO,V4L2:INFO,IPAProxy:INFO")

from datetime import timedelta
import csv
import datetime
import hashlib
import json
import logging as log
import shutil
import subprocess
import threading
import time

import re

import numpy as np
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from picamera2.outputs import Output

from expframework.experiment import Experiment
from expframework.protocol import Protocol
from hive.assembly import ScopeAssembly
from detectors.cameras.rpi_hq_picam2 import JpegEncoderRedWithBGStats


__description__ = \
"""Long-term continuous RGB intensity, no video written.

Use create_exp() to open an experiment, start_acq_blocking() to run,
mark("label") to timestamp a shake, cleanup() to finish.
"""


## --------------------------------------------------------------------------
##  Experiment
## --------------------------------------------------------------------------

def populate_exp():
	"""Add experimental parameters."""
	exp = Experiment.current
	exp.attribs["run_hours"] = 16
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 18
	exp.attribs["quality"] = 100
	exp.attribs["num_threads"] = 3
	exp.attribs["light"] = (0.5, 0, 0)
	exp.attribs["group"] = "red_light"
	exp.attribs["channels"] = ("r", "g", "b")
	exp.attribs["tandh_sampling_period_minutes"] = 5

	## T&H is also read at this period into telemetry.csv, alongside the CPU
	## and camera-sensor temperatures. The tandh stream above stays at 5 min:
	## every stream call rewrites the experiment YAML, which is disk I/O.
	exp.attribs["tandh_poll_s"] = 1.0

	## Per-frame records are flushed to CSV on this interval. Without a
	## flush_fn the encoder keeps every record in memory, and 16 h at 25 Hz is
	## ~1.4 million of them -- see JpegEncoderRedWithBGStats.
	exp.attribs["flush_interval_s"] = 60

	## Telemetry sample period, and how long cam.frames may stand still before
	## the camera is declared stalled. 2 s sits above libcamera's own 1 s
	## dequeue timeout, so by the time this fires libcamera has already given
	## up, cancelled its requests and is waiting for the application to
	## restart the stream -- which is exactly when stop/start is the remedy.
	exp.attribs["poll_s"] = 1.0
	exp.attribs["stall_s"] = 2.0

	## Give up after this many consecutive failed recoveries and keep the rest
	## of the run (tandh, telemetry) going rather than dying.
	exp.attribs["max_recovery_attempts"] = 3
	exp.attribs["sync_files"] = False
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["longterm_intensity"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])

	## One row per flush, not per frame: a MeasurementStream call writes the
	## experiment YAML to disk, which cannot be done at 25 Hz. The per-frame
	## data goes to intensities.csv.
	exp.new_measurementstream("intensity",
		monitors=["window", "frames"],
		measurements=["r_mean", "r_std", "g_mean", "g_std", "b_mean", "b_std"])

	## One row per stall.
	exp.new_measurementstream("stalls",
		monitors=["n", "reason", "level", "recovered"],
		measurements=["stalled_at_s", "recover_s", "frames_before"])

	populate_exp()

	os.makedirs("protocols", exist_ok=True)
	for src in ("experiments/masterprotocols/masterprotocol_June26.md",
				"experiments/selectswimmers.md"):
		try:
			Protocol(src).write(os.path.join("protocols", os.path.basename(src)))
		except Exception as e:
			print(Panel(f"[red]Protocol not loaded: {src}\n{e}", title="protocol"))


## --------------------------------------------------------------------------
##  Output sink -- counts frames, writes nothing
## --------------------------------------------------------------------------

class NullOutput(Output):
	"""Accepts encoded frames and discards them.

	Deliberately a real Output rather than passing None: the encoder's output
	thread only runs when there is an output to feed, and that thread's
	liveness is one of the signals this script watches. Everything from the
	camera through the encode pool to the output thread stays exactly as it is
	in the recording script; only the write to disk is removed.

	Counting here as well as at the camera matters. cam.frames counts what
	libcamera delivered; self.frames counts what came out of the encoder. The
	two diverging is how an encoder-side stall is told apart from a camera-side
	one.
	"""

	def __init__(self):
		super().__init__()
		self.frames = 0
		self.bytes = 0

	def outputframe(self, frame, keyframe=True, timestamp=None, packet=None,
					audio=False):
		if self.recording:
			self.frames += 1
			self.bytes += len(frame)


## --------------------------------------------------------------------------
##  Per-frame intensity sink
## --------------------------------------------------------------------------

global csv_lock, csv_rows, intens_path, telem_path
csv_lock = threading.Lock()
csv_rows = 0
intens_path = None
telem_path = None


def _write_intensities(records):
	"""Append a flushed batch to intensities.csv.

	Runs on an ENCODER thread (JpegEncoderRedWithBGStats calls flush_fn from
	__record_intensities__), so it is lock-guarded against the drain performed
	by the monitor thread, and it must stay cheap -- an append and a flush,
	nothing more. Exceptions here are swallowed by the encoder, so anything
	that goes wrong is logged rather than raised.
	"""
	global csv_rows
	if not records:
		return
	try:
		with csv_lock:
			with open(intens_path, "a", newline="") as f:
				w = csv.writer(f)
				for r in records:
					w.writerow([r["t_ns"],
								f'{r.get("r", float("nan")):.4f}',
								f'{r.get("g", float("nan")):.4f}',
								f'{r.get("b", float("nan")):.4f}'])
				f.flush()
			csv_rows += len(records)
	except Exception as e:
		log.error(f"intensity flush failed: {type(e).__name__}: {e}")


def _summarise(records, window):
	"""One stream row per flush -- the thing that is actually plottable later
	without reading a million-line CSV."""
	if not records:
		return
	try:
		a = {c: np.array([r[c] for r in records if c in r], dtype=float)
			 for c in ("r", "g", "b")}
		Experiment.current.mstreams["intensity"](
			window=window, frames=len(records),
			**{f"{c}_{k}": round(float(getattr(a[c], k)()), 4)
			   for c in ("r", "g", "b") for k in ("mean", "std")
			   if a[c].size})
	except Exception as e:
		log.error(f"intensity summary failed: {type(e).__name__}: {e}")


## --------------------------------------------------------------------------
##  Camera
## --------------------------------------------------------------------------

def cam_cycle():
	"""close -> open -> configure, leaving the camera open and configured.

	Same reasoning as the other scripts here: Camera.open() assigns a new
	Picamera2 over self.cam WITHOUT closing the old one, and open() does not
	apply self.config, so always close first and configure explicitly.
	"""
	global scope
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


def new_encoder():
	"""A fresh encoder and sink.

	intensity_channels is passed explicitly: JpegEncoderRedWithBGStats
	setdefault()s it to ("g", "b"), which would leave the recorded RED channel
	unmeasured. All three are wanted here.
	"""
	exp = Experiment.current
	enc = JpegEncoderRedWithBGStats(
		q=exp.attribs["quality"],
		num_threads=exp.attribs["num_threads"],
		intensity_channels=tuple(exp.attribs["channels"]),
		flush_fn=_write_intensities,
		flush_interval_s=exp.attribs["flush_interval_s"])
	return enc, NullOutput()


## Camera-sensor temperature. The IMX477 reports it in each frame's embedded
## data and libcamera passes it on as "SensorTemperature" (integer degC,
## clamped -20..80). It is sampled from a post_callback once a second, not per
## frame. Absent from the metadata -> the column stays blank.
global _cam_temp, _cam_temp_at
_cam_temp, _cam_temp_at = None, 0.0


def _cam_temp_cb(request):
	"""Runs on the camera thread for every frame, so it must be cheap and must
	never raise. Reads the metadata at most once a second."""
	global _cam_temp, _cam_temp_at
	try:
		now = time.monotonic()
		if now - _cam_temp_at >= 1.0:
			_cam_temp_at = now
			_cam_temp = request.get_metadata().get("SensorTemperature")
	except Exception:
		pass


def _cam_temp_c():
	"""The last reading, or blank if it is more than 5 s old (camera stalled)."""
	if _cam_temp is None or time.monotonic() - _cam_temp_at > 5.0:
		return ""
	return round(float(_cam_temp), 1)


def start_recording():
	"""Begin a continuous recording into the null sink."""
	global encoder, sink, scope
	encoder, sink = new_encoder()
	## Re-attached on every start: cam_cycle() clears the callbacks, and a
	## level-2 recovery replaces the Picamera2 object entirely.
	scope.cam.cam.post_callback = _cam_temp_cb
	scope.cam.cam.start_recording(encoder, sink)
	log.info("Recording started (frames discarded, intensities kept).")


def drain_encoder(window):
	"""Take whatever the encoder still holds and write it out.

	Called before an encoder is discarded, so the tail of a window is not lost
	when the camera is restarted mid-flight.
	"""
	global encoder
	try:
		records = encoder.drain()
	except Exception as e:
		log.error(f"drain failed: {type(e).__name__}: {e}")
		return
	_write_intensities(records)
	_summarise(records, window)


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


def stall_reason():
	"""Why the camera stopped, in libcamera's own words.

	libcamera logs the frontend timeout and the dequeue-timer expiry and then
	returns -- there is no exception to catch anywhere in the Python stack, so
	its log is the only place the reason exists.
	"""
	logfile = os.environ.get("LIBCAMERA_LOG_FILE", LIBCAMERA_LOG)
	tail = ""
	if os.path.exists(logfile):
		tail = _run(f"tail -40 {logfile}")
	else:
		## No log file: the variable was set after libcamera loaded. The same
		## messages go to stderr and, under a service, to the journal.
		tail = _run("journalctl -b --no-pager 2>/dev/null | "
					"grep -iE 'frontend has timed out|Dequeue timer|"
					"attached securely|vc_sm_cma' | tail -20")

	for pattern, label in (("frontend has timed out", "frontend_timeout"),
						   ("Dequeue timer", "dequeue_timeout"),
						   ("vc_sm_cma", "cma_failure"),
						   ("v4l2_m2m", "v4l2_poll_block")):
		if pattern.lower() in tail.lower():
			return label, tail
	return "unknown", tail


def snapshot(tag):
	"""Freeze the machine state at the moment of a stall."""
	try:
		path = f"stall_{tag}.txt"
		with open(path, "w") as f:
			f.write(f"## {datetime.datetime.now()}\n\n")
			for title, cmd in (("dmesg", "dmesg -T 2>/dev/null | tail -60"),
							   ("journal", "journalctl -b --no-pager 2>/dev/null | tail -40"),
							   ("throttled", "vcgencmd get_throttled; vcgencmd measure_temp"),
							   ("meminfo", "grep -iE 'cma|MemAvailable' /proc/meminfo")):
				f.write(f"\n===== {title} =====\n{_run(cmd)}")
		return path
	except Exception as e:
		log.error(f"snapshot failed: {type(e).__name__}: {e}")
		return None


def _temp_c():
	try:
		with open("/sys/class/thermal/thermal_zone0/temp") as f:
			return round(int(f.read().strip()) / 1000.0, 1)
	except Exception:
		return -1.0


global _throttled_cache, _throttled_at
_throttled_cache, _throttled_at = "", 0.0


def _throttled():
	"""vcgencmd forks, so it is sampled at most once a minute rather than at
	the 1 Hz telemetry rate."""
	global _throttled_cache, _throttled_at
	if time.monotonic() - _throttled_at > 60.0:
		out = _run("vcgencmd get_throttled", timeout=5)
		m = re.search(r"throttled=(0x[0-9a-fA-F]+)", out)
		_throttled_cache = m.group(1) if m else "?"
		_throttled_at = time.monotonic()
	return _throttled_cache


def _csi_irq():
	"""Total interrupts on the CSI/Unicam receiver.

	The one counter that sits BELOW picamera2. If this keeps climbing while
	cam.frames stands still, the camera is still delivering and the stall is
	software-side; if it stops climbing, the link or the sensor stopped. That
	distinction is not available anywhere else in the stack.
	"""
	try:
		total = 0
		with open("/proc/interrupts") as f:
			for line in f:
				if re.search(r"csi|unicam|rp1-cfe|mipi", line, re.I):
					total += sum(int(x) for x in line.split()[1:] if x.isdigit())
		return total
	except Exception:
		return -1


def _rss_mb():
	try:
		with open("/proc/self/status") as f:
			for line in f:
				if line.startswith("VmRSS:"):
					return round(int(line.split()[1]) / 1024.0, 1)
	except Exception:
		pass
	return -1.0


def _cma_free_mb():
	try:
		with open("/proc/meminfo") as f:
			for line in f:
				if line.startswith("CmaFree:"):
					return round(int(line.split()[1]) / 1024.0, 1)
	except Exception:
		pass
	return -1.0


## --------------------------------------------------------------------------
##  Recovery
## --------------------------------------------------------------------------

def _frames_advance(timeout_s=4.0):
	"""True once the camera delivers a frame again.

	The only honest test that recovery worked. Reading scope.cam.cam fresh on
	every pass because level 2 replaces the Picamera2 object entirely, and a
	new one restarts its own frame counter at zero -- so this compares against
	a baseline taken after the restart, never across it.
	"""
	global scope
	start = scope.cam.cam.frames
	deadline = time.monotonic() + timeout_s
	while time.monotonic() < deadline:
		time.sleep(0.1)
		try:
			if scope.cam.cam.frames > start:
				return True
		except Exception:
			return False
	return False


def recover(window):
	"""Bring the camera back. Returns (level, ok).

	Two levels, cheapest first. Level 1 is exactly what a sampling run does
	between clips, and what restarting a preview does by hand -- it is the
	recovery libcamera is waiting for after it cancels its requests. Level 2
	rebuilds the Picamera2 object, for the case where the first is not enough.
	"""
	global encoder, sink, scope

	drain_encoder(window)

	## Level 1: stop and restart the recording on the existing camera.
	try:
		try:
			scope.cam.cam.stop_recording()
		except Exception as e:
			log.error(f"stop_recording during recovery: {e}")
		start_recording()
		if _frames_advance():
			return 1, True
		log.error("level 1 recovery: frames did not resume")
	except Exception as e:
		log.error(f"level 1 recovery failed: {type(e).__name__}: {e}")

	## Level 2: full close / open / configure, then record again.
	try:
		cam_cycle()
		start_recording()
		return 2, _frames_advance()
	except Exception as e:
		log.error(f"level 2 recovery failed: {type(e).__name__}: {e}")
		return 2, False


## --------------------------------------------------------------------------
##  Tuning-file verification
## --------------------------------------------------------------------------

## The driver asks for the scientific tuning; the stock file is what libcamera
## falls back to if that request is lost. Both are compared against what the
## camera is actually doing.
TUNING_FILES = {
	"scientific": "/usr/share/libcamera/ipa/rpi/vc4/imx477_scientific.json",
	"default": "/usr/share/libcamera/ipa/rpi/vc4/imx477.json",
}


def _algorithms(tuning):
	"""v2 tuning files list single-key dicts under "algorithms"; v1 is flat.
	Same parser as camtests/ccm_crosstalk_test.py."""
	if "algorithms" in tuning:
		out = {}
		for entry in tuning["algorithms"]:
			out.update(entry)
		return out
	return {k: v for k, v in tuning.items() if k.startswith("rpi.")}


def _ccm_table(path):
	with open(path) as f:
		ccms = _algorithms(json.load(f)).get("rpi.ccm", {}).get("ccms", [])
	return sorted(((c["ct"], c["ccm"]) for c in ccms), key=lambda x: x[0])


def _interp_ccm(table, ct):
	"""rpi.ccm interpolates linearly in colour temperature and clamps at the
	ends of the table; do the same."""
	if not table:
		return None
	if ct <= table[0][0]:
		return table[0][1]
	if ct >= table[-1][0]:
		return table[-1][1]
	for (c0, m0), (c1, m1) in zip(table, table[1:]):
		if c0 <= ct <= c1:
			w = (ct - c0) / float(c1 - c0)
			return [a + w * (b - a) for a, b in zip(m0, m1)]
	return None


def verify_tuning():
	"""Which tuning file is the camera ACTUALLY using? Three independent answers.

	1. requested -- what picamera2 put in LIBCAMERA_RPI_TUNING_FILE.
	2. libcamera_says -- the "Using tuning file <path>" line libcamera writes
	   at INFO under IPAProxy when it loads the IPA. Reliable only if
	   LIBCAMERA_LOG_FILE was set before the camera system first started; if
	   the framework built the camera at boot, the line went to stderr.
	3. ccm_match -- behavioural, and independent of logging: the camera
	   reports the colour-correction matrix it is applying and the colour
	   temperature it chose. Interpolating each candidate file's CCM table at
	   that temperature and comparing shows which file the numbers came from.

	Must never raise; the result is logged and the run carries on.
	"""
	global scope
	res = {"requested": os.environ.get("LIBCAMERA_RPI_TUNING_FILE")}
	try:
		logfile = os.environ.get("LIBCAMERA_LOG_FILE", LIBCAMERA_LOG)
		hits = []
		if os.path.exists(logfile):
			with open(logfile, errors="replace") as f:
				hits = [l.strip() for l in f if "Using tuning file" in l]
		res["libcamera_says"] = hits[-1].split("Using tuning file", 1)[1].strip() \
			if hits else None

		md = scope.cam.cam.capture_metadata()
		ct, ccm = md.get("ColourTemperature"), md.get("ColourCorrectionMatrix")
		res["colour_temperature"] = ct
		res["reported_ccm"] = [round(x, 4) for x in ccm] if ccm else None
		if ct and ccm:
			errs = {}
			for name, path in TUNING_FILES.items():
				if os.path.exists(path):
					expect = _interp_ccm(_ccm_table(path), ct)
					if expect:
						errs[name] = round(max(abs(a - b) for a, b in zip(expect, ccm)), 4)
			res["ccm_max_abs_error"] = errs
			if errs:
				best = min(errs, key=errs.get)
				## 0.02 allows for float rounding in the reported metadata.
				res["ccm_match"] = best if errs[best] < 0.02 else "inconclusive"

		sci = TUNING_FILES["scientific"]
		if os.path.exists(sci):
			with open(sci, "rb") as f:
				res["scientific_sha256"] = hashlib.sha256(f.read()).hexdigest()
			res["scientific_mtime"] = str(datetime.datetime.fromtimestamp(
				os.path.getmtime(sci)))
		else:
			res["scientific_sha256"] = "FILE MISSING"
	except Exception as e:
		res["error"] = f"{type(e).__name__}: {e}"

	sci = TUNING_FILES["scientific"]
	evidence = [res.get("libcamera_says") == sci, res.get("ccm_match") == "scientific"]
	against = [res.get("libcamera_says") not in (None, sci),
			   res.get("ccm_match") == "default"]
	res["verdict"] = ("scientific CONFIRMED" if any(evidence) and not any(against)
					  else "NOT the scientific tuning" if any(against)
					  else "unconfirmed")
	colour = {"scientific CONFIRMED": "green",
			  "NOT the scientific tuning": "red"}.get(res["verdict"], "yellow")
	print(Panel(Pretty(res), title=f"[{colour}]tuning file: {res['verdict']}"))
	try:
		Experiment.current.log_event("tuning_check", attribs=res)
		if res["verdict"] != "scientific CONFIRMED":
			Experiment.current.note(f"Tuning file check: {res['verdict']}. "
									f"libcamera_says={res.get('libcamera_says')}, "
									f"ccm_match={res.get('ccm_match')}")
	except Exception as e:
		log.error(f"tuning_check log failed: {e}")
	return res


def check_cam_temp():
	"""Is the camera-sensor temperature actually reported? Answered from real
	frames (the callback has seen ~50 by now), not from the libcamera source.
	Logged; never raises."""
	t = _cam_temp_c()
	ok = t != ""
	msg = (f"{t} degC -- SensorTemperature present" if ok else
		   "not in the frame metadata -- cam_temp_c stays blank")
	print(Panel(msg, title=f"[{'green' if ok else 'yellow'}]camera temperature"))
	try:
		Experiment.current.log_event("cam_temp_check",
									 attribs={"present": ok, "value": t})
	except Exception as e:
		log.error(f"cam_temp_check log failed: {e}")
	return ok


## --------------------------------------------------------------------------
##  Marks
## --------------------------------------------------------------------------

def mark(label=""):
	"""Timestamp a note into the experiment log.

	Usable before start_acq_blocking() or after it returns, NOT during --
	that call holds the interpreter.
	"""
	try:
		exp = Experiment.current
		t = time.time()
		exp.log_event("mark", attribs={"label": str(label),
									   "t": t,
									   "dt": str(datetime.datetime.now())})
		exp.note(f"MARK: {label}")
		print(Panel(f"[cyan]{datetime.datetime.now():%H:%M:%S}  {label}", title="mark"))
		return t
	except Exception as e:
		log.error(f"mark failed: {type(e).__name__}: {e}")
		return None


## --------------------------------------------------------------------------
##  Sensors
## --------------------------------------------------------------------------

## T&H is read by one thread only. The sensor sits behind the Pico's serial
## link, and two threads talking to it at once would interleave on the wire.
global _tandh, _tandh_at, _tandh_stop, _tandh_thread
_tandh, _tandh_at = None, 0.0
_tandh_stop = threading.Event()
_tandh_thread = None


def _tandh_loop(period_s):
	"""Read T&H every period_s into _tandh. Runs off the watchdog loop, so a
	slow serial reply cannot delay stall detection."""
	global _tandh, _tandh_at
	scope = ScopeAssembly.current
	while not _tandh_stop.is_set():
		t = time.monotonic()
		try:
			_tandh, _tandh_at = scope.tandh.read(), time.monotonic()
		except Exception as e:
			log.error(f"tandh read failed: {type(e).__name__}: {e}")
		_tandh_stop.wait(max(0.0, period_s - (time.monotonic() - t)))


def start_tandh(period_s):
	global _tandh_thread
	_tandh_stop.clear()
	_tandh_thread = threading.Thread(target=_tandh_loop, args=(period_s,),
									 daemon=True)
	_tandh_thread.start()


def stop_tandh():
	_tandh_stop.set()
	if _tandh_thread is not None:
		_tandh_thread.join(timeout=10)


def _tandh_now():
	"""(temp, humidity) from the last reading, blank if older than 5 s."""
	if not _tandh or time.monotonic() - _tandh_at > 5.0:
		return "", ""
	return _tandh.get("temp", ""), _tandh.get("humidity", "")


def record_sensor():
	"""Write the latest T&H reading to the tandh stream. Must never raise:
	this runs as a scheduled job, and ExpScheduler.loop has no try/except, so
	anything escaping here kills the scheduler thread and the rest of the run.

	Uses the T&H thread's last reading rather than reading the sensor, so the
	serial link only ever has one user."""
	try:
		tandh = Experiment.current.mstreams["tandh"]
		temp, hum = _tandh_now()
		if temp == "":
			print("[red]TandH reading failed![default]")
			temp, hum = 0, 0
		tandh(temp=temp, humidity=hum).panel()
	except Exception as e:
		log.error(f"record_sensor failed: {type(e).__name__}: {e}")


## --------------------------------------------------------------------------
##  Acquisition
## --------------------------------------------------------------------------

global stalls
stalls = 0


def _telemetry_row(w, t0, window):
	"""One row per poll. These eight numbers are what separate a camera-side
	stall from an encoder-side one: frames vs sink.frames vs queue depth vs
	output-thread liveness."""
	global encoder, sink, scope
	try:
		cam = scope.cam.cam
		w.writerow([round(time.time(), 3),
					round(time.monotonic() - t0, 2),
					window,
					cam.frames,
					sink.frames,
					encoder.tasks.qsize(),
					int(encoder.thread.is_alive()) if getattr(encoder, "thread", None) else -1,
					_rss_mb(),
					_cma_free_mb(),
					_temp_c(),
					_throttled(),
					_csi_irq(),
					_cam_temp_c(),
					*_tandh_now(),
					_boot_ns()])
	except Exception as e:
		log.error(f"telemetry row failed: {type(e).__name__}: {e}")


def _boot_ns():
	"""The clock SensorTimestamp is on (CLOCK_BOOTTIME), so each row pairs it
	with the wall clock and t_ns in intensities.csv maps onto wall time."""
	try:
		return time.clock_gettime_ns(time.CLOCK_BOOTTIME)
	except (AttributeError, OSError):
		return time.monotonic_ns()


def start_acq_blocking():
	"""Run the camera continuously, recording intensity and watching for stalls.

	Blocks until run_hours elapses or Ctrl-C. Everything is written as it goes,
	so an interrupted run keeps whatever it collected.
	"""
	global exp, scope, encoder, sink, stalls, intens_path, telem_path

	exp = Experiment.current
	scope = ScopeAssembly.current
	a = exp.attribs

	intens_path = exp.newfile("intensities.csv", abspath=False)
	telem_path = exp.newfile("telemetry.csv", abspath=False)
	with open(intens_path, "w", newline="") as f:
		csv.writer(f).writerow(["t_ns", "r", "g", "b"])
	with open(telem_path, "w", newline="") as f:
		csv.writer(f).writerow(["wall", "elapsed_s", "window", "cam_frames",
								"sink_frames", "queue", "out_thread_alive",
								"rss_mb", "cma_free_mb", "temp_c", "throttled",
								"csi_irq", "cam_temp_c", "tandh_temp",
								"tandh_rh", "boot_ns"])

	print("[red]Clearing experiment scheduler...")
	exp.schedule.clear()

	start_kernel_log()
	scope.lit.setVs(*a["light"])
	scope.beacon.on()
	## Only after the last set-up command to the Pico: from here on the T&H
	## thread is the serial link's only user until stop_tandh().
	start_tandh(a["tandh_poll_s"])
	cam_cycle()
	start_recording()
	time.sleep(2.0)             # let AWB settle so the reported CT is meaningful
	verify_tuning()
	check_cam_temp()

	record_sensor()
	exp.schedule.every(a["tandh_sampling_period_minutes"]).minutes \
		.until(timedelta(hours=a["run_hours"] + 1)).do(record_sensor)

	exp.logs.update(scope.get_config())
	exp.__save__()

	t0 = time.monotonic()
	deadline = t0 + a["run_hours"] * 3600.0
	window = 0
	next_window = t0 + a["flush_interval_s"]
	last_n, last_t = scope.cam.cam.frames, time.monotonic()

	print(Panel(f"Recording intensity for [bold]{a['run_hours']} h[/bold].\n"
				f"No video is written. Shake the scope whenever you like and "
				f"call [bold]mark(\"shake\")[/bold] to timestamp it.\n"
				f"Ctrl-C stops cleanly.", title="intensity_continuous"))

	tele = open(telem_path, "a", newline="")
	w = csv.writer(tele)
	try:
		while time.monotonic() < deadline:
			time.sleep(a["poll_s"])
			_telemetry_row(w, t0, window)
			tele.flush()

			if time.monotonic() >= next_window:
				window += 1
				next_window = time.monotonic() + a["flush_interval_s"]

			## Stall detection. cam.frames counts only requests libcamera
			## completed successfully, so it standing still is the one honest
			## signal that the camera has stopped -- there is no exception and
			## cam.is_open stays True throughout.
			cam = scope.cam.cam
			n = cam.frames
			if n != last_n:
				last_n, last_t = n, time.monotonic()
				continue
			if time.monotonic() - last_t < a["stall_s"]:
				continue

			stalls += 1
			stalled_at = round(time.monotonic() - t0, 2)
			reason, tail = stall_reason()
			snap = snapshot(f"{stalls:03d}")
			log.error(f"STALL #{stalls} at {stalled_at}s: {reason}")
			print(Panel(f"[red]STALL #{stalls} at {stalled_at:.0f}s -- {reason}\n"
						f"{tail.strip()[-300:]}", title="camera stall"))
			exp.log_event("camera_stall", attribs={
				"n": stalls, "reason": reason, "stalled_at_s": stalled_at,
				"frames_before": int(n), "snapshot": snap})

			t_rec = time.monotonic()
			level, ok = 0, False
			for attempt in range(1, a["max_recovery_attempts"] + 1):
				level, ok = recover(window)
				if ok:
					break
				log.error(f"recovery attempt {attempt} failed")
				time.sleep(2.0)
			recover_s = round(time.monotonic() - t_rec, 2)

			try:
				exp.mstreams["stalls"](n=stalls, reason=reason, level=level,
									   recovered=bool(ok),
									   stalled_at_s=stalled_at,
									   recover_s=recover_s,
									   frames_before=int(n)).panel()
			except Exception as e:
				log.error(f"stall stream write failed: {e}")

			exp.log_event("camera_recovery", attribs={
				"n": stalls, "level": level, "recovered": bool(ok),
				"recover_s": recover_s})

			if not ok:
				exp.note(f"Camera could not be recovered after stall #{stalls}. "
						 f"Telemetry and tandh continue; video pipeline is down.")
				print(Panel("[red]Camera not recovered. The run continues so the "
							"rest of the record is kept, but no further "
							"intensity will be collected.", title="recovery"))
				break

			## A new Picamera2 restarts its own frame counter.
			last_n, last_t = scope.cam.cam.frames, time.monotonic()

	except KeyboardInterrupt:
		print("\n[yellow]Interrupted. Finishing cleanly...")
	finally:
		try:
			tele.close()
		except Exception:
			pass
		stop_kernel_log()
		stop_tandh()            # before anything else talks to the Pico
		drain_encoder(window)
		try:
			scope.cam.cam.stop_recording()
		except Exception as e:
			log.error(f"stop_recording at end: {e}")
		try:
			scope.cam.close()
		except Exception as e:
			log.error(f"camera close at end: {e}")
		scope.beacon.off()

	print(Panel(f"frames discarded : {sink.frames}\n"
				f"intensity rows   : {csv_rows}\n"
				f"stalls           : {stalls}\n"
				f"elapsed          : {(time.monotonic() - t0) / 3600.0:.2f} h",
				title="run complete"))

	## ExpScheduler.loop is `while not self.end_thread`, and nothing else sets
	## that flag -- without this the scheduler thread spins forever and the
	## process never exits, which is exactly what left eight experiments open
	## for two days on 2026-11-09.
	cleanup()


## --------------------------------------------------------------------------
##  Kernel message stream
## --------------------------------------------------------------------------

global _dmesg_proc
_dmesg_proc = None


def start_kernel_log():
	"""Stream kernel messages to kernel.log for the whole run.

	`dmesg --follow` rather than periodic snapshots: the ring buffer holds a
	bounded number of lines and a 16 h run can wrap it, losing exactly the
	early messages that would explain a late failure. Following it also
	timestamps each line as it arrives, so a kernel event can be lined up
	against the inter-frame gaps -- which otherwise have no explanation
	attached to them at all.
	"""
	global _dmesg_proc
	## stdbuf -oL: dmesg block-buffers when its stdout is a file rather than a
	## tty, so without this the last few kilobytes of kernel messages sit
	## unflushed and are lost when the process is terminated -- precisely the
	## messages written just before a failure.
	for cmd in (["stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["sudo", "-n", "stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["dmesg", "--follow", "-T"]):
		f = None
		try:
			f = open("kernel.log", "a", buffering=1)
			_dmesg_proc = subprocess.Popen(cmd, stdout=f,
										   stderr=subprocess.STDOUT)
			## Liveness alone is too weak: `sudo -n ...` stays alive briefly
			## before failing, and a restricted dmesg writes its refusal and
			## exits. Require the process to still be running AND the log to
			## be free of the refusals those two produce.
			time.sleep(0.8)
			refused = ""
			try:
				with open("kernel.log", errors="replace") as r:
					refused = r.read()[-400:]
			except Exception:
				pass
			bad = re.search(r"operation not permitted|password is required|"
							r"not found|read kernel buffer failed|"
							r"invalid option|unrecognized", refused, re.I)
			if _dmesg_proc.poll() is None and not bad:
				log.info(f"Kernel log streaming via: {' '.join(cmd)}")
				return True
			if bad:
				log.error(f"kernel log refused ({cmd[0]}): {bad.group(0)}")
			try:
				_dmesg_proc.terminate()
				_dmesg_proc.wait(timeout=3)
			except Exception:
				pass
			_dmesg_proc = None
		except Exception as e:
			log.error(f"kernel log start failed ({cmd[0]}): {e}")
		finally:
			## The child holds its own dup of the descriptor, so closing ours
			## is correct whether or not the attempt succeeded -- and without
			## it each failed candidate leaks a handle.
			if f is not None:
				try:
					f.close()
				except Exception:
					pass
	log.error("kernel.log unavailable (dmesg restricted and sudo -n refused)")
	return False


def stop_kernel_log():
	global _dmesg_proc
	if _dmesg_proc is None:
		return
	try:
		_dmesg_proc.terminate()
		_dmesg_proc.wait(timeout=5)
	except Exception:
		try:
			_dmesg_proc.kill()
		except Exception:
			pass
	_dmesg_proc = None


## --------------------------------------------------------------------------
##  End-of-run statistics
## --------------------------------------------------------------------------

def run_stats():
	"""Summarise the run from the two CSVs it just wrote.

	The inter-frame gap distribution is the point. A 2 s stall is caught live
	by the monitor, but a marginal camera shows up long before that as a tail
	of 100-500 ms gaps that nothing else in this script would notice. Over a
	million frames that tail is either there or it is not.
	"""
	out = {}
	try:
		## --- gaps, streamed: 1.4 M rows will not be held in memory ---------
		gaps, prev, n, nan = [], None, 0, 0
		with open(intens_path) as f:
			r = csv.reader(f)
			next(r, None)
			for row in r:
				n += 1
				try:
					t = int(row[0])
				except (ValueError, IndexError):
					nan += 1
					continue
				if prev is not None and t > prev:
					gaps.append((t - prev) / 1e6)      # ns -> ms
				prev = t
		if gaps:
			g = np.array(gaps)
			nominal = 1000.0 / Experiment.current.attribs["fps"]
			out["frames_csv"] = n
			out["gap_ms_p50"] = round(float(np.percentile(g, 50)), 3)
			out["gap_ms_p99"] = round(float(np.percentile(g, 99)), 3)
			out["gap_ms_max"] = round(float(g.max()), 1)
			out["gaps_over_100ms"] = int((g > 100).sum())
			out["gaps_over_500ms"] = int((g > 500).sum())
			out["gaps_over_2s"] = int((g > 2000).sum())
			## A dropped frame is a gap that is a multiple of the nominal
			## interval; this counts the frames missing from those gaps.
			out["frames_missing"] = int(np.maximum(
				np.round(g / nominal) - 1, 0).sum())
			out["fps_effective"] = round(1000.0 * len(g) / float(g.sum()), 4)

		## --- telemetry ------------------------------------------------------
		cols = {k: [] for k in ("cam_frames", "sink_frames", "queue",
								"rss_mb", "cma_free_mb", "temp_c", "csi_irq",
								"cam_temp_c", "tandh_temp")}
		thr = set()
		with open(telem_path) as f:
			for row in csv.DictReader(f):
				for k in cols:
					try:
						cols[k].append(float(row[k]))
					except (ValueError, KeyError, TypeError):
						pass
				thr.add(row.get("throttled", ""))
		if cols["cam_frames"]:
			out["cam_frames_final"] = int(cols["cam_frames"][-1])
			out["sink_frames_final"] = int(cols["sink_frames"][-1])
			out["encoder_shortfall"] = out["cam_frames_final"] - out["sink_frames_final"]
			out["queue_max"] = int(max(cols["queue"]))
			out["rss_mb_start"] = cols["rss_mb"][0]
			out["rss_mb_end"] = cols["rss_mb"][-1]
			out["rss_mb_growth"] = round(cols["rss_mb"][-1] - cols["rss_mb"][0], 1)
			out["cma_free_mb_min"] = min(cols["cma_free_mb"])
			if cols["temp_c"]:
				out["temp_c_max"] = max(cols["temp_c"])
				out["temp_c_mean"] = round(sum(cols["temp_c"]) / len(cols["temp_c"]), 1)
			for k in ("cam_temp_c", "tandh_temp"):
				if cols[k]:
					out[f"{k}_min"] = min(cols[k])
					out[f"{k}_max"] = max(cols[k])
					out[f"{k}_mean"] = round(sum(cols[k]) / len(cols[k]), 2)
				else:
					out[f"{k}_rows"] = 0
			if cols["csi_irq"] and cols["csi_irq"][0] >= 0:
				out["csi_irq_total"] = int(cols["csi_irq"][-1] - cols["csi_irq"][0])
		out["throttled_values"] = sorted(v for v in thr if v and v != "?")
		try:
			if os.path.exists("kernel.log"):
				with open("kernel.log", errors="replace") as f:
					lines = f.readlines()
				out["kernel_lines"] = len(lines)
				out["kernel_errors"] = sum(
					1 for l in lines if re.search(
						r"error|fail|timed out|reset|under-volt|oom", l, re.I))
			else:
				out["kernel_lines"] = -1
		except Exception as e:
			log.error(f"kernel.log summary failed: {e}")
		out["stalls"] = stalls
	except Exception as e:
		log.error(f"run_stats failed: {type(e).__name__}: {e}")
		out["error"] = f"{type(e).__name__}: {e}"
	return out


def collect_diagnostics():
	"""Run the standalone system collector into this experiment.

	Shelling out to scripts/debug/collect_diagnostics.py rather than
	reimplementing: it already captures the full dmesg, both journals, the
	libcamera errors, throttle bits, CMA and the camera enumeration, and it
	imports nothing from this framework so it still works if the framework is
	what broke.
	"""
	for root in (os.getcwd(), os.path.expanduser("~/trappyscopes"),
				 os.path.dirname(os.path.dirname(os.path.dirname(
					 os.path.abspath(__file__))))):
		script = os.path.join(root, "scripts", "debug", "collect_diagnostics.py")
		if os.path.exists(script):
			log.info(f"Collecting system diagnostics with {script}")
			out = _run(f'python3 "{script}" --out diagnostics '
					   f'--exp-dir "{os.getcwd()}" --no-tar', timeout=300)
			print(Panel(out.strip()[-600:] or "(no output)",
						title="system diagnostics"))
			return True
	log.error("collect_diagnostics.py not found; skipping system diagnostics")
	return False


def cleanup():
	"""Save, offload and stop the schedule. Does NOT close the experiment --
	exp.close() joins the scheduler thread, so it cannot be called from one.
	Type exp.close() afterwards."""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	try:
		scope.lit.setVs(0, 0, 0)
	except Exception as e:
		log.error(f"lights off failed: {e}")

	## The libcamera log lives outside the experiment because it has to exist
	## before the experiment does. Copy it in so the bundle is self-contained.
	try:
		src = os.environ.get("LIBCAMERA_LOG_FILE", LIBCAMERA_LOG)
		if os.path.exists(src):
			shutil.copy2(src, "libcamera.log")
	except Exception as e:
		log.error(f"libcamera log copy failed: {e}")

	stats = run_stats()
	try:
		with open("run_stats.yaml", "w") as f:
			for k, v in stats.items():
				f.write(f"{k}: {v}\n")
	except Exception as e:
		log.error(f"run_stats write failed: {e}")
	exp.log_event("run_stats", attribs=stats)
	print(Panel(Pretty(stats), title="run statistics"))

	collect_diagnostics()

	exp.logs.update(scope.get_config())
	exp.schedule.clear()
	exp.schedule.end_thread = True
	exp.__save__()
	try:
		print(exp.mstreams["stalls"].tabulate("n", "reason", "level",
											  "recovered", "recover_s"))
	except Exception:
		pass
	exp.sync_dir()
	exp.note("Intensity run offloaded and schedule stopped. Experiment left open")
	print(Panel("[yellow]Offloaded, schedule stopped.\n"
				"The experiment is still OPEN. Type [bold]exp.close()[/bold] "
				"to finish it.", title="cleanup"))


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	print("Lights ready...")
	cam_cycle()
	scope.beacon.off()
	print(Panel(f'create_exp() -> start_acq_blocking()\n\n'
				f'mark("shake start") to timestamp a disturbance.\n'
				f'cleanup() then exp.close() when done.\n\n'
				f'libcamera log: {os.environ.get("LIBCAMERA_LOG_FILE")}',
				title="intensity_continuous"))
