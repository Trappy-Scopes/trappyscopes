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

import datetime
import logging as log
import os
import subprocess
import threading
import time
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from picamera2.request import MappedArray

from core.precision.timing import precise_sleep
from detectors.cameras.rpi_hq_picam2 import JpegEncoderGrayRedCh
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


__description__ = \
"""Live bead-flow speed estimate on the grayscale preview, recorded for validation.

Records MJPEG clips of beads in traps while a coarse flow speed is estimated
live and printed over the red-channel (grayscale) preview. The clips are the
validation set: the offline analysis (adaptive lag, Kalman, expansion fit)
runs on them later and is compared with the live estimate logged here. The
other output is performance -- camera fps, dropped frames, estimator rate,
latency, CPU load and temperature -- to find where the live pipeline breaks.

    create_exp("beads_1_3_6_10um")   open the experiment
    goto_trap("AF7")                 name the trap; live preview + estimate
                                     to focus (Ctrl-C to stop), not recorded
    record_trap()                    one clip per mode for that trap
    ...goto_trap / record_trap for each trap...
    cleanup()                        lights off, save, sync
    exp.close()

Modes, recorded in this order for every trap, to isolate failures:

    record                     MJPEG only. Baseline encoder cost.
    record_preview             + grayscale DRM preview.
    record_preview_estimate    + live speed estimate and overlay.

Comparing dropped frames (from each clip's .tpts) across the three says
whether frames are lost to the encoder, the preview or the estimator.

What reaches the recording
--------------------------
The grayscale preview copies red into green and blue in post_callback, which
runs before the encoder (see Camera.rpreview). The recording uses
JpegEncoderGrayRedCh, which keeps only red, so the clip is unchanged.
JpegEncoderRedWithBGStats must NOT be used here: its green/blue means would
be copies of red. The overlay goes through set_overlay(), which is
composited by the preview only and never reaches the encoder.

Live estimate
-------------
Coarse by design. The red channel is decimated (analysis_step) and cropped
to the centre of the frame (roi_frac), i.e. inside the trap. The frame is
tiled, each tile is phase-correlated against the frame `lag` frames earlier,
and the median displacement of the confident tiles is the speed. The lag
adapts so beads move ~target_px per pair: sub-pixel shifts are at the noise
floor, so a slow flow needs frames further apart. Frame times are sensor
timestamps, not the nominal fps. No background subtraction, no temporal
filtering, no expansion -- that is the offline analysis' job.

Exposure
--------
exp.attribs["exposure_ms"] in other scripts is not applied to the camera. The
values recorded here are read from the camera configuration and from the
frame metadata of every clip.
"""


## --------------------------------------------------------------------------
##  Constants
## --------------------------------------------------------------------------

## IMX477 2x2 binned (2028x1520, cropped to 1520x1520): 1.55 um x 2.
SENSOR_PIXEL_UM = 3.1

## Used only when the scope has no magnification on record. Measured value for
## M5, logged in its experiment.yaml (optics.magnification) on 2026-08-28.
DEFAULT_MAGNIFICATION = 1.5699

MODES = ("record", "record_preview", "record_preview_estimate")


## --------------------------------------------------------------------------
##  Setup
## --------------------------------------------------------------------------

def magnification():
	"""(magnification, source). Reads the scope's optics if it has one."""
	scope = ScopeAssembly.current
	for source, get in (("scope.optics", lambda: scope.optics["magnification"]),
						("scope.optics.attribs", lambda: scope.optics.attribs["magnification"])):
		try:
			return float(get()), source
		except Exception:
			pass
	return DEFAULT_MAGNIFICATION, "DEFAULT_MAGNIFICATION (no value on the scope)"


def create_exp(label="beads"):
	"""Open the experiment. The label goes into the experiment name."""
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["bead_flow_speed", label])

	exp.new_measurementstream("acq", monitors=["acq"])
	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])

	## One row per clip. Per-estimate rows go to a CSV beside the clip -- a
	## MeasurementStream call is a YAML write to disk.
	exp.new_measurementstream("flowlive",
		monitors=["split", "trap", "mode", "acq", "csv", "frames", "dropped",
				  "estimates", "throttled"],
		measurements=["cam_fps", "est_hz", "latency_ms", "proc_ms", "lag",
					  "speed_med", "speed_last", "valid_frac",
					  "cpu_mean", "cpu_max", "temp_max", "load1",
					  "exposure_us", "frame_duration_us"])

	## Recording
	exp.attribs["chunk_size_sec"] = 60
	exp.attribs["clips_per_mode"] = 1
	exp.attribs["modes"] = list(MODES)
	exp.attribs["quality"] = 100
	exp.attribs["num_threads"] = 3
	exp.attribs["light"] = (0.5, 0, 0)
	exp.attribs["light_stabilization_delay_s"] = 1
	exp.attribs["beacon_stabilization_delay_s"] = 1
	exp.attribs["sync_files"] = True

	## What the camera actually runs at -- read from its configuration, not set
	## here. Each clip also logs the exposure from the frame metadata.
	ctrl = scope.cam.controls
	exp.attribs["exposure_ms"] = ctrl["ExposureTime"] / 1000
	exp.attribs["analogue_gain"] = ctrl["AnalogueGain"]
	exp.attribs["frame_duration_us"] = int(ctrl["FrameDurationLimits"][1])
	exp.attribs["fps"] = 1e6 / exp.attribs["frame_duration_us"]
	exp.attribs["resolution"] = tuple(scope.cam.config["main"]["size"])

	## Calibration: um per full-resolution pixel
	mag, source = magnification()
	exp.attribs["magnification"] = mag
	exp.attribs["magnification_source"] = source
	exp.attribs["sensor_pixel_um"] = SENSOR_PIXEL_UM
	exp.attribs["um_per_px"] = SENSOR_PIXEL_UM / mag

	## Live estimator
	exp.attribs["analysis_step"] = 2      ## decimation: 1520 -> 760 px
	exp.attribs["roi_frac"] = 0.7         ## central crop, inside the trap
	exp.attribs["win"] = 64               ## tile size (analysis px)
	exp.attribs["target_px"] = 2.0        ## displacement per pair to aim for
	exp.attribs["lag_max"] = 50           ## frames; memory ~ lag_max x 280 kB
	exp.attribs["est_rate_hz"] = 5        ## estimates per second, at most
	exp.attribs["min_peak_ratio"] = 1.3   ## tile kept if peak / 2nd peak >= this

	exp.attribs["trap"] = None
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))
	if source.startswith("DEFAULT"):
		print(Panel(f"[yellow]No magnification on this scope. Using "
					f"{DEFAULT_MAGNIFICATION} (M5). Every um/s scales with it.",
					title="calibration"))
		exp.note(f"Magnification not found on the scope; using default "
				 f"{DEFAULT_MAGNIFICATION}.")


## --------------------------------------------------------------------------
##  Camera
## --------------------------------------------------------------------------

def cam_cycle():
	"""close -> open -> configure, leaving the camera open and configured.

	Same as light_perturbation.cam_cycle(): Camera.open() assigns a new
	Picamera2 without closing the old one, and open() does not apply
	self.config, so always close first and configure explicitly. Callbacks
	and the overlay are cleared so an interrupted clip cannot leak its
	grayscale copy or its text into the next one.
	"""
	global scope
	scope = ScopeAssembly.current
	for stop in (lambda: scope.cam.cam.stop_recording(),
				 lambda: scope.cam.cam.stop(),
				 lambda: scope.cam.cam.set_overlay(None),
				 lambda: scope.cam.cam.stop_preview()):
		try:
			stop()
		except Exception:
			pass          ## not running: nothing to stop
	scope.cam.close()
	scope.cam.open()
	scope.cam.configure()
	scope.cam.cam.pre_callback = None
	scope.cam.cam.post_callback = None


def make_post_callback(gray=False, live=None):
	"""post_callback for a clip: grayscale preview and/or frame grab.

	gray: copy red into green and blue (the rpreview trick). Harmless to a
	red-only encoder; see __description__.
	live: a LiveFlow that is handed every frame.
	"""
	def callback(request):
		with MappedArray(request, "main") as m:
			if live is not None:
				try:
					t_ns = request.get_metadata()["SensorTimestamp"]
				except Exception:
					t_ns = time.monotonic_ns()
				live.push(m.array, t_ns)
			if gray:
				m.array[..., 1] = m.array[..., 0]
				m.array[..., 2] = m.array[..., 0]
	return callback


## --------------------------------------------------------------------------
##  Live estimator
## --------------------------------------------------------------------------

class LiveFlow:
	"""Coarse live flow speed from the red channel.

	push() runs on the camera thread for every frame and only stores a
	decimated crop. The estimate runs on its own thread at est_rate_hz, so
	a slow estimate skips frames instead of holding up the camera.
	"""

	COLUMNS = ("t_sensor_ns", "t_mono_ns", "lag", "dt_s", "dx_px", "dy_px",
			   "vx_um_s", "vy_um_s", "speed_um_s", "n_valid", "n_tiles",
			   "peak_ratio_med", "proc_ms", "latency_ms", "cam_fps")

	def __init__(self, shape, um_per_px, step=2, roi_frac=0.7, win=64,
				 target_px=2.0, lag_max=50, rate_hz=5, min_peak_ratio=1.3,
				 overlay=None):
		H, W = shape[:2]
		ch, cw = int(H * roi_frac), int(W * roi_frac)
		## crop so the decimated ROI is a whole number of tiles
		ch -= ch % (step * win)
		cw -= cw % (step * win)
		self.y0, self.x0 = (H - ch) // 2, (W - cw) // 2
		self.y1, self.x1 = self.y0 + ch, self.x0 + cw
		self.ny, self.nx = ch // step // win, cw // step // win
		self.decim, self.win = step, win
		self.um_per_px = um_per_px * step       ## analysis pixel
		self.target_px, self.lag_max = target_px, lag_max
		self.period = 1.0 / rate_hz
		self.min_peak_ratio = min_peak_ratio
		self.max_px = win / 4
		self.overlay = overlay                  ## callable(lines) or None
		w1 = np.hanning(win).astype(np.float32)
		self.window = np.outer(w1, w1)

		self._frames = deque(maxlen=lag_max + 2)   ## (t_sensor_ns, t_mono_ns, img)
		self._sensor_t = deque(maxlen=26)          ## for the live fps readout
		self._lock = threading.Lock()
		self._stop = threading.Event()
		self._thread = None
		self._px_per_frame = None
		self.records = []

	## camera thread -------------------------------------------------------
	def push(self, arr, t_ns):
		img = arr[self.y0:self.y1:self.decim, self.x0:self.x1:self.decim, 0].copy()
		with self._lock:
			self._frames.append((t_ns, time.monotonic_ns(), img))
			self._sensor_t.append(t_ns)

	## estimator thread ----------------------------------------------------
	def start(self):
		self._stop.clear()
		self._thread = threading.Thread(target=self._run, daemon=True,
										name="liveflow")
		self._thread.start()

	def stop(self):
		self._stop.set()
		if self._thread is not None:
			self._thread.join(timeout=5)

	def cam_fps(self):
		with self._lock:
			t = list(self._sensor_t)
		if len(t) < 2:
			return float("nan")
		return (len(t) - 1) / ((t[-1] - t[0]) / 1e9)

	def _tiles(self, img):
		w = self.win
		t = img.reshape(self.ny, w, self.nx, w).swapaxes(1, 2).astype(np.float32)
		t -= t.mean(axis=(2, 3), keepdims=True)
		return np.fft.rfft2(t * self.window)

	def tile_shifts(self, a, b):
		"""Displacement (dy, dx) of every tile from a to b, in pixels, and the
		peak-to-second-peak ratio of each correlation."""
		w = self.win
		R = self._tiles(b) * np.conj(self._tiles(a))
		R /= np.abs(R) + 1e-9
		r = np.fft.fftshift(np.fft.irfft2(R, s=(w, w)), axes=(2, 3))
		r = r.reshape(-1, w, w)
		n = r.shape[0]
		flat = r.reshape(n, -1)
		k = flat.argmax(axis=1)
		py, px = np.divmod(k, w)
		idx = np.arange(n)
		peak = flat[idx, k]

		## sub-pixel: 3-point parabola (neighbours wrap)
		def sub(c, m, p):
			den = m - 2 * c + p
			return np.where(np.abs(den) > 1e-12, 0.5 * (m - p) / den, 0.0)
		sy = sub(peak, r[idx, (py - 1) % w, px], r[idx, (py + 1) % w, px])
		sx = sub(peak, r[idx, py, (px - 1) % w], r[idx, py, (px + 1) % w])

		## second peak outside the 5x5 neighbourhood of the first
		masked = r.copy()
		for d in range(-2, 3):
			for e in range(-2, 3):
				masked[idx, (py + d) % w, (px + e) % w] = -np.inf
		second = masked.reshape(n, -1).max(axis=1)
		ratio = peak / np.maximum(second, 1e-9)

		dy = py - w // 2 + sy
		dx = px - w // 2 + sx
		return dy, dx, ratio

	def _choose_lag(self, available):
		if self._px_per_frame is None:
			want = 1
		else:
			want = self.target_px / max(self._px_per_frame, 1e-6)
		return int(np.clip(round(want), 1, min(self.lag_max, available)))

	def _run(self):
		while not self._stop.wait(self.period):
			try:
				self.step()
			except Exception as e:      ## never kill the thread mid-clip
				log.error(f"LiveFlow estimate failed: {e}")

	def step(self):
		"""One estimate from the newest frame. Returns the row, or None."""
		with self._lock:
			frames = list(self._frames)
		if len(frames) < 2:
			return None
		tic = time.perf_counter()
		lag = self._choose_lag(len(frames) - 1)
		t1, m1, b = frames[-1]
		t0, _, a = frames[-1 - lag]
		dt = (t1 - t0) / 1e9
		if dt <= 0:
			return None
		dy, dx, ratio = self.tile_shifts(a, b)
		ok = (ratio >= self.min_peak_ratio) & (np.hypot(dy, dx) <= self.max_px)
		n_valid = int(ok.sum())
		if n_valid >= 3:
			mdy, mdx = float(np.median(dy[ok])), float(np.median(dx[ok]))
			d = float(np.hypot(mdy, mdx))
			if d > 0.8 * self.max_px:
				self._px_per_frame = 2 * d / lag    ## near aliasing: back off
			else:
				ppf = d / lag
				self._px_per_frame = ppf if self._px_per_frame is None \
									 else 0.7 * self._px_per_frame + 0.3 * ppf
		else:
			mdy = mdx = float("nan")
			## nothing confident: often too large a shift, so shorten
			if self._px_per_frame is not None:
				self._px_per_frame *= 2
		k = self.um_per_px / dt
		vx, vy = mdx * k, mdy * k
		now = time.monotonic_ns()
		row = dict(t_sensor_ns=t1, t_mono_ns=now, lag=lag, dt_s=dt,
				   dx_px=mdx, dy_px=mdy, vx_um_s=vx, vy_um_s=vy,
				   speed_um_s=float(np.hypot(vx, vy)), n_valid=n_valid,
				   n_tiles=int(ok.size),
				   peak_ratio_med=float(np.median(ratio)),
				   proc_ms=(time.perf_counter() - tic) * 1e3,
				   latency_ms=(now - m1) / 1e6, cam_fps=self.cam_fps())
		self.records.append(row)
		if self.overlay is not None:
			self.overlay(self._lines(row))
		return row

	def est_hz(self):
		if len(self.records) < 2:
			return float("nan")
		t = [r["t_mono_ns"] for r in self.records[-10:]]
		return (len(t) - 1) / ((t[-1] - t[0]) / 1e9)

	def _lines(self, row):
		speed = "  --  " if np.isnan(row["speed_um_s"]) else f"{row['speed_um_s']:6.2f}"
		return [f"speed {speed} um/s",
				f"cam {row['cam_fps']:5.1f} fps   est {self.est_hz():4.1f} Hz",
				f"lag {row['lag']:3d} fr   {row['latency_ms']:4.0f} ms   "
				f"tiles {row['n_valid']}/{row['n_tiles']}"]

	def write_csv(self, filename):
		with open(filename, "w") as f:
			f.write(",".join(self.COLUMNS) + "\n")
			for r in self.records:
				f.write(",".join(f"{r[c]:.6g}" if isinstance(r[c], float) else str(r[c])
								 for c in self.COLUMNS) + "\n")

	EMPTY_SUMMARY = dict(estimates=0, est_hz=float("nan"), latency_ms=float("nan"),
						 proc_ms=float("nan"), lag=float("nan"), speed_med=float("nan"),
						 speed_last=float("nan"), valid_frac=float("nan"))

	def summary(self):
		if not self.records:
			return dict(self.EMPTY_SUMMARY)
		col = lambda c: np.array([r[c] for r in self.records], dtype=float)
		t = col("t_mono_ns")
		speed = col("speed_um_s")
		good = speed[np.isfinite(speed)]
		return dict(estimates=len(self.records),
					est_hz=(len(t) - 1) / ((t[-1] - t[0]) / 1e9) if len(t) > 1 else float("nan"),
					latency_ms=float(np.median(col("latency_ms"))),
					proc_ms=float(np.median(col("proc_ms"))),
					lag=float(np.median(col("lag"))),
					speed_med=float(np.median(good)) if good.size else float("nan"),
					speed_last=float(good[-1]) if good.size else float("nan"),
					valid_frac=float(np.mean(col("n_valid") / col("n_tiles"))))


def text_overlay(cam, size=(760, 760)):
	"""Returns lines -> set_overlay(). Text only, top-left, on a dark box.
	Composited by the preview; never reaches the encoder."""
	try:
		font = ImageFont.load_default(size=size[1] // 26)
	except TypeError:                         ## Pillow < 10.1
		font = ImageFont.load_default()

	def draw(lines):
		img = Image.new("RGBA", size, (0, 0, 0, 0))
		d = ImageDraw.Draw(img)
		pad, lh = 10, size[1] // 22
		box_w = max(int(d.textlength(s, font=font)) for s in lines) + 2 * pad
		d.rectangle((0, 0, box_w, pad * 2 + lh * len(lines)), fill=(0, 0, 0, 170))
		for i, s in enumerate(lines):
			d.text((pad, pad + i * lh), s, font=font, fill=(255, 255, 80, 255))
		try:
			cam.set_overlay(np.asarray(img))
		except Exception as e:
			log.error(f"set_overlay failed: {e}")
	return draw


## --------------------------------------------------------------------------
##  System monitor
## --------------------------------------------------------------------------

class SysMonitor:
	"""CPU use, SoC temperature and load, sampled every `period` s."""

	def __init__(self, period=1.0):
		self.period = period
		self.cpu, self.temp, self.load = [], [], []
		self._stop = threading.Event()
		self._thread = None

	@staticmethod
	def _cpu_times():
		with open("/proc/stat") as f:
			v = [int(x) for x in f.readline().split()[1:]]
		idle = v[3] + v[4]
		return idle, sum(v)

	def _run(self):
		try:
			prev = self._cpu_times()
		except Exception:
			prev = None
		while not self._stop.wait(self.period):
			try:
				cur = self._cpu_times()
				if prev:
					d_idle, d_tot = cur[0] - prev[0], cur[1] - prev[1]
					self.cpu.append(100.0 * (1 - d_idle / max(d_tot, 1)))
				prev = cur
			except Exception:
				pass
			try:
				with open("/sys/class/thermal/thermal_zone0/temp") as f:
					self.temp.append(int(f.read()) / 1000)
			except Exception:
				pass
			try:
				self.load.append(os.getloadavg()[0])
			except Exception:
				pass

	def start(self):
		self._thread = threading.Thread(target=self._run, daemon=True, name="sysmon")
		self._thread.start()

	def stop(self):
		self._stop.set()
		if self._thread is not None:
			self._thread.join(timeout=3)

	def summary(self):
		f = lambda v, fn: float(fn(v)) if v else float("nan")
		try:
			throttled = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
									   text=True, timeout=2).stdout.strip()
		except Exception:
			throttled = "n/a"
		return dict(cpu_mean=f(self.cpu, np.mean), cpu_max=f(self.cpu, np.max),
					temp_max=f(self.temp, np.max), load1=f(self.load, np.max),
					throttled=throttled)


def tpts_stats(tpts_filename, frame_duration_us):
	"""(frames, measured fps, dropped frames) from a picamera2 .tpts file
	(timecode format v2: one timestamp in ms per line)."""
	try:
		with open(tpts_filename) as f:
			t = np.array([float(s) for s in f if s.strip() and not s.startswith("#")])
	except Exception as e:
		log.error(f"Could not read {tpts_filename}: {e}")
		return 0, float("nan"), -1
	if t.size < 2:
		return int(t.size), float("nan"), 0
	dt = np.diff(t)
	nominal = frame_duration_us / 1000
	dropped = int(np.sum(np.maximum(np.round(dt / nominal) - 1, 0)))
	fps = (t.size - 1) / ((t[-1] - t[0]) / 1000)
	return int(t.size), float(fps), dropped


## --------------------------------------------------------------------------
##  Acquisition
## --------------------------------------------------------------------------

global split_no
split_no = 0


def filename_fn(split_no, trap, mode):
	global exp
	stamp = str(datetime.datetime.now()).split(".")[0] \
			.replace(" ", "__").replace(":", "_").replace("-", "_")
	return exp.newfile(f"{stamp}__{time.time_ns()}__{trap}__{mode}__split_{split_no}.mjpeg",
					   abspath=False)


def new_liveflow(cam):
	a = Experiment.current.attribs
	H, W = a["resolution"][1], a["resolution"][0]
	return LiveFlow((H, W), a["um_per_px"], step=a["analysis_step"],
					roi_frac=a["roi_frac"], win=a["win"], target_px=a["target_px"],
					lag_max=a["lag_max"], rate_hz=a["est_rate_hz"],
					min_peak_ratio=a["min_peak_ratio"], overlay=text_overlay(cam))


def goto_trap(trap, tsec=600):
	"""Name the current trap and show the live estimate until Ctrl-C (or tsec).

	For moving to and focusing on the trap. Nothing is recorded; the median
	speed seen is written to the notes.
	"""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	exp.attribs["trap"] = str(trap)
	exp.log_event("trap_set", attribs={"trap": str(trap)})

	scope.lit.setVs(*exp.attribs["light"])
	cam_cycle()
	cam = scope.cam.cam
	live = new_liveflow(cam)
	cam.post_callback = make_post_callback(gray=True, live=live)
	cam.start_preview(scope.cam.preview_type, **scope.cam.preview_options)
	try:
		cam.start()
		live.start()
		print(f"[green]Trap {trap}: live preview. Ctrl-C to stop.")
		precise_sleep(tsec)
	except KeyboardInterrupt:
		print("Preview has ended...")
	finally:
		live.stop()
		cam_cycle()

	s = live.summary()
	exp.note(f"goto_trap({trap}): {s['estimates']} estimates, median speed "
			 f"{s['speed_med']:.2f} um/s, est {s['est_hz']:.1f} Hz (not recorded).")
	print(Panel(Pretty(s), title=f"trap {trap}"))


def capture(mode):
	"""Record one clip of the current trap in `mode`. Returns True on success.

	Failures are logged and swallowed so one bad clip does not end the run;
	Ctrl-C still stops it (KeyboardInterrupt is not an Exception).
	"""
	global exp, scope, split_no
	exp = Experiment.current
	scope = ScopeAssembly.current
	if mode not in MODES:
		raise KeyError(f"Unknown mode {mode!r}. One of: {', '.join(MODES)}")
	a = exp.attribs
	trap = a["trap"] or "notrap"
	preview = mode != "record"
	estimate = mode == "record_preview_estimate"

	scope.beacon.on()
	time.sleep(a["beacon_stabilization_delay_s"])
	scope.lit.setVs(*a["light"])
	time.sleep(a["light_stabilization_delay_s"])

	filename = filename_fn(split_no, trap, mode)
	tpts = filename.replace(".mjpeg", ".tpts")
	exp.mstreams["acq"](acq=filename)

	ok, md = True, {}
	live = None
	sysmon = SysMonitor()
	try:
		cam_cycle()
		cam = scope.cam.cam
		live = new_liveflow(cam) if estimate else None
		if preview:
			cam.post_callback = make_post_callback(gray=True, live=live)
			cam.start_preview(scope.cam.preview_type, **scope.cam.preview_options)
		encoder = JpegEncoderGrayRedCh(q=a["quality"], num_threads=a["num_threads"])
		sysmon.start()
		cam.start_recording(encoder, filename, pts=tpts)
		if live is not None:
			live.start()
		try:
			md = cam.capture_metadata()     ## what the sensor is really doing
		except Exception as e:
			log.error(f"capture_metadata failed: {e}")
		precise_sleep(a["chunk_size_sec"])
	except Exception as e:
		ok = False
		print(Panel(f"[red]split {split_no} ({trap}, {mode}) :: acq failed\n"
					f"{type(e).__name__}: {e}", title="capture"))
		exp.log_event("acq_failed", attribs={"split": split_no, "trap": trap, "mode": mode,
											 "filename": filename,
											 "error": f"{type(e).__name__}: {e}"})
		exp.note(f"{split_no} :: {trap} {mode} acq failed ({type(e).__name__}: {e}).")
	finally:
		if live is not None:
			live.stop()
		sysmon.stop()
		try:
			cam_cycle()      ## stops recording and preview, clears callbacks/overlay
		except Exception as e:
			log.error(f"camera did not reopen after split {split_no}: {e}")
		scope.beacon.off()

	if ok:
		frames, fps, dropped = tpts_stats(tpts, a["frame_duration_us"])
		csvname = ""
		if live is not None:
			csvname = filename.replace(".mjpeg", "_flowlive.csv")
			live.write_csv(csvname)
			exp.log("filename_created", attribs={"filename": csvname,
												 "rows": len(live.records)})
		s = live.summary() if live is not None else dict(LiveFlow.EMPTY_SUMMARY)
		sm = sysmon.summary()
		r = lambda v, n=3: round(float(v), n) if np.isfinite(v) else float("nan")
		exp.mstreams["flowlive"](split=split_no, trap=trap, mode=mode, acq=filename,
								 csv=csvname, frames=frames, dropped=dropped,
								 estimates=s["estimates"], throttled=sm["throttled"],
								 cam_fps=r(fps), est_hz=r(s["est_hz"]),
								 latency_ms=r(s["latency_ms"], 1), proc_ms=r(s["proc_ms"], 1),
								 lag=r(s["lag"], 1), speed_med=r(s["speed_med"]),
								 speed_last=r(s["speed_last"]), valid_frac=r(s["valid_frac"]),
								 cpu_mean=r(sm["cpu_mean"], 1), cpu_max=r(sm["cpu_max"], 1),
								 temp_max=r(sm["temp_max"], 1), load1=r(sm["load1"], 2),
								 exposure_us=md.get("ExposureTime", float("nan")),
								 frame_duration_us=md.get("FrameDuration", float("nan"))).panel()

		expected = a["chunk_size_sec"] * a["fps"]
		if frames < 0.9 * expected or dropped > 0.05 * expected:
			exp.note(f"{split_no} :: {trap} {mode}: {frames}/{expected:.0f} frames, "
					 f"{dropped} dropped -- this mode is losing frames.")
		if a["sync_files"]:
			## Only the clip is moved; sidecars go with the final sync_dir().
			exp.sync_file_bg(filename, remove_source=True)

	split_no = split_no + 1
	return ok


def record_trap(modes=None, clips_per_mode=None):
	"""Record the current trap: clips_per_mode clips in each mode, in order."""
	exp = Experiment.current
	if not exp.attribs["trap"]:
		raise RuntimeError("No trap set. Call goto_trap(<name>) first.")
	modes = modes or exp.attribs["modes"]
	n = clips_per_mode or exp.attribs["clips_per_mode"]
	results = [(m, capture(m)) for m in modes for _ in range(n)]
	print(exp.mstreams["flowlive"].tabulate("split", "trap", "mode", "cam_fps",
											"dropped", "est_hz", "speed_med"))
	return results


def record_sensor():
	"""Read temperature and humidity."""
	scope = ScopeAssembly.current
	tandh = Experiment.current.mstreams["tandh"]
	try:
		value = scope.tandh.read()
	except Exception:
		print("[red]TandH reading failed![default]")
		value = {"temp": 0, "humidity": 0}
	tandh(**value).panel()


def cleanup():
	"""Lights off, save, offload. Leaves the experiment open: type exp.close()."""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.lit.setVs(0, 0, 0)
	record_sensor()
	exp.logs.update(scope.get_config())
	exp.__save__()
	print(exp.mstreams["flowlive"].tabulate("split", "trap", "mode", "cam_fps", "dropped",
											"est_hz", "latency_ms", "speed_med"))
	exp.sync_dir()
	exp.note("Data offloaded. Experiment left open.")
	print(Panel("[yellow]Data offloaded. Lights off.\nType [bold]exp.close()[/bold] "
				"to finish.", title="cleanup"))


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	cam_cycle()
	scope.beacon.off()
	print(Panel('create_exp("<label>") -> goto_trap("<trap>") -> record_trap() '
				'-> ... -> cleanup()\n\n'
				f'modes: {", ".join(MODES)}', title="bead flow speed estimation"))
