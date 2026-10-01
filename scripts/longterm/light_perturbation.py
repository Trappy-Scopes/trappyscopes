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
import logging as log
import os
import time

import numpy as np
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from expframework.protocol import Protocol
from hive.assembly import ScopeAssembly

from detectors.cameras.rpi_hq_picam2 import JpegEncoderRedWithBGStats


__description__ = \
"""Light perturbation experiment -- sampled MJPEG, one condition per microscope.

Same sampling as mjpeg_sampling.py (60 s clip every 30 min for 22 h), but each
microscope runs one of four light/reagent conditions. The same file is loaded on
every scope; the only thing that differs is the condition passed to create_exp().

                      between acquisitions        during acquisition
    control       0.5 V red                   0.5 V red
    dark          lights off                  0.5 V red
    dcmu          0.5 V red (+ DCMU)          0.5 V red
    white         0.5 V red + G,B at 3.0 V    0.5 V red

Every arm is RECORDED under identical red-only illumination. The perturbation
is what happens between acquisitions; the measurement is always made the same
way. That is not a stylistic choice -- it is forced by the ISP.

Measured on M1, 2026-10-01 (11af00e079, see
scripts/calibration/camtests/ccm_crosstalk_test.py): imx477_scientific.json
carries 19 colour correction matrices, none of them the identity, and WHICH one
is applied depends on the AWB colour-temperature estimate, i.e. on the
illumination spectrum. With the red LED held at 0.5 V throughout, the red
channel reads 86.2 under red only, 25.5 with green added (-70%) and 146.8 with
blue added (+70%). So a red-channel recording made under green and blue light
is not comparable to one made under red alone -- not by a fixed offset, because
the transform itself changes. Dropping to red for the 60 s acquisition removes
the problem at the source and needs no change to the camera tuning.

Green and blue mean intensity are still measured per frame in every condition.
In every arm they should now read near zero during acquisition (reference:
g=0.050, b=0.016). They are no longer a measurement of the perturbation -- they
are the control that proves the lights actually came down before the clip was
recorded. A white-arm clip with elevated g/b means the switch did not take.

    create_exp("dcmu")   open the experiment, name it, arm the condition
    start_acq()          begin sampling (this is when the lights are taken over)
    cleanup()            lights off, save, sync and stop the schedule
    exp.close()          finish the experiment (must be typed by the operator;
                         cleanup() runs as a scheduled job and close() cannot
                         join the scheduler thread from inside it)

The lights are NOT touched until start_acq(). Trap cells under 0.5 V red for as
long as you need after create_exp(); the condition only takes effect at the end
of the first acquisition -- which for `white` means the perturbation starts
after the first clip, exactly as `dark` goes dark after its first clip.
"""


## --------------------------------------------------------------------------
##  Conditions
## --------------------------------------------------------------------------
##  light_idle : illumination between acquisitions.
##  light_acq  : illumination while recording. Always 0.5 V red present.
##
##  The four arms are data, not code paths: capture() always does
##  setVs(light_acq) -> record -> setVs(light_idle). For every condition except
##  `dark` the two are equal, so the trailing set is a no-op.

V_RED = 0.5
V_MAX = 3.0            ## hardware full scale is 3.3 V (volt/3.3 -> duty_u16);
                       ## the calibration sweep tops out at 3.0 V, so 3.0 it is.

DARK  = (0.0,   0.0,   0.0)
RED   = (V_RED, 0.0,   0.0)
WHITE = (V_RED, V_MAX, V_MAX)

CONDITIONS = {
	"control": {"light_idle": RED,   "light_acq": RED,
				"note": "Control condition. 0.5 V red continuous. "
						"Medium contains the control delivery vehicle only."},

	"dark":    {"light_idle": DARK,  "light_acq": RED,
				"note": "Dark condition. Lights off except during the 60 s "
						"acquisition, when 0.5 V red is applied. Medium "
						"contains the control delivery vehicle only."},

	"dcmu":    {"light_idle": RED,   "light_acq": RED,
				"note": "DCMU condition. 0.5 V red continuous. Medium contains "
						"5 umol/mL DCMU. See light_dcmu_perturbation.md."},

	"white":   {"light_idle": WHITE, "light_acq": RED,
				"note": "White condition. 0.5 V red with green and blue at "
						"3.0 V between acquisitions; red only (0.5, 0, 0) "
						"during the 60 s acquisition, so the recording is made "
						"under the same illumination as every other arm. "
						"Medium contains the control delivery vehicle only."},
}


## --------------------------------------------------------------------------
##  Setup
## --------------------------------------------------------------------------

def create_exp(condition):
	"""Open the experiment for one condition and arm it.

	The condition goes into the experiment name, so it is visible in the
	directory listing when the four microscopes are collated.
	"""
	global exp, scope
	scope = ScopeAssembly.current

	if condition not in CONDITIONS:
		raise KeyError(f"Unknown condition {condition!r}. "
					   f"One of: {', '.join(CONDITIONS)}")

	exp = Experiment.Construct(["sampled_longterm_traj", "light_perturb", condition])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	## One summary row per clip. The per-frame records go to a CSV beside each
	## clip -- a MeasurementStream call is a YAML write to disk, so it cannot
	## be done per frame. This stream is the 44-point perturbation curve.
	exp.new_measurementstream("chstats",
		monitors=["split", "condition", "acq", "csv", "frames"],
		measurements=["g_mean", "g_std", "b_mean", "b_std"])

	exp.attribs["sampling_period_hours"] = 0.5
	exp.attribs["sampling_hours"] = 22
	exp.attribs["tandh_sampling_period_minutes"] = 5

	exp.attribs["chunk_size_sec"] = 60
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 3
	exp.attribs["quality"] = 100
	exp.attribs["num_threads"] = 3
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts"
	exp.attribs["measure_bg"] = True
	exp.attribs["sync_files"] = True
	exp.attribs["auto_cleanup"] = True
	exp.attribs["beacon_stabilization_delay_s"] = 1

	## In the dark condition the LEDs are cold-started every 30 min, so they
	## need longer to settle than the 1 s the always-on conditions get away
	## with. AeEnable/AwbEnable are off, so this is LED warm-up only.
	exp.attribs["light_stabilization_delay_s"] = 5

	set_condition(condition)

	load_protocols()
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def load_protocols():
	"""Copy the protocols into the experiment. A missing file is a note, not a
	crash -- the scopes should not refuse to start over a protocol that has not
	been written yet."""
	global exp
	os.makedirs("protocols", exist_ok=True)
	for src in ("experiments/masterprotocols/masterprotocol_June26.md",
				"experiments/selectswimmers.md",
				"experiments/light_dcmu_perturbation.md"):
		dst = os.path.join("protocols", os.path.basename(src))
		try:
			Protocol(src).write(dst)
			log.info(f"Loaded protocol: {src}")
		except Exception as e:
			print(Panel(f"[red]Protocol not loaded: {src}\n{e}", title="protocol"))
			exp.note(f"Protocol could not be loaded: {src} ({type(e).__name__}: {e})")


def set_condition(name, force=False):
	"""Arm one of the four conditions. Does NOT touch the lights.

	The lights stay wherever you have them, so cells can be trapped under
	0.5 V red for as long as needed. The condition is applied by start_acq(),
	at the end of the first acquisition.

	Refuses to change the condition once acquisitions have started, since that
	would mix two arms into one dataset. force=True overrides.
	"""
	global exp
	exp = Experiment.current

	if name not in CONDITIONS:
		raise KeyError(f"Unknown condition {name!r}. One of: {', '.join(CONDITIONS)}")

	done = len(exp.mstreams["acq"].readings)
	if done and not force:
		raise RuntimeError(f"{done} acquisitions already recorded under "
						   f"`{exp.attribs.get('condition')}`. Changing the "
						   f"condition now would mix two arms in one dataset. "
						   f"Pass force=True if that is really what you want.")

	spec = CONDITIONS[name]
	exp.attribs["condition"] = name
	exp.attribs["light_idle"] = spec["light_idle"]
	exp.attribs["light_acq"] = spec["light_acq"]
	exp.attribs["light"] = spec["light_acq"]      ## compatibility with mjpeg_sampling
	exp.attribs["condition_note"] = spec["note"]
	exp.attribs["group"] = f"lightpert_{name}"

	exp.log_event("condition_set", attribs={"condition": name,
										    "light_idle": spec["light_idle"],
										    "light_acq": spec["light_acq"],
										    "forced": bool(done)})
	exp.note(f"Condition `{name}` armed. {spec['note']}")

	print(Panel(f"condition  : [bold]{name}\n"
				f"light_acq  : {spec['light_acq']}   (while recording)\n"
				f"light_idle : {spec['light_idle']}   (between acquisitions)\n\n"
				f"{spec['note']}\n\n"
				f"[yellow]Lights unchanged. Trap cells now; the condition is "
				f"applied at the end of the first acquisition.",
				title="set_condition"))
	return spec


## --------------------------------------------------------------------------
##  Acquisition
## --------------------------------------------------------------------------

global split_no
split_no = 0


def filename_fn(split_no):
	global exp
	stamp = str(datetime.datetime.now()).split(".")[0] \
			.replace(" ", "__").replace(":", "_").replace("-", "_")
	return exp.newfile(f"{stamp}__{time.time_ns()}__split_{split_no}.mjpeg",
					   abspath=False)


def write_intensities(filename, records):
	"""Dump one clip's per-frame green/blue means beside the clip, and return
	the summary row.

	One CSV per clip rather than one appended file for the whole run: each clip
	already carries its own .tpts sidecar, and ExpSync moves clips individually
	with remove_source=True, so a single file being appended to while sync is
	moving data around is a hazard. Records are already sorted by t_ns.
	"""
	global exp
	csvname = filename.replace(".mjpeg", "_intensities.csv")
	with open(csvname, "w") as f:
		f.write("t_ns,g,b\n")
		for r in records:
			f.write(f'{r["t_ns"]},{r["g"]:.4f},{r["b"]:.4f}\n')
	exp.log("filename_created", attribs={"filename": csvname,
										 "frames": len(records)})

	g = np.array([r["g"] for r in records]) if records else np.array([0.0])
	b = np.array([r["b"] for r in records]) if records else np.array([0.0])
	return csvname, g, b


def capture():
	"""Record one clip under the armed condition. Returns True on success.

	No per-condition branch: light_acq is applied, the clip is recorded, and
	light_idle is restored. For every condition but `dark` those are equal.

	A failed acquisition is recorded and swallowed, NOT re-raised.
	ExpScheduler.loop runs `while not end_thread: self.run_pending()` with no
	try/except (experiment.py:72), so an exception escaping a scheduled job
	kills the scheduler thread outright -- taking the remaining 40-odd
	acquisitions, the tandh sampling and auto_cleanup with it, and leaving the
	lights wherever they were. One bad clip must not end a 22 h run.
	(mjpeg_sampling.py re-raises here, so it has that failure mode.)
	"""
	global exp, split_no
	exp = Experiment.current
	scope = ScopeAssembly.current

	scope.beacon.on()
	time.sleep(exp.attribs["beacon_stabilization_delay_s"])

	## Bring the illumination up for the acquisition and let the LEDs settle.
	scope.lit.setVs(*exp.attribs["light_acq"])
	time.sleep(exp.attribs["light_stabilization_delay_s"])

	filename = filename_fn(split_no)
	acq = exp.mstreams["acq"](acq=filename)

	## A fresh encoder per clip. No flush_fn: a 60 s clip is ~1500 records, so
	## drain() at the end is enough -- the periodic flush exists for the
	## continuous recordings, where memory would grow over hours.
	encoder = JpegEncoderRedWithBGStats(q=exp.attribs["quality"],
										num_threads=exp.attribs["num_threads"]) \
			  if exp.attribs["measure_bg"] else None

	ok = True
	try:
		scope.cam.open()
		scope.cam.configure()
		scope.cam.read(exp.attribs["camera_mode"],
					   filename,
					   tsec=exp.attribs["chunk_size_sec"],
					   show_preview=False,
					   quality=exp.attribs["quality"],
					   encoder=encoder)
	except Exception as e:
		ok = False
		print(Panel(f"[red]split {split_no} :: acq failed\n{type(e).__name__}: {e}",
					title="capture"))
		exp.log_event("acq_failed", attribs={"split": split_no, "filename": filename,
											 "error": f"{type(e).__name__}: {e}"})
		exp.note(f"{split_no} :: acq failed ({type(e).__name__}: {e}). "
				 f"Continuing with the schedule.")
	finally:
		try:
			scope.cam.close()
		except Exception as e:
			log.error(f"camera close failed after split {split_no}: {e}")
		## Return to the condition's resting illumination. For `dark` this is
		## what switches the lights back off; for the rest it changes nothing.
		## In the finally block so the lights are restored even on failure.
		scope.lit.setVs(*exp.attribs["light_idle"])

	## Drain the channel intensities -- read() discards action return values,
	## so the encoder reference held here is the only way to reach them.
	if ok and encoder is not None:
		records = encoder.drain()
		csvname, g, b = write_intensities(filename, records)
		exp.mstreams["chstats"](split=split_no,
								condition=exp.attribs["condition"],
								acq=filename, csv=csvname, frames=len(records),
								g_mean=round(float(g.mean()), 4),
								g_std=round(float(g.std()), 4),
								b_mean=round(float(b.mean()), 4),
								b_std=round(float(b.std()), 4)).panel()

		expected = exp.attribs["chunk_size_sec"] * exp.attribs["fps"]
		if len(records) < 0.9 * expected:
			exp.note(f"{split_no} :: only {len(records)}/{expected} frames "
					 f"measured -- the encoder is dropping frames.")

	split_no = split_no + 1
	scope.beacon.off()
	if ok and exp.attribs["sync_files"]:
		## Only the clip is moved; the .tpts and _intensities.csv sidecars are
		## left for the final sync_dir(), as in mjpeg_sampling.py.
		exp.sync_file_bg(filename, remove_source=True)
	return ok


def record_sensor():
	"""Read temperature and humidity."""
	scope = ScopeAssembly.current
	tandh = Experiment.current.mstreams["tandh"]
	try:
		value = scope.tandh.read()
	except Exception:
		print("[red]TandH reading failed![default]")
		value = {"temp": 0, "humidity": 0}
	r = tandh(**value)
	r.panel()


def start_acq():
	"""Begin sampling. This is where the script takes control of the lights."""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current

	if "condition" not in exp.attribs:
		raise RuntimeError("No condition armed. Call create_exp(<condition>) or "
						   "set_condition(<condition>) first -- refusing to "
						   f"start. One of: {', '.join(CONDITIONS)}")

	print("[red]Clearing experiment scheduler...")
	exp.schedule.clear()

	## Handover: until this point the lights were the operator's, for trapping.
	exp.log_event("condition_armed", attribs={"condition": exp.attribs["condition"],
											  "light_idle": exp.attribs["light_idle"],
											  "light_acq": exp.attribs["light_acq"]})
	exp.note(f'Acquisition started under condition `{exp.attribs["condition"]}`. '
			 f'Lights are now under script control.')

	## Temperature and humidity
	record_sensor()
	exp.schedule.every(exp.attribs["tandh_sampling_period_minutes"]).minutes \
		.until(timedelta(hours=exp.attribs["sampling_hours"])).do(record_sensor)

	## First acquisition, then every sampling_period_hours
	if not capture():
		print(Panel("[red]The first acquisition failed. The schedule is still "
					"being set up in case the scope recovers, but check the "
					"microscope now.", title="start_acq"))
	exp.schedule.every(exp.attribs["sampling_period_hours"]).hours \
		.until(timedelta(hours=exp.attribs["sampling_hours"])).do(capture)

	if exp.attribs["auto_cleanup"]:
		exp.schedule.every(exp.attribs["sampling_hours"] + 1).hours \
			.until(timedelta(hours=exp.attribs["sampling_hours"] + 2)).do(cleanup)

	print(Panel(Pretty(exp.schedule.get_jobs()), title="Scheduled jobs"))


def cleanup():
	"""Offload the experiment and stop the schedule. Does NOT close.

	cleanup() is itself a scheduled job (auto_cleanup), so it runs on the
	exp.schedule.loop thread. exp.close() ends with
	self.schedule.thread.join(), and a thread cannot join itself -- that raises
	`RuntimeError: cannot join current thread`, which kills the scheduler
	thread and skips everything after the join in close(): os.chdir(lastwd) and
	Share.updateps1(). mjpeg_sampling.py hit exactly this.

	So closing is left to the operator. Once this has run, type:

	    exp.close()
	"""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.lit.setVs(*DARK)
	exp.logs.update(scope.get_config())
	exp.schedule.clear()            ## removes the current job as well
	exp.schedule.end_thread = True  ## stop the loop once this job returns
	exp.__save__()
	print(exp.mstreams["chstats"].tabulate("split", "condition", "frames",
										   "g_mean", "b_mean"))
	exp.sync_dir()
	exp.note("Data offloaded and schedule stopped. Experiment left open")
	print(Panel("[yellow]Data offloaded, schedule stopped. Lights off.\n"
				"The experiment is still OPEN. Type [bold]exp.close()[/bold] "
				"to finish it.", title="cleanup"))


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	print("Lights ready...")
	scope.cam.close()
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.off()
	print(Panel(f'create_exp("<condition>") -> start_acq() -> cleanup()\n\n'
				f'conditions: {", ".join(CONDITIONS)}',
				title="light perturbation"))
