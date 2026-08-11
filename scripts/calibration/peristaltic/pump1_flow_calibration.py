"""
Peristaltic pump flow calibration -- fast (prime) and pulsed (perfusion) modes.

Calibrates ONE pump (pump1, channel 1) and copies the result to the others: the
four pumps are multiplexed per channel and the microfluidic device varies more
between chips than the pumps do between units, so a per-pump calibration would
be false precision. What we want here is an approximate flow rate.

    fast mode   -- priming the line, chip NOT connected. One speed, timed runs.
    pulsed mode -- perfusion, chip INLINE. Volume per 5 s burst at several
                   speeds, because a burst is not 5 s of steady flow: spin-up
                   and stiction eat part of every one.

Runs against real hardware, or against a simulated rig (simulated=True) that
synthesises the cylinder readings -- so the whole procedure and all of its
arithmetic can be exercised in seconds before touching media.

RUNNING THIS AFTER THE PERFUSION SCRIPT
Scripts are exec'd into the CLI globals, so two scripts loaded in succession
share one namespace and the second silently wins every name they have in
common. The order that works:

    ts keypad_pump_control.py     # chambertests: perfusion run
    >>> stop()                    # closes THAT experiment, stops the pumps,
                                  #   cancels the keypad jobs
    ts pump1_flow_calibration.py  # loads; starts nothing
    >>> cal_run(simulated=True)   # rehearse end to end, you type the volumes
    >>> cal_run(simulated=False)  # or the real thing

cal_run() walks the whole procedure in order and prompts where a human has to
act; its docstring lists every step and the argument that changes it. The
individual cal_* steps remain callable on their own.

The keypad itself plays no part in calibration: the pump is commanded directly,
and cal_setup() cancels any keypad polling left running so nothing else can
change speed or mode mid-measurement.

Every entry point here is prefixed cal_ for that reason, so stop() still means
what it meant in the control script -- safe-state the pumps and close the
perfusion experiment -- and is never shadowed by this file. Loading this script
does not construct an Experiment; cal_create_exp() refuses if one is still open
rather than orphaning it.

READING THE CYLINDER
The outlet tube stays submerged in the measuring cylinder, so it displaces
volume and the readings need care:

    L0  level before the tube is inserted
    L1  level with the tube inserted at its working depth  <- the zero
    L2  level at the end of the run, tube still in
    L3  level after the tube is withdrawn                  <- consistency check

Delivered volume comes from L2 - L1: both are read with the tube in the same
place, so its displacement cancels. Two residual effects are corrected:

  * The displacement of the submerged tube is L1 x (1 - r) - L0, not the raw
    L1 - L0. It should equal A_tube x depth; if it does not, the tube is not at
    the depth you think.
  * As the level rises, more tube becomes submerged, so the liquid occupies a
    reduced cross-section. A cylinder is graduated for its full bore, so it
    over-reads by A_cyl / (A_cyl - A_tube). Corrected:

        V_true = (L2 - L1) x (1 - (d_tube / d_cyl)^2)

    For a 5 mm tube in a 24 mm cylinder that is 4.3 % -- small, but systematic,
    and free to remove.
  * L3 is read with the tube OUT, so it IS a true volume, and it should equal
    L2 x (1 - r) - displacement. Comparing raw differences instead would be
    wrong -- the tube-in reading is scaled by the reduced bore, and that
    scaling grows with the level. A mismatch means the tube moved.

author: Yatharth Bhasin
date: 10-August-2026
licence: MIT Licence

Copyright (c) 2026 Yatharth Bhasin

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

## Do common imports
import datetime
import math
import time
import logging as log
from rich import print
from rich.prompt import Prompt
from rich.table import Table
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly

__description__ = \
"""
Flow calibration for one peristaltic pump, fast and pulsed modes.

Fast mode: timed runs at the prime speed, chip disconnected, to get ml/min and
a prime time per ml. Pulsed mode: N cycles at each of several speeds, chip
inline, to get ml per 5 s burst -- which cannot be derived from the continuous
rate, because each burst pays a spin-up cost.

The sweep uses a shortened off-time to halve the wall clock (the on-time, and
therefore the transient, is untouched), then verifies one speed at the true
5 s / 55 s duty. If the two disagree, the chip is relaxing during the off phase
and the full-duty numbers become the calibration.

Cylinder readings are corrected for the submerged outlet tube. Results are
written to pump1.params (a persistent shelve) so they ship with every later
experiment via scope.get_config().

Set simulated=True in cal_setup() to rehearse the whole procedure with
synthetic readings.

ORDER OF USE, when following a perfusion run in the same session:
    keypad_pump_control.py -> stop() -> this script -> cal_create_exp()
All entry points are prefixed cal_, so stop() keeps its meaning from the
control script. Loading this file starts nothing.
"""

### Quick explainer
print("[bold]pump flow calibration[/bold]")
print("  cal_create_exp()      make the calibration context")
print("  cal_setup(simulated=?) bind the pump and declare the geometry")
print("  cal_levels(L0, L1)    cylinder before / after the tube goes in")
print("  cal_fast()            prime speed, chip disconnected")
print("  cal_sweep()           ml per burst across the band, chip inline")
print("  cal_verify()          one speed at the true 5s/55s duty")
print("  cal_fit_and_store()   fit, write to pump1.params, copy to others")
print("  cal_run()             [bold]all of the above, in order[/bold]")
print("  cal_report()          table of everything measured")
print("  cal_plot()            matplotlib figure of the calibration")
print("  cal_check()           complain about anything unphysical")
print("  cal_stop()            close the calibration experiment")
print("[dim]The keypad is not used here -- the pump is commanded directly. "
		"cal_setup() cancels any keypad polling still running.[/dim]")
print("[dim]After a perfusion run: stop() that experiment first, then "
		"cal_create_exp(). stop() still belongs to the control script.[/dim]")


## ---------------------------------------------------------------- config
PUMP = 1                       ## the one pump we actually calibrate
COPY_TO = (2,)                 ## pumps that inherit the result

CAL_FAST_SPEED = 0.5               ## prime speed, matches the firmware default
FAST_SECONDS = 60              ## per timed prime run
FAST_REPEATS = 3

SWEEP_SPEEDS = (0.05, 0.08, 0.11, 0.14, 0.17, 0.20)
SWEEP_CYCLES = 8               ## bursts per speed
SWEEP_OFF_S = 25               ## shortened off-time for the sweep
TRUE_ON_S = 5                  ## never changed -- the transient lives here
TRUE_OFF_S = 55                ## the duty actually used for perfusion
VERIFY_SPEED = 0.11
VERIFY_CYCLES = 5

## Geometry -- measure yours and edit, or pass to setup()
CYLINDER_ID_MM = 24.0          ## inner diameter of the measuring cylinder
TUBE_OD_MM = 5.0               ## outer diameter of the submerged outlet tube
TUBE_DEPTH_MM = 40.0           ## how deep the tube sits below the surface

CAL_PUMP_OBJ = None
CAL_SIMULATED = False
CAL_AUTO_READ = False          ## simulation answers its own cylinder readings
CAL_TIME_SCALE = 1.0           ## clock compression, simulation only
RIG = None                     ## the simulated rig, when simulating


## ---------------------------------------------------------------- geometry
def area_ratio(tube_od_mm=None, cyl_id_mm=None):
	"""(d_tube / d_cyl)^2 -- the fraction of the bore the tube occupies."""
	tube_od_mm = TUBE_OD_MM if tube_od_mm is None else tube_od_mm
	cyl_id_mm = CYLINDER_ID_MM if cyl_id_mm is None else cyl_id_mm
	if not cyl_id_mm:
		return 0.0
	return (float(tube_od_mm) / float(cyl_id_mm)) ** 2


def correct_volume(delta_ml):
	"""Difference between two tube-in readings -> true delivered volume.

	Both readings carry the same tube displacement, so it cancels; only the
	reduced-bore scaling remains.
	"""
	return float(delta_ml) * (1.0 - area_ratio())


def true_volume(reading_in, displacement_ml=None):
	"""A single tube-IN reading -> true liquid volume.

	reading_in = (V + displacement) / (1 - r), so inverting:
	    V = reading_in * (1 - r) - displacement
	Needed only for the L3 cross-check; deltas never need it.
	"""
	if displacement_ml is None:
		displacement_ml = LEVELS.get("displacement_true_ml", 0.0)
	return float(reading_in) * (1.0 - area_ratio()) - float(displacement_ml)


def expected_displacement_ml(tube_od_mm=None, depth_mm=None):
	"""Volume the submerged length of tube should displace, in ml."""
	tube_od_mm = TUBE_OD_MM if tube_od_mm is None else tube_od_mm
	depth_mm = TUBE_DEPTH_MM if depth_mm is None else depth_mm
	r_cm = float(tube_od_mm) / 20.0        ## mm diameter -> cm radius
	h_cm = float(depth_mm) / 10.0
	return math.pi * r_cm * r_cm * h_cm    ## cm^3 == ml


## ---------------------------------------------------------------- simulated rig
class SimRig:
	"""A pump and a measuring cylinder that behave plausibly.

	The point is not to imitate a pump faithfully -- it is to let the procedure
	and its arithmetic be run end to end. The truth is known, so fit_and_store()
	can be checked against it: fast_ml_min, and ml_per_cycle = a*speed + b with
	b < 0 standing for the per-burst spin-up loss.
	"""

	def __init__(self, fast_ml_min=22.0, a=1.55, b=-0.018, noise_ml=0.05,
					stiction=0.035, seed=7):
		self.truth = {"fast_ml_min": fast_ml_min, "a": a, "b": b,
						"stiction": stiction}
		self.noise_ml = noise_ml
		self._seed = seed
		self.level_ml = 0.0            ## true liquid volume in the cylinder
		self.tube_in = False
		self.speed = 0.0
		self.cycles = 0
		self.mode = "idle"

	## -- deterministic pseudo-noise, no dependency on random ----------------
	def _noise(self):
		self._seed = (1103515245 * self._seed + 12345) % (2 ** 31)
		return ((self._seed / float(2 ** 31)) - 0.5) * 2.0 * self.noise_ml

	## -- the pump surface this script uses ---------------------------------
	def ml_per_cycle(self, speed):
		if speed < self.truth["stiction"]:
			return 0.0
		v = self.truth["a"] * speed + self.truth["b"]
		return max(0.0, v)

	def deliver(self, ml):
		"""Called by CalSimPump as it runs -- this is the cylinder filling."""
		self.level_ml += float(ml)
		return self.level_ml

	## -- the cylinder ------------------------------------------------------
	def read(self):
		"""What the operator would read off the graduations, tube included."""
		reading = self.level_ml
		if self.tube_in:
			## displacement of the submerged tube, plus the reduced-bore effect
			reading = (reading + expected_displacement_ml()) / (1.0 - area_ratio())
		return round(reading + self._noise(), 2)

	def insert_tube(self):
		self.tube_in = True
		return self.read()

	def withdraw_tube(self):
		self.tube_in = False
		return self.read()


class CalSimPump:
	"""A simulated pump that is registered on the scope and driven like a real one.

	This exists so simulation exercises the SAME control path as hardware: the
	calibration calls set_pulse_duty / set_slow_speed / pulse_on and then polls
	state()["cycles"] exactly as it does against the Pico. Only two things
	differ, and both are deliberate:

	  * the clock is compressed by `time_scale`, so a 6-speed sweep that takes
	    48 minutes on the bench takes under a minute here;
	  * the volume it delivers goes into a simulated cylinder, which you may
	    either read automatically or read out loud and type in yourself.

	It delivers according to the rig's truth: a fixed rate in fast mode, and
	ml_per_cycle = a*speed + b per burst, with b < 0 for the spin-up loss.
	"""

	def __init__(self, name, rig, time_scale=1.0):
		self.name = name
		self.devicetype = "sim.pump"
		self.description = "Simulated peristaltic pump (calibration rehearsal)"
		self.rig = rig
		self.time_scale = float(time_scale)

		self.fast_ = False
		self.pulse_ = False
		self.continuous_ = False
		self.speed_ = 0.0
		self.fast_speed_ = CAL_FAST_SPEED
		self.on_s = TRUE_ON_S
		self.off_s = SWEEP_OFF_S
		self.phase_ = "idle"
		self.cycles_ = 0
		self._phase_left = None      ## time left in the current phase
		self._t = time.time()

	## -- scaled clock -------------------------------------------------------
	def _elapsed(self):
		now = time.time()
		dt = (now - self._t) * self.time_scale
		self._t = now
		return dt

	def _advance(self):
		"""Carry the clock forward, delivering whatever that implies.

		The remainder inside a phase MUST be carried in self._phase_left: a
		poll that lands mid-phase would otherwise throw its time away, and the
		cycle counter would stall part way through a run.
		"""
		dt = self._elapsed()
		if dt <= 0:
			return
		if self.fast_:
			self.rig.deliver(self.rig.truth["fast_ml_min"] * dt / 60.0)
			return
		if not self.pulse_:
			return

		guard = 0
		while dt > 0 and guard < 100000:
			guard += 1
			span = self.on_s if self.phase_ == "on" else self.off_s
			if span <= 0:
				break
			if self._phase_left is None:
				self._phase_left = span
			if dt < self._phase_left:
				self._phase_left -= dt
				break
			dt -= self._phase_left
			self._phase_left = None
			if self.phase_ == "on":
				## a burst just finished
				self.rig.deliver(self.rig.ml_per_cycle(self.speed_))
				self.cycles_ += 1
				self.phase_ = "off"
			else:
				self.phase_ = "on"

	## -- the PeristalticPump surface the calibration uses -------------------
	def set_fast_speed(self, v):
		self._advance()
		self.fast_speed_ = float(v)
		return self.fast_speed_

	def fast_on(self):
		self._advance()
		self.fast_ = True
		return True

	def fast_off(self):
		self._advance()
		self.fast_ = False
		return False

	def set_continuous(self, flag):
		self._advance()
		self.continuous_ = bool(flag)
		return self.continuous_

	def set_pulse_duty(self, on_s, off_s):
		self._advance()
		self.on_s, self.off_s = int(on_s), int(off_s)
		self._phase_left = None
		return (self.on_s, self.off_s)

	def set_slow_speed(self, v):
		self._advance()
		self.speed_ = float(v)
		return self.speed_

	def pulse_on(self):
		self._advance()
		self.pulse_ = True
		self.phase_ = "on"
		self._phase_left = None
		return True

	def stop(self):
		self._advance()
		self.fast_ = False
		self.pulse_ = False
		self.phase_ = "idle"

	def state(self):
		self._advance()
		return {"name": self.name, "cycles": self.cycles_, "phase": self.phase_,
				"speed": self.speed_, "fast": self.fast_, "pulse": self.pulse_,
				"continuous": self.continuous_,
				"slow_limits": (0.03, 0.2), "fast_speed": self.fast_speed_,
				"pulse_duty": (self.on_s, self.off_s), "percent": 50, "dir": 1,
				"mode": "fast" if self.fast_ else ("pulse" if self.pulse_ else "idle")}

	def close(self):
		self.stop()


## ---------------------------------------------------------------- setup
def cal_quiet_keypad(stop_it=True):
	"""Make sure nothing else is driving the pumps.

	The keypad is NOT needed for calibration -- the pump is commanded directly
	here. But if keypad_pump_control.py is still polling from earlier in the
	session, a keypress or its state mirror can change speed or mode in the
	middle of a measurement, and the only symptom is an outlier in the fit.

	Returns True when the coast is clear.
	"""
	running = globals().get("is_running")
	stopper = globals().get("stop_jobs")
	if callable(running):
		try:
			active = bool(running())
		except Exception:
			active = False
		if active:
			print("[yellow]The keypad control script is still polling.[/]")
			if stop_it and callable(stopper):
				stopper()
				print("  [green]Polling cancelled[/] -- the pumps are yours now.")
			else:
				print("  [dim]Call stop_jobs() before calibrating.[/dim]")
				return False
	## Park the keypad LEDs so they do not imply a mode the pump is not in.
	kp_ = getattr(ScopeAssembly.current, "kp", None)
	if kp_ is not None and stop_it:
		try:
			kp_.stop_all()
		except Exception:
			pass
	return True


def cal_create_exp(force=False):
	"""Start a calibration experiment.

	Refuses if one is already open -- typically the perfusion run you loaded
	before this script. Close that first with stop(), or pass force=True.
	"""
	global exp, scope
	scope = ScopeAssembly.current
	if exp is not None and not force and getattr(exp, "active", True):
		print("[yellow]An experiment is already open:[/] {}".format(
				getattr(exp, "name", exp)))
		print("  [dim]Close it with stop() from the previous script, or pass "
				"force=True to start a calibration alongside it.[/dim]")
		return exp
	exp = Experiment.Construct(["calibration", "peristaltic", "flow"],
								user=True, eid=True, date=True, time=True, scopeid=True)
	exp.new_measurementstream("fast",
								measurements=["run", "seconds", "delta_ml", "ml_min"])
	exp.new_measurementstream("pulse",
								monitors=["pass_", "off_s"],
								measurements=["speed", "cycles", "delta_ml",
												"ml_per_cycle", "ml_per_hour"])
	print("[green]Calibration experiment ready.[/] Now run setup().")


def cal_setup(simulated=None, pump=PUMP, auto_read=False, time_scale=60.0,
			cylinder_id_mm=CYLINDER_ID_MM, tube_od_mm=TUBE_OD_MM,
			tube_depth_mm=TUBE_DEPTH_MM, fluidics=None, tube_lot=None):
	"""Bind the pump and record the geometry the corrections depend on.

	simulated=None auto-detects: the real pump if scope.pumpset is mounted, a
	simulated one otherwise. A simulated pump is REGISTERED ON THE SCOPE as
	sim_pump<N>, so scope.draw_tree() shows it and the calibration drives it
	through the same calls it uses on hardware.

	auto_read=False (the default) still prompts you for every cylinder reading,
	so the simulation is a real rehearsal: you invent the millilitres and the
	script does a genuine calibration on them. auto_read=True lets the rig
	answer instead, which is what you want for a quick self-check of the maths.

	time_scale compresses the clock in simulation only -- 60 means a 48-minute
	sweep finishes in under a minute. It has no effect on hardware.
	"""
	global scope, exp, CAL_PUMP_OBJ, CAL_SIMULATED, RIG
	global CAL_AUTO_READ, CAL_TIME_SCALE
	global CYLINDER_ID_MM, TUBE_OD_MM, TUBE_DEPTH_MM
	scope = ScopeAssembly.current

	CYLINDER_ID_MM = float(cylinder_id_mm)
	TUBE_OD_MM = float(tube_od_mm)
	TUBE_DEPTH_MM = float(tube_depth_mm)

	remote = getattr(scope, "pumpset", None) is not None
	if simulated is None:
		simulated = not remote
	CAL_SIMULATED = bool(simulated)
	CAL_AUTO_READ = bool(auto_read) and CAL_SIMULATED
	CAL_TIME_SCALE = float(time_scale) if CAL_SIMULATED else 1.0

	## The keypad plays no part in calibration; just make sure it is not
	## driving the pumps behind our back.
	cal_quiet_keypad()

	if CAL_SIMULATED:
		RIG = SimRig()
		name = "sim_pump{}".format(pump)
		## Register it like any other device, so scope.draw_tree() shows what is
		## being driven and the rehearsal is not a special case hiding in a
		## local variable.
		CAL_PUMP_OBJ = CalSimPump(name, RIG, time_scale=CAL_TIME_SCALE)
		if getattr(scope, name, None) is None:
			try:
				scope.add_device(name, CAL_PUMP_OBJ,
									description="Simulated pump, calibration rehearsal")
			except Exception as err:
				log.error("could not register %s on the scope: %s", name, err)
		else:
			setattr(scope, name, CAL_PUMP_OBJ)
		print("[cyan]SIMULATED[/] -- driving [bold]scope.{}[/bold], clock x{:.0f}, "
				"no fluid moves.".format(name, CAL_TIME_SCALE))
		if CAL_AUTO_READ:
			print("  [dim]the rig answers its own cylinder readings[/dim]")
			print("  [dim]truth: fast {} ml/min, ml/cycle = {}*s {}, stiction {}[/dim]".format(
					RIG.truth["fast_ml_min"], RIG.truth["a"], RIG.truth["b"],
					RIG.truth["stiction"]))
		else:
			print("  [bold]You will be asked for every cylinder reading.[/bold] "
					"Invent them -- the calibration that comes out is real.")
	else:
		if not remote:
			print("[red]scope.pumpset not found and simulated=False.[/]")
			return None
		RIG = None
		CAL_PUMP_OBJ = getattr(scope, "pump{}".format(pump), None)
		if CAL_PUMP_OBJ is None:
			print("[red]scope.pump{} not found.[/]".format(pump))
			return None
		print("[yellow]REAL pump{}[/] -- fluid will move.".format(pump))

	if exp is not None:
		exp.attribs["pump"] = pump
		exp.attribs["simulated"] = CAL_SIMULATED
		exp.attribs["copy_to"] = list(COPY_TO)
		exp.attribs["cylinder_id_mm"] = CYLINDER_ID_MM
		exp.attribs["tube_od_mm"] = TUBE_OD_MM
		exp.attribs["tube_depth_mm"] = TUBE_DEPTH_MM
		exp.attribs["area_ratio"] = round(area_ratio(), 5)
		exp.attribs["fluidics"] = fluidics
		exp.attribs["tube_lot"] = tube_lot
		exp.attribs["fast_speed"] = CAL_FAST_SPEED
		exp.attribs["sweep_speeds"] = list(SWEEP_SPEEDS)
		exp.attribs["sweep_cycles"] = SWEEP_CYCLES
		exp.attribs["sweep_off_s"] = SWEEP_OFF_S
		exp.attribs["true_duty_s"] = (TRUE_ON_S, TRUE_OFF_S)

	print("  cylinder {} mm, tube {} mm, depth {} mm".format(
			CYLINDER_ID_MM, TUBE_OD_MM, TUBE_DEPTH_MM))
	print("  bore taken by the tube: [bold]{:.1f} %[/bold] "
			"-- readings are scaled by {:.4f}".format(
			area_ratio() * 100, 1.0 - area_ratio()))
	print("  a submerged tube {} mm deep should displace ~{:.2f} ml".format(
			TUBE_DEPTH_MM, expected_displacement_ml()))
	return True


## ---------------------------------------------------------------- levels
LEVELS = {}


def ask_ml(label):
	"""Read a cylinder level -- from the operator, or from the simulated rig."""
	if CAL_SIMULATED and CAL_AUTO_READ:
		value = RIG.read()
		print("  [dim]{}: {:.2f} ml (rig)[/dim]".format(label, value))
		return value
	while True:
		raw = Prompt.ask("  [cyan]{}[/cyan] -- cylinder reading in ml".format(label))
		try:
			return float(str(raw).strip())
		except ValueError:
			print("    [red]a number, please[/]")


def cal_levels(l0=None, l1=None):
	"""Record L0 (tube out) and L1 (tube in at working depth).

	L1 is the zero every later reading is measured against.
	"""
	global LEVELS
	if CAL_SIMULATED and CAL_AUTO_READ:
		RIG.withdraw_tube()
	l0 = ask_ml("L0 -- tube OUT, before insertion") if l0 is None else float(l0)
	if CAL_SIMULATED and CAL_AUTO_READ:
		RIG.insert_tube()
	l1 = ask_ml("L1 -- tube IN at working depth") if l1 is None else float(l1)

	## L1 = (L0 + displacement) / (1 - r), so the true displacement is
	## L1*(1-r) - L0. Taking the raw difference L1 - L0 would fold in the
	## reduced-bore scaling and read high.
	displaced = l1 * (1.0 - area_ratio()) - l0
	expect = expected_displacement_ml()
	LEVELS = {"L0": l0, "L1": l1,
				"displacement_true_ml": round(displaced, 3),
				"displaced_raw_ml": round(l1 - l0, 3),
				"expected_displacement_ml": round(expect, 3)}
	print("  displacement {:.2f} ml (raw difference {:.2f}), expected {:.2f} ml".format(
			displaced, l1 - l0, expect))
	if expect and abs(displaced - expect) > max(0.5, 0.3 * expect):
		print("  [yellow]That is well off -- the tube is not at the depth you "
				"think, or the geometry constants are wrong.[/]")
	if exp is not None:
		exp.attribs["levels"] = dict(LEVELS)
		exp.note("Levels: L0={} L1={} displaced={:.2f} ml (expected {:.2f})".format(
				l0, l1, displaced, expect))
	return LEVELS


def cal_close_levels(l3=None):
	"""Optional L3 -- level after withdrawing the tube. Consistency check."""
	if CAL_SIMULATED and CAL_AUTO_READ:
		RIG.withdraw_tube()
	l3 = ask_ml("L3 -- tube OUT, after the run") if l3 is None else float(l3)
	l2 = LEVELS.get("last", LEVELS.get("L1"))
	LEVELS["L3"] = l3
	if l2 is not None:
		## L3 is a tube-OUT reading, so it IS the true volume. Compare it with
		## the true volume implied by the last tube-IN reading. Comparing raw
		## differences would be wrong: the tube-in reading is scaled by the
		## reduced bore, and that scaling grows with level.
		implied = true_volume(l2)
		residual = implied - l3
		LEVELS["L3_implied_ml"] = round(implied, 3)
		LEVELS["L3_residual_ml"] = round(residual, 3)
		print("  tube-out reading {:.2f} ml, implied by the tube-in reading "
				"{:.2f} ml -> residual {:+.2f} ml".format(l3, implied, residual))
		tol = max(0.5, 0.02 * max(1.0, l3))
		if abs(residual) > tol:
			print("  [yellow]Off by more than {:.2f} ml -- the tube moved, or the "
					"cylinder/tube diameters are wrong. Volumes are approximate."
					"[/]".format(tol))
		else:
			print("  [green]Consistent -- the geometry corrections hold.[/]")
	if exp is not None:
		exp.attribs["levels"] = dict(LEVELS)
	return LEVELS


def _measure(label):
	"""Read a level and return the corrected volume since L1."""
	raw = ask_ml(label)
	LEVELS["last"] = raw
	base = LEVELS.get("L1")
	if base is None:
		print("  [red]No L1 recorded -- run levels() first.[/]")
		return None, raw
	return correct_volume(raw - base), raw


## ---------------------------------------------------------------- running
def _cal_sleep(seconds):
	"""Wall-clock wait, compressed in simulation (CAL_TIME_SCALE)."""
	scale = CAL_TIME_SCALE if CAL_TIME_SCALE else 1.0
	time.sleep(float(seconds) / scale)


def _run_fast(seconds):
	"""Identical calls for a real pump and a simulated one."""
	CAL_PUMP_OBJ.set_fast_speed(CAL_FAST_SPEED)
	CAL_PUMP_OBJ.fast_on()
	t0 = time.time()
	try:
		_cal_sleep(seconds)
	finally:
		CAL_PUMP_OBJ.fast_off()
	scale = CAL_TIME_SCALE if CAL_TIME_SCALE else 1.0
	return (time.time() - t0) * scale


def _run_cycles(speed, cycles, off_s):
	"""Run exactly `cycles` bursts, counted by the pump itself, then stop.

	Counting the pump's own cycle counter rather than sleeping for
	cycles*(on+off) means a slow serial link or a missed poll cannot silently
	change the dose. The simulated pump counts the same way, so this code path
	is the one that runs on hardware too.
	"""
	CAL_PUMP_OBJ.set_continuous(False)
	CAL_PUMP_OBJ.set_pulse_duty(TRUE_ON_S, off_s)
	CAL_PUMP_OBJ.set_slow_speed(speed)
	before = int((CAL_PUMP_OBJ.state() or {}).get("cycles", 0))
	CAL_PUMP_OBJ.pulse_on()

	scale = CAL_TIME_SCALE if CAL_TIME_SCALE else 1.0
	deadline = time.time() + (cycles * (TRUE_ON_S + off_s) * 2 + 30) / scale
	done = 0
	try:
		while done < cycles and time.time() < deadline:
			_cal_sleep(1.0)
			st = CAL_PUMP_OBJ.state() or {}
			done = int(st.get("cycles", before)) - before
			print("    [dim]cycle {}/{} phase {}[/dim]".format(
					done, cycles, st.get("phase")), end="\r")
	except KeyboardInterrupt:
		print("\n  [yellow]interrupted[/]")
	finally:
		CAL_PUMP_OBJ.stop()
	print("")
	if done < cycles:
		print("  [yellow]only {} of {} cycles completed[/]".format(done, cycles))
	return done


## ---------------------------------------------------------------- procedures
FAST = []
PULSE = []


def cal_fast(seconds=FAST_SECONDS, repeats=FAST_REPEATS):
	"""Prime speed, chip DISCONNECTED. Timed runs, read the cylinder each time."""
	global FAST
	if not _ready():
		return None
	print("[bold]Fast mode[/bold] -- chip disconnected, {} x {} s at speed {}".format(
			repeats, seconds, CAL_FAST_SPEED))
	stream = exp.mstreams["fast"] if exp is not None else None
	FAST = []
	prev = 0.0
	for i in range(repeats):
		if not CAL_SIMULATED:
			Prompt.ask("  [cyan]run {}/{}[/cyan] -- press enter to start".format(
					i + 1, repeats))
		actual = _run_fast(seconds)
		total, _raw = _measure("after run {}".format(i + 1))
		if total is None:
			return None
		delta = total - prev
		prev = total
		rate = delta * 60.0 / actual if actual else 0.0
		FAST.append({"run": i + 1, "seconds": round(actual, 2),
						"delta_ml": round(delta, 3), "ml_min": round(rate, 3)})
		print("    {:.2f} ml in {:.1f} s -> [bold]{:.2f} ml/min[/bold]".format(
				delta, actual, rate))
		if stream is not None:
			stream(run=i + 1, seconds=round(actual, 2), delta_ml=round(delta, 3),
					ml_min=round(rate, 3))
	rates = [f["ml_min"] for f in FAST]
	print("  mean [bold]{:.2f} ml/min[/bold], spread {:.2f}".format(
			_mean(rates), max(rates) - min(rates)))
	return FAST


def cal_sweep(speeds=SWEEP_SPEEDS, cycles=SWEEP_CYCLES, off_s=SWEEP_OFF_S,
				passes=2):
	"""Chip INLINE. N bursts at each speed, second pass in reverse order.

	The on-time stays at the real 5 s -- that is where the spin-up cost lives.
	Only the off-time is shortened, which is what makes this affordable.
	"""
	global PULSE
	if not _ready():
		return None
	est = len(speeds) * cycles * (TRUE_ON_S + off_s) * passes / 60.0
	print("[bold]Pulse sweep[/bold] -- {} speeds x {} cycles x {} passes, "
			"duty {}s/{}s".format(len(speeds), cycles, passes, TRUE_ON_S, off_s))
	print("  estimated {:.0f} min (the true {}s/{}s duty would be {:.0f} min)".format(
			est, TRUE_ON_S, TRUE_OFF_S,
			len(speeds) * cycles * (TRUE_ON_S + TRUE_OFF_S) * passes / 60.0))
	stream = exp.mstreams["pulse"] if exp is not None else None
	PULSE = []
	prev = LEVELS.get("_last_corrected", 0.0)
	if prev == 0.0:
		prev, _ = _measure("baseline before the sweep")

	for p in range(passes):
		order = list(speeds) if p % 2 == 0 else list(reversed(speeds))
		print("[bold]pass {}[/bold]: {}".format(p + 1, order))
		for speed in order:
			print("  speed {:.3f} -- {} cycles".format(speed, cycles))
			done = _run_cycles(speed, cycles, off_s)
			total, _raw = _measure("after speed {:.3f}".format(speed))
			if total is None:
				return None
			delta = total - prev
			prev = total
			per_cycle = delta / done if done else 0.0
			per_hour = per_cycle * 3600.0 / float(TRUE_ON_S + TRUE_OFF_S)
			row = {"pass_": p + 1, "speed": speed, "cycles": done,
					"delta_ml": round(delta, 3),
					"ml_per_cycle": round(per_cycle, 4),
					"ml_per_hour": round(per_hour, 3), "off_s": off_s}
			PULSE.append(row)
			print("    {:.2f} ml over {} cycles -> [bold]{:.3f} ml/cycle[/bold]"
					" = {:.2f} ml/h at {}s/{}s".format(
					delta, done, per_cycle, per_hour, TRUE_ON_S, TRUE_OFF_S))
			if stream is not None:
				stream(**row)
	LEVELS["_last_corrected"] = prev
	return PULSE


def cal_verify(speed=VERIFY_SPEED, cycles=VERIFY_CYCLES):
	"""Repeat one speed at the TRUE 5s/55s duty and compare ml per cycle.

	If it matches the sweep, the off-time is irrelevant and the shortened sweep
	stands. If it does not, the chip is relaxing between bursts -- and this
	number, not the sweep, is the calibration.
	"""
	if not _ready():
		return None
	print("[bold]Verify[/bold] -- speed {} at the true {}s/{}s duty, {} cycles "
			"({:.0f} min)".format(speed, TRUE_ON_S, TRUE_OFF_S, cycles,
			cycles * (TRUE_ON_S + TRUE_OFF_S) / 60.0))
	prev = LEVELS.get("_last_corrected")
	if prev is None:
		prev, _ = _measure("baseline before verify")
	done = _run_cycles(speed, cycles, TRUE_OFF_S)
	total, _raw = _measure("after verify")
	delta = total - prev
	LEVELS["_last_corrected"] = total
	per_cycle = delta / done if done else 0.0

	sweep_rows = [r["ml_per_cycle"] for r in PULSE if abs(r["speed"] - speed) < 1e-9]
	swept = _mean(sweep_rows) if sweep_rows else None
	result = {"speed": speed, "cycles": done, "delta_ml": round(delta, 3),
				"ml_per_cycle": round(per_cycle, 4),
				"sweep_ml_per_cycle": round(swept, 4) if swept else None,
				"off_s": TRUE_OFF_S}
	if swept:
		diff = (per_cycle - swept) / swept * 100.0 if swept else 0.0
		result["difference_pct"] = round(diff, 1)
		print("  {:.3f} ml/cycle at the true duty vs {:.3f} in the sweep "
				"({:+.1f} %)".format(per_cycle, swept, diff))
		if abs(diff) > 10:
			print("  [yellow]Off-time matters -- the chip relaxes between bursts. "
					"Use the full-duty numbers.[/]")
		else:
			print("  [green]Off-time does not matter -- the shortened sweep is "
					"valid.[/]")
	if exp is not None:
		exp.attribs["verify"] = result
		exp.note("Duty verification: {}".format(result))
	return result


## ---------------------------------------------------------------- fit + store
def cal_fit_and_store(copy_to=COPY_TO, dry_run=False):
	"""Fit both modes, write to pump1.params, copy to the multiplexed siblings."""
	if not PULSE and not FAST:
		print("[red]Nothing measured yet.[/]")
		return None

	calib = {"calib_dt": datetime.datetime.now(),
				"calib_simulated": CAL_SIMULATED,
				"calib_cylinder_id_mm": CYLINDER_ID_MM,
				"calib_tube_od_mm": TUBE_OD_MM,
				"calib_area_ratio": round(area_ratio(), 5),
				"calib_levels": dict(LEVELS)}

	if FAST:
		rates = [f["ml_min"] for f in FAST]
		mean = _mean(rates)
		calib["calib_fast_speed"] = CAL_FAST_SPEED
		calib["calib_fast_ml_min"] = round(mean, 3)
		calib["calib_fast_spread_ml_min"] = round(max(rates) - min(rates), 3)
		calib["calib_fast_runs"] = FAST
		calib["calib_prime_s_per_ml"] = round(60.0 / mean, 3) if mean else None

	if PULSE:
		xs = [r["speed"] for r in PULSE]
		ys = [r["ml_per_cycle"] for r in PULSE]
		slope, intercept = _linfit(xs, ys)
		calib["calib_pulse_duty"] = (TRUE_ON_S, TRUE_OFF_S)
		calib["calib_pulse_sweep_off_s"] = SWEEP_OFF_S
		calib["calib_pulse_speeds"] = xs
		calib["calib_pulse_ml_per_cycle"] = ys
		calib["calib_pulse_slope"] = round(slope, 5)
		calib["calib_pulse_intercept"] = round(intercept, 5)
		calib["calib_pulse_rows"] = PULSE
		if slope:
			calib["calib_stiction_speed"] = round(max(0.0, -intercept / slope), 4)
	if exp is not None and exp.attribs.get("verify"):
		calib["calib_verify"] = exp.attribs["verify"]

	print(_calib_table(calib))
	if dry_run:
		print("[dim]dry run -- nothing written[/dim]")
		return calib
	if CAL_SIMULATED:
		print("[yellow]Simulated -- not writing to the device shelve.[/]")
		if CAL_AUTO_READ:
			_check_against_truth(calib)
		else:
			print("  [dim]Readings were yours, so there is no truth to check "
					"against -- but the fit above is a real calibration of the "
					"numbers you gave.[/dim]")
		return calib

	targets = [PUMP] + list(copy_to)
	for n in targets:
		proxy = getattr(ScopeAssembly.current, "pump{}".format(n), None)
		if proxy is None:
			continue
		if getattr(proxy, "params", None) is None:
			try:
				proxy.make_persist()
			except Exception as err:
				log.error("could not persist pump%s: %s", n, err)
				continue
		for key, value in calib.items():
			proxy.params[key] = value
		proxy.params["calib_source_pump"] = PUMP
		proxy.params["calib_copied"] = (n != PUMP)
		print("[green]wrote calibration to pump{}[/]{}".format(
				n, " [dim](copied)[/dim]" if n != PUMP else ""))
	if exp is not None:
		exp.logs["calibration"] = {k: str(v) for k, v in calib.items()}
		exp.note("Calibration stored on pump{} and copied to {}".format(
				PUMP, list(copy_to)))
	return calib


def cal_report():
	"""Everything measured, as tables."""
	if FAST:
		t = Table(title="fast mode (prime)")
		for c in ("run", "seconds", "delta ml", "ml/min"):
			t.add_column(c)
		for f in FAST:
			t.add_row(str(f["run"]), "{:.1f}".format(f["seconds"]),
						"{:.2f}".format(f["delta_ml"]), "{:.2f}".format(f["ml_min"]))
		print(t)
	if PULSE:
		t = Table(title="pulsed mode (perfusion)")
		for c in ("pass", "speed", "cycles", "delta ml", "ml/cycle", "ml/h @5s/55s"):
			t.add_column(c)
		for r in PULSE:
			t.add_row(str(r["pass_"]), "{:.3f}".format(r["speed"]), str(r["cycles"]),
						"{:.2f}".format(r["delta_ml"]),
						"{:.4f}".format(r["ml_per_cycle"]),
						"{:.2f}".format(r["ml_per_hour"]))
		print(t)


## ---------------------------------------------------------------- plots
## Follows the light-calibration precedent (control_volt_vs_sample_intensity.py):
## build the figure from the stored calibration, save a png next to the script,
## and hand it to the experiment if it will take an image.

def cal_plot(calib=None, save=True, filename=None, show_warnings=True):
	"""Four panels from a calibration: the fit, the flow, the prime, the drift.

	    cal_plot()                    the calibration just measured
	    cal_plot(calibration(1))      whatever is stored on pump1
	    cal_plot(some_dict)           a calibration read back from an old run

	Returns (fig, axes). The panels are chosen so that a bad calibration looks
	bad rather than merely plotting smoothly:

	  A  ml per burst vs speed, one marker per pass, with the least-squares fit,
	     the verify point, and the extrapolated stiction speed
	  B  the same data as ml/hour at the TRUE duty -- the number you actually
	     perfuse at
	  C  the prime runs, with the mean and the spread
	  D  pass 1 against pass 2 at matched speeds; points off the diagonal are
	     drift, tubing fatigue or a moving tube
	"""
	import matplotlib
	matplotlib.use("Agg")
	import matplotlib.pyplot as plt

	calib = calib or _cal_current()
	if not calib:
		print("[red]Nothing to plot.[/]")
		return None, None

	rows = calib.get("calib_pulse_rows") or []
	fast = calib.get("calib_fast_runs") or []
	verify = calib.get("calib_verify") or {}
	duty = tuple(calib.get("calib_pulse_duty", (TRUE_ON_S, TRUE_OFF_S)))
	period = float(duty[0] + duty[1]) if len(duty) == 2 else 60.0

	fig, axes = plt.subplots(2, 2, figsize=(12, 8))
	(axA, axB), (axC, axD) = axes
	fig.suptitle("peristaltic pump calibration{}   {}".format(
			"  [SIMULATED]" if calib.get("calib_simulated") else "",
			calib.get("calib_dt", "")), fontsize=11)

	## -- A: ml per burst vs speed ------------------------------------------
	passes = sorted(set(r.get("pass_", 1) for r in rows))
	markers = ["o", "s", "^", "D"]
	for i, p_ in enumerate(passes):
		xs = [r["speed"] for r in rows if r.get("pass_", 1) == p_]
		ys = [r["ml_per_cycle"] for r in rows if r.get("pass_", 1) == p_]
		axA.plot(xs, ys, markers[i % len(markers)], ms=7, alpha=0.8,
					label="pass {}".format(p_))
	slope = calib.get("calib_pulse_slope")
	inter = calib.get("calib_pulse_intercept")
	if slope is not None and rows:
		lo, hi = min(r["speed"] for r in rows), max(r["speed"] for r in rows)
		span = [0.0, hi * 1.05]
		axA.plot(span, [slope * x + inter for x in span], "-", lw=1.4, color="0.35",
					label="fit  {:.3f}s {:+.4f}".format(slope, inter))
		stic = calib.get("calib_stiction_speed")
		if stic:
			axA.axvline(stic, ls=":", color="crimson", lw=1)
			axA.annotate("stiction {:.3f}".format(stic), (stic, axA.get_ylim()[1]),
							textcoords="offset points", xytext=(4, -12),
							color="crimson", fontsize=8)
	if verify.get("ml_per_cycle") is not None:
		axA.plot([verify["speed"]], [verify["ml_per_cycle"]], "*", ms=16,
					color="darkorange", zorder=5,
					label="verify @ {}s/{}s".format(duty[0], verify.get("off_s", duty[1])))
	axA.set_xlabel("unit speed")
	axA.set_ylabel("ml per {} s burst".format(duty[0]))
	axA.set_title("pulsed mode: volume per burst")
	axA.grid(alpha=0.3)
	axA.legend(fontsize=8)

	## -- B: ml/hour at the true duty ---------------------------------------
	if rows:
		xs = [r["speed"] for r in rows]
		ys = [r["ml_per_cycle"] * 3600.0 / period for r in rows]
		axB.plot(xs, ys, "o", ms=6, color="tab:blue", alpha=0.8)
		if slope is not None:
			span = [0.0, max(xs) * 1.05]
			axB.plot(span, [(slope * x + inter) * 3600.0 / period for x in span],
						"-", lw=1.4, color="0.35")
		axB.set_xlabel("unit speed")
		axB.set_ylabel("ml / hour")
		axB.set_title("perfusion rate at the true {}s/{}s duty".format(*duty))
		axB.grid(alpha=0.3)

	## -- C: the prime runs --------------------------------------------------
	if fast:
		runs = [f["run"] for f in fast]
		rates = [f["ml_min"] for f in fast]
		axC.plot(runs, rates, "o-", color="tab:green")
		mean = sum(rates) / len(rates)
		axC.axhline(mean, ls="--", color="0.4", lw=1,
					label="mean {:.2f} ml/min".format(mean))
		axC.fill_between([min(runs), max(runs)], min(rates), max(rates),
							color="tab:green", alpha=0.12)
		axC.axhline(0, color="0.7", lw=0.8)
		axC.set_xlabel("run")
		axC.set_ylabel("ml / min")
		axC.set_title("fast mode at speed {}".format(calib.get("calib_fast_speed")))
		axC.set_xticks(runs)
		axC.grid(alpha=0.3)
		axC.legend(fontsize=8)

	## -- D: pass against pass ----------------------------------------------
	if len(passes) >= 2:
		first = dict((r["speed"], r["ml_per_cycle"])
						for r in rows if r.get("pass_") == passes[0])
		second = dict((r["speed"], r["ml_per_cycle"])
						for r in rows if r.get("pass_") == passes[1])
		common = sorted(set(first) & set(second))
		if common:
			xs = [first[c] for c in common]
			ys = [second[c] for c in common]
			axD.plot(xs, ys, "o", color="tab:purple")
			for c, x, y in zip(common, xs, ys):
				axD.annotate("{:.2f}".format(c), (x, y), fontsize=7,
								textcoords="offset points", xytext=(4, 4))
			lim = max(max(xs), max(ys)) * 1.1 or 1.0
			axD.plot([0, lim], [0, lim], "--", color="0.5", lw=1)
			axD.set_xlim(0, lim)
			axD.set_ylim(0, lim)
			axD.set_xlabel("pass {} -- ml per burst".format(passes[0]))
			axD.set_ylabel("pass {} -- ml per burst".format(passes[1]))
			axD.set_title("repeatability (labels are speeds)")
			axD.grid(alpha=0.3)
	else:
		axD.text(0.5, 0.5, "one pass only\nno repeatability to show",
					ha="center", va="center", transform=axD.transAxes, color="0.5")
		axD.set_axis_off()

	## -- warnings ------------------------------------------------------------
	if show_warnings:
		notes = cal_check(calib, quiet=True)
		if notes:
			fig.text(0.01, 0.005, "  |  ".join(notes[:3]), fontsize=8,
						color="crimson", va="bottom")

	fig.tight_layout(rect=[0, 0.03, 1, 0.96])
	if save:
		filename = filename or "pump_calibration_plot.png"
		fig.savefig(filename, dpi=140)
		print("[green]Saved[/] {}".format(filename))
		if exp is not None and hasattr(exp, "add_image"):
			try:
				exp.add_image(filename, caption="Peristaltic pump calibration: "
								"volume per burst, perfusion rate, prime rate, "
								"pass-to-pass repeatability.")
			except Exception as err:
				log.error("could not attach the plot to the experiment: %s", err)
	return fig, axes


def cal_check(calib=None, quiet=False):
	"""Sanity-check a calibration and return a list of complaints.

	Worth running before anyone believes a number. These are the failures that
	look plausible on a plot but are not physical.
	"""
	calib = calib or _cal_current()
	notes = []
	if not calib:
		return notes

	fast = calib.get("calib_fast_runs") or []
	if any(f.get("delta_ml", 0) < 0 for f in fast):
		notes.append("a prime run delivered NEGATIVE volume -- the level fell")
	mean = calib.get("calib_fast_ml_min")
	spread = calib.get("calib_fast_spread_ml_min")
	if mean and spread and spread > 0.25 * abs(mean):
		notes.append("prime spread {:.2f} is {:.0f}% of the mean {:.2f}".format(
				spread, 100.0 * spread / abs(mean), mean))

	inter = calib.get("calib_pulse_intercept")
	if inter is not None and inter > 0:
		notes.append("positive intercept {:+.3f} ml -- a burst cannot deliver "
						"volume at zero speed".format(inter))
	slope = calib.get("calib_pulse_slope")
	if slope is not None and slope <= 0:
		notes.append("non-positive slope -- faster is not pumping more")

	rows = calib.get("calib_pulse_rows") or []
	dupes = {}
	for r in rows:
		dupes.setdefault(r["speed"], []).append(r["ml_per_cycle"])
	for speed, vals in sorted(dupes.items()):
		if len(vals) > 1 and max(vals) > 0:
			swing = (max(vals) - min(vals)) / max(vals)
			if swing > 0.3:
				notes.append("speed {:.2f} differs {:.0f}% between passes".format(
						speed, swing * 100))

	verify = calib.get("calib_verify") or {}
	if abs(verify.get("difference_pct") or 0) > 10:
		notes.append("verify disagrees with the sweep by {:+.0f}% -- off-time "
						"matters, or something drifted".format(
						verify["difference_pct"]))

	levels = calib.get("calib_levels") or {}
	got, want = levels.get("displacement_true_ml"), levels.get("expected_displacement_ml")
	if got and want and abs(got - want) > max(0.5, 0.3 * want):
		notes.append("tube displacement {:.2f} ml vs {:.2f} expected -- check "
						"the depth and the diameters".format(got, want))

	if not quiet:
		if notes:
			print("[yellow]Calibration warnings:[/]")
			for n in notes:
				print("  [yellow]![/] {}".format(n))
		else:
			print("[green]Calibration looks self-consistent.[/]")
	return notes


def _cal_current():
	"""Assemble a calibration dict from whatever this session has measured."""
	if not (FAST or PULSE):
		return None
	return cal_fit_and_store(dry_run=True)


## ---------------------------------------------------------------- the whole run
def cal_run(simulated=None, auto_read=False, time_scale=60.0,
			speeds=SWEEP_SPEEDS, cycles=SWEEP_CYCLES, off_s=SWEEP_OFF_S,
			passes=2, fast_seconds=FAST_SECONDS, fast_repeats=FAST_REPEATS,
			verify_speed=VERIFY_SPEED, verify_cycles=VERIFY_CYCLES,
			skip_fast=False, skip_sweep=False, skip_verify=False,
			store=True, geometry=None):
	"""Run the whole calibration in order, start to finish.

	    cal_run(simulated=True)          rehearse: you type the millilitres
	    cal_run(simulated=True, auto_read=True)   quick self-check of the maths
	    cal_run(simulated=False)         the real thing

	The steps, and how to change each of them:

	  1. cal_create_exp()      -- skipped if an experiment is already open
	  2. cal_setup()           -- geometry={"cylinder_id_mm":.., "tube_od_mm":..,
	                              "tube_depth_mm":..} to match your cylinder
	  3. cal_levels()          -- L0 then L1. THE CHIP MUST BE DISCONNECTED for
	                              the fast step that follows
	  4. cal_fast()            -- fast_seconds / fast_repeats
	                              skip_fast=True if the prime rate is already known
	  5. pause                 -- connect the chip before the sweep
	  6. cal_sweep()           -- speeds / cycles / off_s / passes
	                              passes=1 halves it again; speeds=(...) for a
	                              coarser band
	  7. cal_verify()          -- verify_speed / verify_cycles, at the true duty
	                              skip_verify=True if you have already established
	                              that off-time does not matter
	  8. cal_fit_and_store()   -- store=False to fit and print without writing
	  9. cal_close_levels()    -- L3 cross-check
	 10. cal_report()

	Anything you skip here can still be run by hand afterwards; the results
	accumulate in the same tables.
	"""
	geometry = geometry or {}
	print("[bold]full calibration[/bold] -- {}".format(
			"simulated" if simulated else "auto-detect" if simulated is None
			else "REAL HARDWARE"))

	## 1 -----------------------------------------------------------------
	if exp is None:
		cal_create_exp()
	else:
		print("[dim]using the experiment already open[/dim]")

	## 2 -----------------------------------------------------------------
	if cal_setup(simulated=simulated, auto_read=auto_read,
					time_scale=time_scale, **geometry) is None:
		return None

	## 3 -----------------------------------------------------------------
	print("\n[bold]1/6 cylinder zero[/bold]")
	if not (CAL_SIMULATED and CAL_AUTO_READ) and not skip_fast:
		print("  [yellow]Disconnect the chip[/] -- the fast step measures the "
				"free line.")
		Prompt.ask("  press enter when the outlet is in the cylinder")
	cal_levels()

	## 4 -----------------------------------------------------------------
	if not skip_fast:
		print("\n[bold]2/6 fast mode (prime)[/bold]")
		cal_fast(seconds=fast_seconds, repeats=fast_repeats)
	else:
		print("\n[dim]2/6 fast mode skipped[/dim]")

	## 5 -----------------------------------------------------------------
	if not skip_sweep:
		if not (CAL_SIMULATED and CAL_AUTO_READ):
			print("\n[yellow]Connect the microfluidic device now[/] -- the sweep "
					"must see the real flow resistance.")
			Prompt.ask("  press enter when the chip is inline and the line is full")
		print("\n[bold]3/6 pulse sweep[/bold]")
		cal_sweep(speeds=speeds, cycles=cycles, off_s=off_s, passes=passes)
	else:
		print("\n[dim]3/6 pulse sweep skipped[/dim]")

	## 7 -----------------------------------------------------------------
	if not skip_verify:
		print("\n[bold]4/6 duty verification[/bold]")
		cal_verify(speed=verify_speed, cycles=verify_cycles)
	else:
		print("\n[dim]4/6 duty verification skipped[/dim]")

	## 8 -----------------------------------------------------------------
	print("\n[bold]5/6 fit[/bold]")
	calib = cal_fit_and_store(dry_run=not store)

	## 9 + 10 ------------------------------------------------------------
	print("\n[bold]6/6 close out[/bold]")
	cal_close_levels()
	cal_report()
	cal_check(calib)
	if calib:
		cal_plot(calib)
	print("\n[green]Done.[/] cal_stop() to close the experiment.")
	return calib


## ---------------------------------------------------------------- helpers
def _ready():
	if CAL_PUMP_OBJ is None:
		print("[red]Run cal_setup() first.[/]")
		return False
	if "L1" not in LEVELS:
		print("[red]Run cal_levels() first -- there is no zero to measure against.[/]")
		return False
	return True


def _mean(values):
	values = [v for v in values if v is not None]
	return sum(values) / float(len(values)) if values else 0.0


def _linfit(xs, ys):
	"""Least squares y = m x + c, without numpy."""
	n = len(xs)
	if n < 2:
		return 0.0, (ys[0] if ys else 0.0)
	mx, my = _mean(xs), _mean(ys)
	sxx = sum((x - mx) ** 2 for x in xs)
	sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
	if sxx == 0:
		return 0.0, my
	m = sxy / sxx
	return m, my - m * mx


def _calib_table(calib):
	t = Table(title="calibration")
	t.add_column("key")
	t.add_column("value")
	for key in ("calib_fast_ml_min", "calib_fast_spread_ml_min",
				"calib_prime_s_per_ml", "calib_pulse_slope",
				"calib_pulse_intercept", "calib_stiction_speed",
				"calib_pulse_duty", "calib_area_ratio", "calib_simulated"):
		if key in calib:
			t.add_row(key, str(calib[key]))
	return t


def _check_against_truth(calib):
	"""In simulation the answer is known -- say how close the procedure got."""
	if RIG is None:
		return
	truth = RIG.truth
	print("[bold]simulation self-check[/bold]")
	rows = [("fast ml/min", calib.get("calib_fast_ml_min"), truth["fast_ml_min"]),
			("pulse slope a", calib.get("calib_pulse_slope"), truth["a"]),
			("pulse intercept b", calib.get("calib_pulse_intercept"), truth["b"]),
			("stiction speed", calib.get("calib_stiction_speed"),
				round(-truth["b"] / truth["a"], 4))]
	t = Table()
	for c in ("quantity", "recovered", "true", "error %"):
		t.add_column(c)
	for name, got, want in rows:
		if got is None or not want:
			continue
		err = (got - want) / want * 100.0
		t.add_row(name, str(got), str(want),
					"[green]{:+.1f}[/green]".format(err) if abs(err) < 5
					else "[yellow]{:+.1f}[/yellow]".format(err))
	print(t)


def cal_stop():
	"""Safe-state and close."""
	if not CAL_SIMULATED and CAL_PUMP_OBJ is not None:
		try:
			CAL_PUMP_OBJ.stop()
		except Exception as err:
			log.error("could not stop the pump: %s", err)
	if exp is not None:
		exp.logs.update(ScopeAssembly.current.get_config())
		exp.__save__()
		dest = getattr(exp, "destination_dir", None)
		if dest:
			try:
				exp.sync_dir()
				print("[green]Synced[/] -> {}".format(dest))
			except Exception as err:
				log.error("sync_dir failed: %s", err)
		exp.close()
	print("[green]Calibration closed.[/]")


## End of initalization message
print("Script initalization finished.")

## NOTE: deliberately no auto-run. This script is often loaded straight after
## chambertests/keypad_pump_control.py, and silently constructing a second
## Experiment there would orphan the first one. Call cal_create_exp() yourself.
print("[dim]Nothing started. Call cal_create_exp() when you are ready.[/dim]")
