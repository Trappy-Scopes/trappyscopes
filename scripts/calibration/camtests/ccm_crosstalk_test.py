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

import json
import logging as log
import os
import shutil
import time

import yaml

import numpy as np
from rich import print
from rich.panel import Panel
from rich.table import Table

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly


__description__ = \
"""Is the camera's red channel actually red, or a mix of all three?

Motivated by a measurement from encoder_channel_tests on 2026-10-01 (M1,
a95e8c7406): with the red LED held at 0.5 V in BOTH conditions, the mean red
channel fell from 86.14 under red-only light to 52.19 under white light -- a
39.4% drop -- while lux_estimate showed total illumination RISING 9.4x
(53.8 -> 505.1). Adding light cannot remove red photons, so the ISP must be
subtracting green and blue from red. That is what a colour correction matrix
with negative off-diagonal terms does.

It matters because the `white` arm of the light perturbation experiment records
the red channel while green and blue are on. If red is contaminated by a
negative blue term that scales with blue brightness, that arm is not comparable
to the other three -- which is the whole point of the experiment. The red-only
arms (control, dark, dcmu) are unaffected: no green or blue, no cross-talk.

Two halves, usable independently:

    inspect_tuning()      reads the CCM out of the libcamera tuning file and,
                          with an experiment open, records it: one `ccm` row
                          per colour temperature, a `ccm_tuning` event, and a
                          COPY of the tuning file in the experiment directory.
                          Needs no camera. inspect_tuning(record=False) for the
                          static half with no experiment at all.

    create_exp()
    measure_crosstalk()   drives each light channel alone and in combination
                          and tests whether the output is ADDITIVE. A linear,
                          channel-independent pipeline must satisfy
                          R(r+g+b) = R(r) + R(g) + R(b) - 2*R(off).
                          A large negative residual is the cross-talk.
    cleanup()

run_all() does both.

This script runs on top of whatever was run earlier in the session, so it does
not assume anything about the camera: cam_reset() explicitly stops any encoder,
capture and preview, closes and reopens the camera, and clears pre_callback and
post_callback before measuring. cam_shutdown() leaves it closed and the lights
off on every exit path. The red-only condition doubles as a self-check that the
isolation worked.
"""


def _serialisable(value, what):
	"""Verify a value survives a plain YAML round trip BEFORE it is written.

	Two failure modes, both already paid for in this project:

	1. A value yaml.dump cannot represent at all -- an object holding a thread
	   lock, say -- raises on write and poisons every subsequent __save__() of
	   the experiment, long after the call that introduced it.
	   See docs/notes/picamera2.md, R1.
	2. A value that survives the full Dumper but not a safe load. numpy scalars
	   are written as !!python/object/apply:numpy._core.multiarray.scalar with a
	   binary payload, and a safe read maps that to None -- so the number is
	   silently lost rather than loudly broken, which is worse.

	Gating on safe_dump catches both: anything that passes is plain YAML that a
	plain read returns intact, with no extended parsing needed.
	"""
	try:
		yaml.safe_dump(value)
		return True
	except Exception as e:
		log.error(f"ccm_crosstalk: {what} is not serialisable "
				  f"({type(e).__name__}: {e}) -- not written.")
		return False


## The driver hardcodes this path in Camera.__init__ and Camera.open().
TUNING_PATH = "/usr/share/libcamera/ipa/rpi/vc4/imx477_scientific.json"

IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

## Algorithm blocks that can break the assumption "channel n of the output is
## channel n of the sensor". Listed so a surprise shows up as a surprise.
CHANNEL_COUPLING_BLOCKS = {
	"rpi.ccm":         "colour correction matrix -- mixes channels by design",
	"rpi.alsc":        "lens shading -- per-channel spatial gains",
	"rpi.awb":         "auto white balance -- per-channel gains (AwbEnable is False)",
	"rpi.black_level": "black level subtraction -- per-channel offsets",
	"rpi.contrast":    "tone curve -- nonlinear, breaks additivity on its own",
	"rpi.sharpen":     "sharpening -- spatial, luminance-coupled",
	"rpi.denoise":     "denoise -- spatial",
}


## --------------------------------------------------------------------------
##  Camera state
## --------------------------------------------------------------------------

def cam_reset():
	"""Put the camera into a known state regardless of what ran before.

	This script executes on top of whatever scripts were run earlier in the
	session, which can leave the camera:

	  * with a post_callback installed. rpreview() installs one and clears it
	    only in its finally, so an interrupted preview leaves it live -- and a
	    leftover grayscale callback copies one channel over the other two,
	    which would make every number in this script identical across channels
	    and look exactly like total cross-talk.
	  * started, or mid-recording with an encoder attached
	  * with a preview window open

	open() constructs a fresh Picamera2, so the callbacks die with the old
	object -- but they are cleared explicitly here so the guarantee is stated
	rather than inherited from an implementation detail. Each teardown step is
	guarded independently: picamera2 raises if asked to stop something that was
	never started, and that must not prevent the next step from running.
	"""
	global scope
	for label, fn in (("stop_encoder", lambda: scope.cam.cam.stop_encoder()),
					  ("stop",         lambda: scope.cam.cam.stop()),
					  ("stop_preview", lambda: scope.cam.cam.stop_preview())):
		try:
			fn()
			log.info(f"cam_reset: {label} on a camera that was still running.")
		except Exception:
			pass          ## not running: nothing to stop

	try:
		scope.cam.close()
	except Exception as e:
		log.error(f"cam_reset: close failed, continuing: {e}")

	scope.cam.open()
	scope.cam.configure()
	scope.cam.cam.pre_callback = None
	scope.cam.cam.post_callback = None
	log.info("cam_reset: camera reopened, callbacks cleared.")


def cam_shutdown():
	"""Leave the camera closed and the lights off, whatever happened."""
	global scope
	try:
		scope.lit.setVs(0.0, 0.0, 0.0)
	except Exception as e:
		log.error(f"cam_shutdown: could not set lights off: {e}")
	for fn in (lambda: scope.cam.cam.stop(),
			   lambda: scope.cam.cam.stop_preview()):
		try:
			fn()
		except Exception:
			pass
	try:
		scope.cam.cam.post_callback = None
		scope.cam.close()
	except Exception as e:
		log.error(f"cam_shutdown: close failed: {e}")


## --------------------------------------------------------------------------
##  Static: what does the tuning file say?
## --------------------------------------------------------------------------

def _algorithms(tuning):
	"""Tuning files are a list of single-key dicts under "algorithms" (v2) or a
	flat dict (v1). Return {name: block} either way."""
	if "algorithms" in tuning:
		out = {}
		for entry in tuning["algorithms"]:
			out.update(entry)
		return out
	return {k: v for k, v in tuning.items() if k.startswith("rpi.")}


def inspect_tuning(path=TUNING_PATH, record=True):
	"""Print every CCM in the tuning file and say whether it is the identity.

	Needs no camera. With an experiment open and record=True it also writes the
	result into the record: one `ccm` row per colour temperature, a
	`ccm_tuning` event carrying the verdict, and a copy of the tuning file in
	the experiment directory. The tuning file is the thing that determines
	whether the red channel is red, so a measurement of channel cross-talk is
	not interpretable without knowing which tuning produced it -- and the file
	on disk can change under you between runs.

	Returns a dict of what it found, or None if the file is missing.
	"""
	exp = Experiment.current if record else None

	if not os.path.exists(path):
		print(Panel(f"[red]Tuning file not found: {path}\n"
					"Pass the correct path: inspect_tuning('/path/to/tuning.json')",
					title="inspect_tuning"))
		if exp:
			exp.log_event("ccm_tuning", attribs={"path": path, "found": False})
			exp.note(f"ccm_crosstalk: tuning file not found at {path}.")
		return None

	with open(path) as f:
		tuning = json.load(f)
	algos = _algorithms(tuning)
	found_ccms = []

	## --- the CCMs ---------------------------------------------------------
	ccm_block = algos.get("rpi.ccm")
	if ccm_block is None:
		print(Panel("[yellow]No rpi.ccm block in this tuning file -- no colour "
					"correction matrix is applied. Channel mixing, if any, "
					"comes from somewhere else.", title=os.path.basename(path)))
		all_identity = True
	else:
		table = Table(title=f"rpi.ccm -- {os.path.basename(path)}")
		table.add_column("CT (K)", justify="right")
		for label in ("Rr", "Rg", "Rb", "Gr", "Gg", "Gb", "Br", "Bg", "Bb"):
			table.add_column(label, justify="right")
		table.add_column("identity?", justify="center")

		all_identity = True
		for entry in ccm_block.get("ccms", []):
			ccm = [float(v) for v in entry["ccm"]]
			is_id = all(abs(a - b) < 1e-6 for a, b in zip(ccm, IDENTITY))
			all_identity &= is_id
			## JSON gives int/float/str/None, all plain YAML. ct is coerced
			## anyway so a string "4000" in a hand-edited tuning cannot change
			## the column type between runs.
			ct = entry.get("ct", None)
			ct = float(ct) if ct is not None else None
			found_ccms.append({"ct": ct, "ccm": ccm, "identity": bool(is_id)})
			table.add_row(str(ct if ct is not None else "?"),
						  *[f"{v:+.3f}" for v in ccm],
						  "[green]yes" if is_id else "[red]NO")
			if exp and "ccm" in exp.mstreams:
				row = dict(ct=ct, identity=bool(is_id),
						   **{k: float(v) for k, v in
							  zip(("Rr", "Rg", "Rb", "Gr", "Gg", "Gb",
								   "Br", "Bg", "Bb"), ccm)})
				if _serialisable(row, f"ccm row ct={ct}"):
					exp.mstreams["ccm"](**row)
		print(table)

		## The off-diagonal terms of the red row are what pull red down when
		## green and blue are bright: R_out = Rr*R + Rg*G + Rb*B.
		worst = None
		for entry in ccm_block.get("ccms", []):
			ccm = [float(v) for v in entry["ccm"]]
			mix = abs(ccm[1]) + abs(ccm[2])           ## Rg + Rb
			if worst is None or mix > worst[1]:
				worst = (entry.get("ct", "?"), mix, ccm)
		if worst and worst[1] > 1e-6:
			ct, _, ccm = worst
			print(Panel(
				f"Red row at CT={ct}: R_out = {ccm[0]:+.3f}*R {ccm[1]:+.3f}*G {ccm[2]:+.3f}*B\n\n"
				f"[yellow]The green and blue terms are non-zero, so the red channel "
				f"is a mix. With AwbEnable=False the CCM is still applied -- AWB "
				f"only chooses WHICH matrix is interpolated, it does not disable it.",
				title="red row"))

	## --- other blocks that couple channels --------------------------------
	present = Table(title="other blocks that can couple channels")
	present.add_column("block"); present.add_column("present"); present.add_column("why it matters")
	for name, why in CHANNEL_COUPLING_BLOCKS.items():
		if name == "rpi.ccm":
			continue
		present.add_row(name, "[yellow]yes" if name in algos else "[green]no", why)
	print(present)

	verdict = ("[green]Every CCM is the identity -- the tuning is not the cause."
			   if all_identity else
			   "[red]At least one CCM is NOT the identity. This is consistent with "
			   "the 39.4% red drop measured on 2026-10-01.")
	print(Panel(verdict, title="inspect_tuning"))

	## Built from JSON and Python literals only -- no numpy, no objects. The
	## tuning JSON is NOT copied in wholesale; only these fields are lifted,
	## so a future tuning file cannot smuggle something unrepresentable in.
	version = tuning.get("version")
	result = {"path": str(path),
			  "version": float(version) if isinstance(version, (int, float)) else str(version),
			  "blocks": [str(b) for b in sorted(algos)],
			  "ccms": found_ccms,
			  "all_identity": bool(all_identity)}

	if exp:
		## Keep the file itself: the measurement is uninterpretable without it,
		## and the copy on the Pi can change between runs.
		try:
			dst = exp.newfile(os.path.basename(path), abspath=False)
			shutil.copy(path, dst)
			result["copy"] = dst
		except Exception as e:
			log.error(f"inspect_tuning: could not copy tuning file: {e}")
			exp.note(f"ccm_crosstalk: tuning file could not be copied ({e}).")

		attribs = {**result, "found": True}
		if _serialisable(attribs, "ccm_tuning attribs"):
			exp.log_event("ccm_tuning", attribs=attribs)
		else:
			## Never let a bad attribs dict reach exp.logs -- it would break
			## every later __save__(). Degrade to a note.
			exp.log_event("ccm_tuning", attribs={"path": str(path), "found": True,
												 "all_identity": bool(all_identity),
												 "detail": "see note"})
		exp.note(f"ccm_crosstalk: tuning {os.path.basename(path)} -- "
				 f"{len(found_ccms)} CCM(s), all_identity={all_identity}.")

	return result


## --------------------------------------------------------------------------
##  Live: is the output additive?
## --------------------------------------------------------------------------

def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["camtests", "ccm", "crosstalk"])

	## One row per illumination condition: the three output channel means.
	exp.new_measurementstream("crosstalk",
		monitors=["condition", "rV", "gV", "bV", "frames"],
		measurements=["r", "g", "b"])

	## One row per CCM in the tuning file, so the matrix that was in force is
	## part of the record rather than only printed to the terminal.
	exp.new_measurementstream("ccm",
		monitors=["ct", "identity"],
		measurements=["Rr", "Rg", "Rb", "Gr", "Gg", "Gb", "Br", "Bg", "Bb"])

	## One row per additivity test.
	exp.new_measurementstream("additivity",
		monitors=["channel", "predicted", "measured"],
		measurements=["residual", "residual_pct"])

	exp.attribs["voltage"] = 0.5          ## same drive used on every channel
	exp.attribs["frames"] = 30            ## frames averaged per condition
	exp.attribs["settle_s"] = 5           ## LED warm-up, cold start each time
	exp.attribs["tuning"] = TUNING_PATH
	print(Panel(f"voltage {exp.attribs['voltage']} V on every channel, "
				f"{exp.attribs['frames']} frames per condition",
				title="ccm_crosstalk_test"))


def _channel_means(frames):
	"""Mean of each output channel over `frames` captured arrays.

	capture_array returns a copy, so this measures the same pipeline output the
	encoders see -- no MappedArray, no encoder, no files.

	Returns a plain list of three Python floats, NOT a numpy array: numpy
	scalars leak into every value derived from them, and a numpy scalar written
	to the experiment reads back as None under a safe YAML load. Converting
	once here is the only place that has to remember.
	"""
	global scope
	acc = np.zeros(3, dtype=np.float64)
	for _ in range(frames):
		arr = scope.cam.cam.capture_array("main")
		acc += arr.reshape(-1, 3).mean(axis=0)
	return [float(v) for v in (acc / frames)]


def measure_crosstalk():
	"""Drive each channel alone and in combination, and test additivity.

	If the pipeline were linear and channel-independent, output under combined
	illumination would be the sum of the outputs under each channel alone, with
	the dark level counted once:

	    R(r+g+b) = R(r) + R(g) + R(b) - 2*R(off)

	A large negative residual means the pipeline is subtracting one channel from
	another. Splitting it into r+g and r+b says WHICH channel does the
	subtracting -- the 2026-10-01 measurement only used white, so green's and
	blue's contributions could not be separated.
	"""
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current

	V = exp.attribs["voltage"]
	frames = exp.attribs["frames"]
	conditions = {
		"off":   (0.0, 0.0, 0.0),
		"r":     (V,   0.0, 0.0),
		"g":     (0.0, V,   0.0),
		"b":     (0.0, 0.0, V),
		"r+g":   (V,   V,   0.0),
		"r+b":   (V,   0.0, V),
		"g+b":   (0.0, V,   V),
		"r+g+b": (V,   V,   V),
	}

	means = {}
	cam_reset()
	scope.cam.cam.start()
	try:
		for name, volts in conditions.items():
			scope.lit.setVs(*volts)
			time.sleep(exp.attribs["settle_s"])
			means[name] = _channel_means(frames)
			r, g, b = means[name]
			row = dict(condition=str(name), rV=float(volts[0]),
					   gV=float(volts[1]), bV=float(volts[2]),
					   frames=int(frames), r=round(r, 4), g=round(g, 4),
					   b=round(b, 4))
			if _serialisable(row, f"crosstalk row {name}"):
				exp.mstreams["crosstalk"](**row)
			print(f"  {name:6} {volts}  ->  r={r:7.3f}  g={g:7.3f}  b={b:7.3f}")

			## Self-check on the red-only condition. With a working pipeline
			## the reference measurement is r=86.1, g=0.054, b=0.028 -- three
			## orders of magnitude apart. Three near-equal channels means
			## something is broadcasting one channel over the others, i.e. a
			## post_callback survived from an earlier script despite
			## cam_reset(). Every later number would be meaningless, so stop.
			if name == "r" and r > 1.0:
				spread = max(abs(g - r), abs(b - r)) / r
				if spread < 0.05:
					raise RuntimeError(
						f"Red-only light gives r={r:.3f} g={g:.3f} b={b:.3f} -- "
						f"all three channels within {spread:.1%}. A channel "
						f"broadcast callback is still installed; the camera was "
						f"not isolated from whatever ran before. Aborting.")
	finally:
		cam_shutdown()

	## --- results table ----------------------------------------------------
	table = Table(title=f"output channel means, {V} V per channel")
	table.add_column("illumination"); 
	for c in ("r", "g", "b"):
		table.add_column(f"{c}_out", justify="right")
	for name in conditions:
		table.add_row(name, *[f"{v:.3f}" for v in means[name]])
	print(table)

	## --- additivity -------------------------------------------------------
	off = means["off"]
	print()
	for i, ch in enumerate(("r", "g", "b")):
		## All plain floats already -- _channel_means converts at the source --
		## but round()/float() here keeps that true if it ever stops being.
		predicted = float(means["r"][i] + means["g"][i] + means["b"][i] - 2 * off[i])
		measured = float(means["r+g+b"][i])
		residual = measured - predicted
		pct = 100.0 * residual / predicted if predicted else 0.0
		row = dict(channel=str(ch), predicted=round(predicted, 4),
				   measured=round(measured, 4), residual=round(residual, 4),
				   residual_pct=round(float(pct), 2))
		if _serialisable(row, f"additivity row {ch}"):
			exp.mstreams["additivity"](**row).panel()

	## --- which channel pulls red down? ------------------------------------
	r_alone = means["r"][0]
	drop_g = means["r+g"][0] - (r_alone + means["g"][0] - off[0])
	drop_b = means["r+b"][0] - (r_alone + means["b"][0] - off[0])
	print(Panel(
		f"red alone                        : {r_alone:7.3f}\n"
		f"red with green added, residual   : {drop_g:+7.3f}\n"
		f"red with blue  added, residual   : {drop_b:+7.3f}\n\n"
		f"Negative residuals mean that channel is being subtracted from red.\n"
		f"Compare against the 2026-10-01 result: red fell 86.14 -> 52.19\n"
		f"(-39.4%) going from red-only to white at the same 0.5 V red drive.",
		title="who subtracts from red"))

	exp.note(f"ccm_crosstalk: red alone {r_alone:.3f}; residual on adding green "
			 f"{drop_g:+.3f}, on adding blue {drop_b:+.3f}.")
	return means


def run_all():
	"""Static inspection, then the live measurement.

	create_exp() first -- both halves record into the open experiment.
	"""
	if Experiment.current is None:
		raise RuntimeError("No experiment open. Call create_exp() first, or "
						   "inspect_tuning(record=False) for the static half "
						   "on its own.")
	inspect_tuning()
	measure_crosstalk()


def cleanup():
	global exp, scope
	exp = Experiment.current
	scope = ScopeAssembly.current
	cam_shutdown()
	exp.logs.update(scope.get_config())
	exp.schedule.clear()
	exp.__save__()
	print(exp.mstreams["crosstalk"].tabulate("condition", "r", "g", "b"))
	exp.sync_dir()
	exp.close()


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	scope.beacon.off()
	print(Panel("inspect_tuning()  -- static, no camera needed\n"
				"create_exp() -> measure_crosstalk() -> cleanup()\n"
				"run_all()         -- both",
				title="ccm_crosstalk_test"))
