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
import math
import os
import pickle
import time

from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly

from detectors.cameras.rpi_hq_picam2 import (JpegEncoderGrayChannel,
                                             JpegEncoderGrayRedCh,
                                             JpegEncoderRedWithBGStats)


__description__ = \
"""Acceptance test for the single-channel encoders and the camera actions.

Covers the encoders (JpegEncoderGrayChannel for r/g/b, the JpegEncoderGrayRedCh
alias, JpegEncoderRedWithBGStats with its periodic flush), the per-frame channel
intensity mapping, and the img / timelapse / vid / lux_estimate actions plus the
rpreview() grayscale preview.

Every recording runs twice: once under white light, where all three channels
carry signal, and once under red-only light. That gives the intensity mapping a
positive and a negative control -- under red light the g/b means must collapse
towards the noise floor, and if they do not, the channel indices are wrong.

    create_exp()   open the experiment and declare parameters
    run_all()      run every test in sequence (blocking, ~12 min)
    cleanup()      save, sync and close

Individual tests can also be called on their own after create_exp():
    test_getstate(), test_channel_encoders(), test_bgstats(),
    test_image(), test_timelapse(), test_video(), test_lux(),
    test_rpreview(), test_rpreview_throughput()
"""


## --------------------------------------------------------------------------
##  Experiment setup
## --------------------------------------------------------------------------

def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["camtests", "encoders", "channels"])

	## acq : one row per recording / capture.
	exp.new_measurementstream("acq",
		monitors=["test", "encoder", "channel", "light", "acq"],
		measurements=["filesize_mb", "duration_s"])

	## chstats : SUMMARY of the per-frame intensity mapping, one row per run.
	## The per-frame records go to a CSV -- never to a measurement stream, as
	## MeasurementStream.__call__ triggers Experiment.__save__() (a YAML write
	## to disk) and that cannot keep up with 25 fps.
	exp.new_measurementstream("chstats",
		monitors=["test", "channel", "light", "acq", "csv", "frames"],
		measurements=["mean", "std"])

	## perf : frame rates, for the preview cost measurement.
	exp.new_measurementstream("perf",
		monitors=["test", "condition"], measurements=["fps"])

	exp.attribs["light_white"] = (0.5, 0.5, 0.5)
	exp.attribs["light_red"]   = (0.5, 0.0, 0.0)
	exp.attribs["light_off"]   = (0.0, 0.0, 0.0)
	exp.attribs["light_stabilization_delay_s"] = 2

	exp.attribs["clip_sec"]      = 20      ## length of each encoder clip
	exp.attribs["flush_every_s"] = 5       ## so a 20 s clip flushes ~4 times
	exp.attribs["quality"]       = 100
	exp.attribs["num_threads"]   = 3

	exp.attribs["timelapse_frames"]  = 5
	exp.attribs["timelapse_delay_s"] = 2
	exp.attribs["lux_sec"]           = 10
	exp.attribs["preview_sec"]       = 15

	exp.attribs["channels"] = ["r", "g", "b"]
	exp.attribs["group"]    = "encoder_acceptance"
	exp.attribs["sync_files"] = False      ## small files; sync once at the end

	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


## --------------------------------------------------------------------------
##  Helpers
## --------------------------------------------------------------------------

def set_light(name):
	"""Set the illumination to the named attrib and let it settle."""
	global exp, scope
	scope.lit.setVs(*exp.attribs[f"light_{name}"])
	time.sleep(exp.attribs["light_stabilization_delay_s"])
	return name


def cam_cycle():
	"""close -> open -> configure.

	open() calls self.cam.configure() with no argument, so self.config is not
	applied by it; configure() has to be called explicitly afterwards. Every
	acquisition script on this branch does the same.
	"""
	global scope
	scope.cam.close()
	scope.cam.open()
	scope.cam.configure()


def record_acq(test, acq, encoder=None, channel=None, light=None, duration_s=None):
	"""Log one produced file and report its size. Returns the size in MB.

	Camera.read() catches and prints exceptions rather than raising, so a
	failed action shows up here as a missing or empty file, not as a traceback.
	"""
	global exp
	size_mb = round(os.path.getsize(acq) / (1024 ** 2), 3) if os.path.exists(acq) else 0.0
	r = exp.mstreams["acq"](test=test, encoder=encoder, channel=channel,
							light=light, acq=os.path.basename(acq),
							filesize_mb=size_mb, duration_s=duration_s)
	r.panel()
	if size_mb == 0.0:
		print(Panel(f"[red]{test}: no output at {acq}", title="FAILED"))
		exp.note(f"{test}: produced no output ({acq}).")
	return size_mb


class IntensityWriter:
	"""flush_fn target for the channel intensity mapping.

	Appends each flushed batch to a CSV and keeps only running sums, so memory
	stays bounded however long the recording runs. This is the pattern the
	encoder's flush_fn exists for -- accumulating every record in a list works
	for a 20 s test clip but not for an overnight one.

	It is called from an encoder thread, so it stays short. Reopening the file
	per flush (rather than holding a handle) means an interrupted run still
	leaves a complete CSV on disk.
	"""

	def __init__(self, path, fields):
		self.path = path
		self.fields = list(fields)
		self.n = 0
		self._sum = {k: 0.0 for k in self.fields}
		self._sumsq = {k: 0.0 for k in self.fields}
		with open(self.path, "w") as f:
			f.write(",".join(["t_ns", *self.fields]) + "\n")

	def __call__(self, records):
		with open(self.path, "a") as f:
			for rec in records:
				f.write(",".join([str(rec["t_ns"])] +
								 [f"{rec[k]:.4f}" for k in self.fields]) + "\n")
				for k in self.fields:
					self._sum[k] += rec[k]
					self._sumsq[k] += rec[k] ** 2
		self.n += len(records)

	def summary(self, field):
		"""(mean, std) for one channel, from the running sums."""
		if not self.n:
			return (0.0, 0.0)
		mean = self._sum[field] / self.n
		var = max(0.0, self._sumsq[field] / self.n - mean ** 2)
		return (mean, math.sqrt(var))


## --------------------------------------------------------------------------
##  Tests
## --------------------------------------------------------------------------

def test_getstate():
	"""Camera.__getstate__ must pickle, and must not mutate the live config.

	The old implementation returned None and shallow-copied self.config, so
	stringifying NoiseReductionMode rewrote the real control enum in place.
	"""
	global exp, scope
	before = scope.cam.config["controls"]["NoiseReductionMode"]

	state = scope.cam.__getstate__()
	ok_returns = state is not None
	try:
		pickle.dumps(state)
		ok_pickles = True
	except Exception as e:
		ok_pickles = False
		print(f"[red]pickle.dumps failed: {e}")

	after = scope.cam.config["controls"]["NoiseReductionMode"]
	ok_intact = (after is before) and not isinstance(after, str)

	passed = ok_returns and ok_pickles and ok_intact
	print(Panel(f"returns a dict : {ok_returns}\n"
				f"pickles        : {ok_pickles}\n"
				f"config intact  : {ok_intact}  ({after!r})",
				title="test_getstate " + ("[green]PASS" if passed else "[red]FAIL")))
	exp.note(f"test_getstate: {'pass' if passed else 'FAIL'}")
	return passed


def test_channel_encoders():
	"""JpegEncoderGrayChannel for each of r/g/b, under white then red light.

	Each encoder records its own channel and measures the mean intensity of the
	other two, which exercises both halves of the class in one pass.
	"""
	global exp, scope

	for light in ("white", "red"):
		set_light(light)
		for ch in exp.attribs["channels"]:
			others = [c for c in ("r", "g", "b") if c != ch]

			acq = exp.newfile(f"grayscale_{ch}_{light}.mjpeg", abspath=False)
			csv = exp.newfile(f"grayscale_{ch}_{light}_intensities.csv", abspath=False)

			writer = IntensityWriter(csv, others)
			enc = JpegEncoderGrayChannel(q=exp.attribs["quality"],
										 num_threads=exp.attribs["num_threads"],
										 channel=ch,
										 intensity_channels=others)

			cam_cycle()
			scope.cam.read("vid_mjpeg_tpts", acq,
						   tsec=exp.attribs["clip_sec"],
						   show_preview=False,
						   quality=exp.attribs["quality"],
						   encoder=enc)
			scope.cam.close()

			## read() discards action return values, so drain the encoder here.
			writer(enc.drain())

			record_acq("channel_encoder", acq, encoder="JpegEncoderGrayChannel",
					   channel=ch, light=light, duration_s=exp.attribs["clip_sec"])

			for other in others:
				mean, std = writer.summary(other)
				exp.mstreams["chstats"](test="channel_encoder", channel=other,
										light=light, acq=os.path.basename(acq),
										csv=os.path.basename(csv), frames=writer.n,
										mean=round(mean, 4), std=round(std, 4)).panel()

	set_light("off")
	print(Panel("Compare the white-light and red-light rows in `chstats`: under "
				"red light the g and b means must collapse towards zero. If they "
				"do not, the channel indices are wrong.", title="test_channel_encoders"))


def test_alias_encoder():
	"""JpegEncoderGrayRedCh must still work and must add no intensity cost."""
	global exp, scope
	light = set_light("red")
	acq = exp.newfile("alias_redch.mjpeg", abspath=False)

	enc = JpegEncoderGrayRedCh(q=exp.attribs["quality"],
							   num_threads=exp.attribs["num_threads"])
	cam_cycle()
	scope.cam.read("vid_mjpeg_tpts", acq, tsec=exp.attribs["clip_sec"],
				   show_preview=False, quality=exp.attribs["quality"], encoder=enc)
	scope.cam.close()

	record_acq("alias_encoder", acq, encoder="JpegEncoderGrayRedCh",
			   channel="r", light=light, duration_s=exp.attribs["clip_sec"])

	## Intensity mapping is opt-in, so the alias must have recorded nothing.
	leftover = len(enc.drain())
	print(Panel(f"intensity records (must be 0): {leftover}",
				title="test_alias_encoder " + ("[green]PASS" if leftover == 0 else "[red]FAIL")))
	set_light("off")


def test_bgstats():
	"""JpegEncoderRedWithBGStats: red to file, blue+green measured, periodic flush.

	This is the encoder the real acquisition will use. The flush interval is
	short here so the callback fires several times within one clip.
	"""
	global exp, scope

	for light in ("white", "red"):
		set_light(light)
		acq = exp.newfile(f"bgstats_{light}.mjpeg", abspath=False)
		csv = exp.newfile(f"bgstats_{light}_intensities.csv", abspath=False)

		writer = IntensityWriter(csv, ["g", "b"])
		enc = JpegEncoderRedWithBGStats(q=exp.attribs["quality"],
										num_threads=exp.attribs["num_threads"],
										flush_fn=writer,
										flush_interval_s=exp.attribs["flush_every_s"])

		cam_cycle()
		scope.cam.read("vid_mjpeg_tpts", acq, tsec=exp.attribs["clip_sec"],
					   show_preview=False, quality=exp.attribs["quality"], encoder=enc)
		scope.cam.close()

		enc.drain()   ## flushes the tail through flush_fn as well

		size_mb = record_acq("bgstats", acq, encoder="JpegEncoderRedWithBGStats",
							 channel="r", light=light,
							 duration_s=exp.attribs["clip_sec"])

		expected = exp.attribs["clip_sec"] * 25
		print(Panel(f"frames measured : {writer.n} (expect ~{expected} at 25 fps)\n"
					f"file size       : {size_mb} MB\n"
					f"csv             : {csv}",
					title=f"test_bgstats [{light}]"))
		if writer.n < 0.9 * expected:
			exp.note(f"test_bgstats [{light}]: only {writer.n}/{expected} frames "
					 f"measured -- the encoder is dropping frames.")

		for field in ("g", "b"):
			mean, std = writer.summary(field)
			exp.mstreams["chstats"](test="bgstats", channel=field, light=light,
									acq=os.path.basename(acq), csv=os.path.basename(csv),
									frames=writer.n, mean=round(mean, 4),
									std=round(std, 4)).panel()

	set_light("off")


def test_image():
	"""The `img` action.

	Expect a printed RuntimeError here even on success: __image__ calls
	stop_preview() unconditionally, and picamera2 raises "No preview specified"
	when none was started. read() catches it, and it happens after
	capture_file(), so the file is written regardless -- but the acquisition is
	never logged to the experiment and post_action_callback never runs. Judge
	this test by the file, not by the traceback. Not one of the seven fixes, so
	it is still live on main.
	"""
	global exp, scope
	light = set_light("white")
	acq = exp.newfile("still.png", abspath=False)
	cam_cycle()
	scope.cam.read("img", acq, tsec=3, show_preview=False)
	scope.cam.close()
	record_acq("img", acq, light=light, duration_s=3)
	set_light("off")


def test_timelapse():
	"""The `timelapse` action -- previously broken three separate ways."""
	global exp, scope
	light = set_light("white")
	frames = exp.attribs["timelapse_frames"]
	acq = exp.newfile("timelapse.jpg", abspath=False)

	cam_cycle()
	scope.cam.read("timelapse", acq, show_preview=False,
				   frames=frames, delay_s=exp.attribs["timelapse_delay_s"])
	scope.cam.close()

	## Files are written as <nnn>_<eid>_timelapse.jpg next to `acq`.
	stem = os.path.basename(acq).rsplit(".", 1)[0]
	written = sorted(f for f in os.listdir(os.path.dirname(os.path.abspath(acq)))
					 if f.endswith(f"_{stem}.jpg"))
	passed = len(written) == frames
	print(Panel(f"expected {frames} frames, found {len(written)}\n" + "\n".join(written),
				title="test_timelapse " + ("[green]PASS" if passed else "[red]FAIL")))
	for f in written:
		record_acq("timelapse", f, light=light)
	if not passed:
		exp.note(f"test_timelapse: wrote {len(written)} of {frames} frames.")
	set_light("off")


def test_video():
	"""The `vid` action, for each name in Camera.ENCODERS.

	`vid` and `vid_noprev` both raised AttributeError before the encodermap
	fix, so this is the first time either has run.
	"""
	global exp, scope
	light = set_light("white")

	for name, ext in (("h264encoder", "h264"), ("mjpegencoder", "mjpeg")):
		acq = exp.newfile(f"video_{name}.{ext}", abspath=False)
		cam_cycle()
		scope.cam.read("vid", acq, tsec=exp.attribs["clip_sec"],
					   show_preview=False, encoder=name)
		scope.cam.close()
		record_acq("vid", acq, encoder=name, light=light,
				   duration_s=exp.attribs["clip_sec"])

	## Default encoder (H264Encoder) and the no-preview wrapper.
	acq = exp.newfile("video_default_noprev.h264", abspath=False)
	cam_cycle()
	scope.cam.read("vid_noprev", acq, tsec=exp.attribs["clip_sec"])
	scope.cam.close()
	record_acq("vid_noprev", acq, encoder="H264Encoder (default)", light=light,
			   duration_s=exp.attribs["clip_sec"])
	set_light("off")


def test_lux():
	"""The renamed `lux_estimate` action. Also gives the baseline frame rate."""
	global exp, scope
	for light in ("white", "red", "off"):
		set_light(light)
		acq = exp.newfile(f"lux_{light}.csv", abspath=False)
		cam_cycle()
		scope.cam.read("lux_estimate", acq, tsec=exp.attribs["lux_sec"])
		scope.cam.close()
		record_acq("lux_estimate", acq, light=light, duration_s=exp.attribs["lux_sec"])


def test_rpreview():
	"""Visual check of the grayscale single-channel preview.

	Nothing is written to file, so this one needs a human at the screen. Under
	white light the image must be gray, not tinted -- a tint means the channel
	broadcast is not covering every channel.
	"""
	global exp, scope
	set_light("white")
	cam_cycle()
	print(Panel("Watch the preview window: red channel, grayscale, white light.",
				title="test_rpreview"))
	scope.cam.rpreview(exp.attribs["preview_sec"], channel="r")

	set_light("red")
	print(Panel("Same under red light -- should look near-identical to the "
				"normal preview.", title="test_rpreview"))
	scope.cam.rpreview(exp.attribs["preview_sec"], channel="r")

	scope.cam.close()
	set_light("off")
	exp.note("test_rpreview: visual check performed by operator.")


def test_rpreview_throughput():
	"""Cost of the grayscale preview: frame rate with and without the callback.

	rpreview() writes two full frames back into the buffer on the camera event
	loop (~4.6 MB at 1520x1520). This measures whether that holds the
	configured frame rate. It installs the same callback rpreview() uses rather
	than calling rpreview(), because the frame rate has to be sampled from the
	same thread while the callback is live.
	"""
	global exp, scope
	import numpy as np
	from picamera2.request import MappedArray

	set_light("white")
	ch = JpegEncoderGrayChannel.CHANNELS["r"]
	others = tuple(c for c in (0, 1, 2) if c != ch)

	def to_grayscale(request):
		with MappedArray(request, "main") as m:
			for other in others:
				m.array[..., other] = m.array[..., ch]

	def measure(seconds):
		durations = []
		deadline = time.monotonic() + seconds
		while time.monotonic() < deadline:
			durations.append(scope.cam.cam.capture_metadata()["FrameDuration"])
		return 1e6 / float(np.mean(durations))

	results = {}
	for condition, callback in (("plain", None), ("grayscale", to_grayscale)):
		cam_cycle()
		scope.cam.cam.post_callback = callback
		scope.cam.cam.start_preview(scope.cam.preview_type, **scope.cam.preview_options)
		try:
			scope.cam.cam.start()
			time.sleep(2)                      ## let the pipeline settle
			results[condition] = measure(exp.attribs["preview_sec"])
		finally:
			scope.cam.cam.post_callback = None
			scope.cam.cam.stop()
			scope.cam.cam.stop_preview()
			scope.cam.close()

		exp.mstreams["perf"](test="rpreview_throughput", condition=condition,
							 fps=round(results[condition], 2)).panel()

	drop = results["plain"] - results["grayscale"]
	print(Panel(f"plain preview     : {results['plain']:.2f} fps\n"
				f"grayscale preview : {results['grayscale']:.2f} fps\n"
				f"cost              : {drop:.2f} fps",
				title="test_rpreview_throughput"))
	if drop > 1.0:
		exp.note(f"test_rpreview_throughput: grayscale preview costs {drop:.2f} fps. "
				 f"Shrink the main stream if that matters.")
	set_light("off")


## --------------------------------------------------------------------------
##  Sequencing
## --------------------------------------------------------------------------

def run_all(interactive=True):
	"""Run every test in sequence. Blocking.

	interactive=False skips test_rpreview, which needs somebody watching the
	screen; every other test verifies itself from the files it produces.
	"""
	global exp, scope
	started = time.time()
	exp.note("encoder_channel_tests: run_all started.")

	tests = [test_getstate, test_channel_encoders, test_alias_encoder,
			 test_bgstats, test_image, test_timelapse, test_video, test_lux,
			 test_rpreview_throughput]
	if interactive:
		tests.append(test_rpreview)

	for test in tests:
		print("\n")
		print(Panel(f"{test.__name__}", style="yellow"))
		try:
			test()
		except KeyboardInterrupt:
			print(Panel(f"[red]{test.__name__} interrupted -- moving on.", style="red"))
			exp.note(f"{test.__name__}: interrupted by operator.")
			scope.cam.close()
		except Exception as e:
			print(Panel(f"[red]{test.__name__} raised: {e}", style="red"))
			exp.note(f"{test.__name__}: raised {type(e).__name__}: {e}")
			scope.cam.close()

	set_light("off")
	exp.note(f"encoder_channel_tests: run_all finished in {time.time()-started:.0f} s.")
	print(exp.mstreams["acq"].tabulate("test", "encoder", "channel", "light",
									   "acq", "filesize_mb"))
	print(exp.mstreams["chstats"].tabulate("test", "channel", "light", "frames",
										   "mean", "std"))


def cleanup():
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.lit.setVs(*exp.attribs["light_off"])
	exp.logs.update(scope.get_config())
	exp.schedule.clear()
	exp.__save__()
	exp.sync_dir()
	exp.close()


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	scope.beacon.off()
	scope.cam.close()
	print(Panel("create_exp() -> run_all() -> cleanup()", title="camtests"))
