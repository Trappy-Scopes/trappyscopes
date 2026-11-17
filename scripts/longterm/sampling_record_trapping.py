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

from datetime import timedelta
import datetime
import time
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty
import ast
import os
import glob
import re
import logging as log

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from functools import partial

from expframework.protocol import Protocol

from picamera2.request import MappedArray
from core.precision.timing import precise_sleep
from detectors.cameras.rpi_hq_picam2 import JpegEncoderGrayRedCh


__decription__ = \
"""Long term measurement using periodic video sampling, plus recording of the
trapping flow.

Identical to mjpeg_sampling.py, with one addition: record_trapping() records
the beads/cells flowing into the traps while a grayscale (red channel)
preview is shown, until the operator stops it with Ctrl-C. No live tracking,
no estimation -- preview and record only. Call it as many times as needed
before start_acq(); each call writes the next file in the trapping folder:

    trapping/trapping_flow_1.mjpeg  (+ .tpts)
    trapping/trapping_flow_2.mjpeg  (+ .tpts)
    ...

Every recording emits a `trapping_flow_start` event and either a
`trapping_flow_stop` event (duration, frames, measured fps, dropped frames,
how it ended) or a `trapping_flow_failed` event.

print("Use create_exp() to open a new experiment. Use exp = findexp() to open an old one.")
print("Use record_trapping() to record the trapping flow (Ctrl-C to stop). Repeat as needed.")
print("Use start_acq() to start acquiring.")
print("Use cleanup() to sync and offload. Then call exp.close() to finish.")
"""


def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment.Construct(["sampled_longterm_traj"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	exp.params["sampling_period_hours"] = 0.5
	exp.params["sampling_hours"] = 22
	exp.params["tandh_sampling_period_minutes"] = 5

	
	exp.attribs["chunk_size_sec"] = 60
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 3
	exp.attribs["quality"] = 100
	exp.attribs["no_splits"] = 81
	exp.attribs["light"] = (0.5,0,0)
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts"
	exp.attribs["group"] = "red_light"
	exp.attribs["sync_files"] = True
	exp.attribs["auto_cleanup"] = True
	exp.attribs["beacon_stabilization_delay_s"] = 1

	## Trapping-flow recordings (record_trapping). Not synced while recording:
	## background sync costs frames; cleanup()'s sync_dir() offloads the folder.
	exp.attribs["trapping_folder"] = "trapping"
	exp.attribs["trapping_light"] = (0.5,0,0)
	exp.attribs["trapping_quality"] = 100
	exp.attribs["trapping_num_threads"] = 3
	exp.attribs["trapping_max_min"] = 30      ## safety stop if Ctrl-C never comes
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


	# Protocol
	os.makedirs("protocols", exist_ok=True)
	p = Protocol("experiments/masterprotocols/masterprotocol_June26.md")
	p.write("protocols/masterprotocol_June26.md")

	p = Protocol("experiments/selectswimmers.md")
	p.write("protocols/selectswimmers.md")

 


## Split number
global split_no
split_no = 0

global capturefilelist, syncidx
syncidx = 0
capturefilelist = []

def sync_file():
	global exp, capturefilelist, syncidx
	if len(capturefilelist) > 1:
		exp.sync_file_bg(capturefilelist[syncidx], remove_source=True)
		syncidx = syncidx + 1

def filename_fn(split_no):
	global exp
	global capturefilelist
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__{time.time_ns()}__split_{split_no}.mjpeg', abspath=False)
	capturefilelist.append(filename)
	#if split_no >= 1 and exp.params["sync_files"]:
	#	sync_file()
	return filename



def capture():
	"""Function that records videos"""
	scope = ScopeAssembly.current
	exp = Experiment.current
	scope.beacon.on()
	time.sleep(exp.params["beacon_stabilization_delay_s"])

	exp = Experiment.current
	split = len(exp.mstreams["acq"].readings)
	
	global split_no
	filename=filename_fn(split_no)
	acq = exp.mstreams["acq"](acq=filename)
	
	### Capture
	try:
		scope.cam.open()
		scope.cam.configure()
		scope.cam.read(exp.attribs["camera_mode"], 
					   filename,
					   tsec=exp.attribs["chunk_size_sec"], 
					 	show_preview=False,
						quality=exp.attribs["quality"])
		scope.cam.close()
	except Exception as e:
		raise e
		scope.cam.close()
		exp.note(f"{split_no} :: acq failed.")

	split_no = split_no + 1
	#acq.panel()
	scope.beacon.off()
	if exp.params["sync_files"]:
		exp.sync_file_bg(filename, remove_source=True)


def record_sensor():
	"""Read temperature sensor"""
	tandh = Experiment.current.mstreams["tandh"]
	try:
		value = scope.tandh.read()
	except:
		print("[red]TandH reading failed![default]")
		value =  {"temp": 0, "humidity":0}
	r = tandh(**value)
	r.panel()


def cleanup():
	"""Offload the experiment and stop the schedule. Does NOT close.

	cleanup() is itself a scheduled job, so it runs on the exp.schedule.loop
	thread. exp.close() ends with self.schedule.thread.join(), and a thread
	cannot join itself -- that raised `RuntimeError: cannot join current
	thread`, which killed the scheduler thread and skipped everything after the
	join in close(): os.chdir(self.lastwd) and Share.updateps1().

	So closing is left to the operator. Once this has run, type:

	    exp.close()
	"""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	exp.logs.update(ScopeAssembly.current.get_config())
	exp.schedule.clear()            ## removes the current job as well
	exp.schedule.end_thread = True  ## stop the loop once this job returns
	exp.__save__()
	exp.sync_dir()
	exp.note("Data offloaded and schedule stopped. Experiment left open")
	print(Panel("[yellow]Data offloaded, schedule stopped.\n"
				"The experiment is still OPEN. Type [bold]exp.close()[/bold] "
				"to finish it.", title="cleanup"))

def start_acq():
	global exp, scope, capture
	scope = ScopeAssembly.current

	## Clear all other scheduled job for safety...
	print("[red]Clearing experiment scheduler...")
	exp.schedule.clear()


	## Read tandh
	record_sensor()
	Experiment.current.schedule.every(exp.params["tandh_sampling_period_minutes"]).minutes.until(timedelta(hours=exp.params["sampling_hours"])).do(record_sensor)

	## Set lights and capture
	scope.lit.setVs(*exp.params["light"])
	capture()
	Experiment.current.schedule.every(exp.params["sampling_period_hours"]).hours.until(timedelta(hours=exp.params["sampling_hours"])).do(capture)

## Cleanup
	if exp.attribs["auto_cleanup"]:
		Experiment.current.schedule.every(exp.params["sampling_hours"]+1).hours.until(timedelta(hours=exp.params["sampling_hours"]+2)).do(cleanup)
	


## --------------------------------------------------------------------------
##  Trapping-flow recording: grayscale preview + record, no analysis
## --------------------------------------------------------------------------

def cam_cycle():
	"""close -> open -> configure, leaving the camera open and configured.

	Same as light_perturbation.cam_cycle(): Camera.open() assigns a new
	Picamera2 without closing the old one, and open() does not apply
	self.config, so always close first and configure explicitly. Callbacks are
	cleared so a grayscale copy cannot leak into the next acquisition.
	"""
	scope = ScopeAssembly.current
	for stop in (lambda: scope.cam.cam.stop_recording(),
				 lambda: scope.cam.cam.stop(),
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


def _next_trapping_no(folder):
	"""1 + the highest trapping_flow_<n>.mjpeg already in the folder, so a
	restarted session never overwrites an earlier recording."""
	nums = [int(m.group(1)) for f in glob.glob(os.path.join(folder, "trapping_flow_*.mjpeg"))
			if (m := re.search(r"trapping_flow_(\d+)\.mjpeg$", f))]
	return max(nums, default=0) + 1


def _tpts_stats(tpts_filename, frame_duration_us):
	"""(frames, measured fps, dropped frames) from a picamera2 .tpts file."""
	try:
		with open(tpts_filename) as f:
			t = [float(s) for s in f if s.strip() and not s.startswith("#")]
	except Exception as e:
		log.error(f"Could not read {tpts_filename}: {e}")
		return 0, None, None
	if len(t) < 2:
		return len(t), None, 0
	nominal = frame_duration_us / 1000
	dropped = sum(max(round((b - a) / nominal) - 1, 0) for a, b in zip(t, t[1:]))
	return len(t), (len(t) - 1) / ((t[-1] - t[0]) / 1000), int(dropped)


def record_trapping(max_min=None, label=""):
	"""Record the trapping flow with a grayscale preview until Ctrl-C.

	Writes trapping/trapping_flow_<n>.mjpeg (+ .tpts), n counting up across
	calls. The red channel is recorded (JpegEncoderGrayRedCh); the preview
	copies red into green and blue, which does not change the recorded clip.
	max_min: safety stop in minutes (default exp.attribs["trapping_max_min"]).
	label: optional free text stored with the events.

	Leaves the camera open and configured, as the script's start-up does.
	Returns the clip's path, or None if the recording failed.
	"""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	a = exp.attribs
	max_s = 60 * (max_min if max_min is not None else a["trapping_max_min"])

	folder = a["trapping_folder"]
	os.makedirs(folder, exist_ok=True)
	n = _next_trapping_no(folder)
	filename = os.path.join(folder, f"trapping_flow_{n}.mjpeg")
	tpts = filename.replace(".mjpeg", ".tpts")
	exp.log("filename_created", attribs={"filename": filename, "kind": "trapping_flow"})

	ctrl = scope.cam.controls
	frame_us = int(ctrl["FrameDurationLimits"][1])
	start = {"n": n, "filename": filename, "tpts": tpts, "label": str(label),
			 "light": tuple(a["trapping_light"]), "quality": a["trapping_quality"],
			 "exposure_us": ctrl["ExposureTime"], "frame_duration_us": frame_us,
			 "max_s": max_s}

	scope.lit.setVs(*a["trapping_light"])
	scope.beacon.on()

	def to_grayscale(request):
		with MappedArray(request, "main") as m:
			m.array[..., 1] = m.array[..., 0]
			m.array[..., 2] = m.array[..., 0]

	how, t0, ok = "user_quit", None, True
	try:
		cam_cycle()
		cam = scope.cam.cam
		cam.post_callback = to_grayscale
		cam.start_preview(scope.cam.preview_type, **scope.cam.preview_options)
		encoder = JpegEncoderGrayRedCh(q=a["trapping_quality"], num_threads=a["trapping_num_threads"])
		cam.start_recording(encoder, filename, pts=tpts)
		t0 = time.monotonic()
		exp.log_event("trapping_flow_start", attribs=start)
		print(Panel(f"Recording [bold]{filename}[/bold]\n"
					f"[yellow]Ctrl-C to stop[/yellow] (safety stop after {max_s / 60:.0f} min)",
					title=f"trapping flow {n}"))
		try:
			precise_sleep(max_s)
			how = "max_duration"
		except KeyboardInterrupt:
			how = "user_quit"
	except Exception as e:
		ok = False
		exp.log_event("trapping_flow_failed", attribs={**start, "error": f"{type(e).__name__}: {e}"})
		exp.note(f"trapping flow {n} failed ({type(e).__name__}: {e}).")
		print(Panel(f"[red]trapping flow {n} failed\n{type(e).__name__}: {e}", title="record_trapping"))
	finally:
		duration = time.monotonic() - t0 if t0 is not None else 0.0
		try:
			cam_cycle()      ## stops recording and preview, clears the callback
		except Exception as e:
			log.error(f"camera did not reopen after trapping flow {n}: {e}")
		scope.beacon.off()

	if not ok:
		exp.__save__()
		return None

	frames, fps, dropped = _tpts_stats(tpts, frame_us)
	stop = {"n": n, "filename": filename, "ended": how, "duration_s": round(duration, 2),
			"frames": frames, "fps": round(fps, 3) if fps else None, "dropped": dropped}
	exp.log_event("trapping_flow_stop", attribs=stop)
	exp.__save__()
	print(Panel(Pretty(stop), title=f"trapping flow {n} saved"))
	return filename



if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	#scope.lit.setVs(2.4,0,0)
	print("Lights ready...")
	#scope.cam.config["controls"]["ExposureTime"] = 3000
	scope.cam.close()
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.off()

