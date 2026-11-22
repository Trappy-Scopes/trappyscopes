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
# | Date      : June 2026                                                      |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+


from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty
import logging as log


from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from expframework.protocol import Protocol


__decription__ = \
"""Long term measurement with continuous recording.

Use `create_exp() to open a new experiment. Use findexp() to open an old one.
Use `start_acq_blocking()` to start acquiring.
Use `stop_cam()` to kill the capture thread.
"""



def populate_exp():
	"""Add experimental parameters"""
	exp = Experiment.current
	exp.attribs["chunk_size_sec"] = 10*60
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 18
	exp.attribs["quality"] = 100
	exp.attribs["no_chunks"] = 81
	exp.attribs["light"] = (0.5,0,0)
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts_multi"
	exp.attribs["group"] = "red_light"
	exp.attribs["sync_files"] = False
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scopeid, scope
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment.Construct(["longterm_traj"])
	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	# Protocol
	os.makedirs("protocols", exist_ok=True)
	p = Protocol("experiments/masterprotocols/masterprotocol_June26.md")
	p.write("protocols/masterprotocol_June26.md")

	p = Protocol("experiments/selectswimmers.md")
	p.write("protocols/selectswimmers.md")

	populate_exp()






global process
process = None

def stop_cam():
	global process, scope
	print(f"Killing: {process}")
	process.kill()
	print(f"Killed: {process}")
	scope.beacon.blink()

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
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__{time.time_ns()}__split_{split_no}.mjpeg', abspath=False)
	capturefilelist.append(filename)
	if split_no > 1 and exp.params["sync_files"]:
		sync_file()
	return filename





def capture():
	global exp, scope
		
	# Pending -> File record mechaanism
	#c = exp.mstreams["acq"](filename=filename)
	#c.panel()
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.cam.read(exp.attribs["camera_mode"], filename_fn, no_splits=exp.attribs["no_chunks"], tsec=exp.attribs["chunk_size_sec"], 
					show_preview=False, quality=exp.attribs["quality"])

	## Experiment is finishing - therefore sync the whole directory
	
	#exp.__save__()
	#exp.sync_dir()
	#exp.close()

## --------------------------------------------------------------------------
##  Run evidence -- AI generated (Claude, Anthropic), 2026-11
## --------------------------------------------------------------------------
## Until 2026-11-22 a crash left nothing but a split that stopped: libcamera's
## messages went only to the terminal, the kernel log was not kept, and the
## blocked read() logs nothing. This writes, live, into the experiment folder:
##   libcamera.log   libcamera's messages (all of stderr), wall time in front
##   kernel.log      dmesg, followed for the whole run
##   telemetry.csv   1 Hz: split (as in the file name), split file size, camera frames, CSI
##                   interrupts, CMA, SoC temperature, throttle flags
## and logs an event (with a snapshot of the machine state) when
##   camera_stall    the camera delivers no frame for stall_s, or
##   output_stall    frames keep arriving but the split file stops growing for
##                   output_stall_s -- the encoder/output side, not the camera.
## The acquisition itself is unchanged.

import csv
import os
import re
import subprocess
import threading

from detectors.cameras.camlogs import CameraLogs, csi_irq

global _logs, _watcher, _watch_stop
_logs, _watcher, _watch_stop = None, None, threading.Event()


def _sys_read(path, key=None):
	try:
		with open(path) as f:
			if key is None:
				return f.read().strip()
			for line in f:
				if line.startswith(key):
					return line.split()[1]
	except Exception:
		return ""


global _thr, _thr_at
_thr, _thr_at = "", 0.0


def _throttled():
	"""vcgencmd forks, so at most every 10 s."""
	global _thr, _thr_at
	if time.monotonic() - _thr_at < 10:
		return _thr
	_thr_at = time.monotonic()
	try:
		out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
							 text=True, timeout=5).stdout
		m = re.search(r"throttled=(0x[0-9a-fA-F]+)", out)
		_thr = m.group(1) if m else ""
	except Exception:
		_thr = ""
	return _thr


def _evidence(exp, kind, n, **attribs):
	"""Log one stall: libcamera's reason, a snapshot, an event and a note."""
	reason, tail = _logs.reason()
	snap = _logs.snapshot(f"{kind}_{n:02d}.txt")
	exp.log_event(kind, attribs={"n": n, "reason": reason, "snapshot": snap, **attribs})
	exp.note(f"{kind} #{n} in split {attribs.get('split')}: {reason}")
	exp.__save__()
	log.error(f"{kind} #{n}: {reason} {attribs}")
	print(Panel(f"[red]{kind} #{n}: {reason}\n{attribs}\n{tail.strip()[-300:]}",
				title="run evidence"))


def _watch(exp, scope, period=1.0, stall_s=5.0, output_stall_s=30.0):
	path = exp.newfile("telemetry.csv", abspath=False)
	n_cam = n_out = 0
	last_n = last_b = None
	t_n = t_b = time.monotonic()
	irq_at_frame = csi_irq()
	cam_flag = out_flag = False
	with open(path, "w", newline="") as f:
		w = csv.writer(f)
		w.writerow(["wall", "split", "split_file", "split_bytes", "cam_frames",
					"csi_irq", "cma_free_mb", "temp_c", "throttled"])
		while not _watch_stop.wait(period):
			try:
				n = scope.cam.cam.frames
			except Exception:
				n = None
			name = capturefilelist[-1] if capturefilelist else ""
			try:
				b = os.path.getsize(name) if name else None
			except OSError:
				b = None
			irq, now = csi_irq(), time.monotonic()
			temp = _sys_read("/sys/class/thermal/thermal_zone0/temp")
			cma = _sys_read("/proc/meminfo", "CmaFree:")
			try:
				w.writerow([round(time.time(), 3), len(capturefilelist) - 1, os.path.basename(name),
							b, n, irq, round(int(cma) / 1024, 1) if cma else "",
							round(int(temp) / 1000, 1) if temp else "", _throttled()])
				f.flush()
			except Exception:
				pass
			if n != last_n:
				last_n, t_n, irq_at_frame, cam_flag = n, now, irq, False
			elif not cam_flag and now - t_n >= stall_s:
				cam_flag, n_cam = True, n_cam + 1
				_evidence(exp, "camera_stall", n_cam, split=len(capturefilelist) - 1,
						  frames=n, csi_irq_since_last_frame=irq - irq_at_frame)
			if b != last_b:
				last_b, t_b, out_flag = b, now, False
			elif (not out_flag and b is not None and now - t_b >= output_stall_s
				  and now - t_n < stall_s):
				out_flag, n_out = True, n_out + 1
				_evidence(exp, "output_stall", n_out, split=len(capturefilelist) - 1,
						  split_file=os.path.basename(name), split_bytes=b, frames=n)


def start_evidence(exp, scope):
	"""libcamera.log, kernel.log and the watcher, from now on."""
	global _logs, _watcher
	_logs = CameraLogs().start()
	_watch_stop.clear()
	_watcher = threading.Thread(target=_watch, args=(exp, scope), daemon=True,
								name="run-evidence")
	_watcher.start()


def stop_evidence():
	_watch_stop.set()
	if _watcher is not None:
		_watcher.join(timeout=5)
	if _logs is not None:
		_logs.stop()


def start_acq():

	global exp, scope, capture
	scope = ScopeAssembly.current
	scope.beacon.on()


	## Read tandh
	tandh = exp.mstreams["tandh"]
	def record_sensor():
		try:
			value = scope.tandh.read()
		except:
			print("[red]TandH reading failed![default]")
			value =  {"temp": 0, "humidity":0}
		r = tandh(**value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(seconds=exp.attribs["chunk_size_sec"]*exp.attribs["no_chunks"])).do(record_sensor)
	exp.logs.update(scope.get_config())
	exp.__save__()
	print("All jobs: ", exp.schedule.get_jobs())

	## Set lights and capture
	scope.lit.setVs(*exp.attribs["light"])
	
	scope.cam.close()
	time.sleep(1)
	log.info("Camera closed for process forking.")

	from multiprocessing import Process
	global process
	process = Process(target=capture)
	process.start()

def start_acq_blocking():

	global capture
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.beacon.on()


	## Explicit schedule clear
	exp.schedule.clear()
	#exp.schedule.loop()

	## Read tandh
	tandh = exp.mstreams["tandh"]
	def record_sensor():
		try:
			value = scope.tandh.read()
		except:
			print("[red]TandH reading failed![default]")
			value =  {"temp": 0, "humidity":0}
		r = tandh(**value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(seconds=exp.attribs["chunk_size_sec"]*exp.attribs["no_chunks"])).do(record_sensor)
	exp.logs.update(scope.get_config())
	exp.__save__()
	print("All jobs: ", exp.schedule.get_jobs())

	## Set lights and capture
	scope.lit.setVs(*exp.attribs["light"])
	start_evidence(exp, scope)      # AI generated (Claude), 2026-11: run evidence

	#from multiprocessing import Process
	#global process
	#process = Process(target=capture)
	#process.start()
	capture()
	stop_evidence()                 # AI generated (Claude), 2026-11
	exp.__save__()
	exp.logs.update(scope.get_config())
	scope.beacon.blink()
	exp.sync_dir(remove_source=False)
	exp.sync_dir()


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	scope.lit.setVs(0.50,0,0)
	print("Lights ready...")
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.off()
