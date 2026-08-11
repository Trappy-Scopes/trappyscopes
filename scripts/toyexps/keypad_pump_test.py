"""
Keypad-driven pump test with simulated motors.

Reads the Pimoroni RGB keypad mounted as `scope.kp` and applies its commands to
three simulated peristaltic pumps registered as `scope.pump1/2/3`. Nothing
touches real hardware: the pumps are `SimPump` objects that mirror the
`pico_firmware.actuators.dcmotor.DCMotor` API, so swapping to real motors later
is a one-line change in `add_pumps()`.

author: Yatharth Bhasin
date: 08-August-2026
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
import time
import logging as log
from datetime import timedelta
from rich import print
from rich.table import Table
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly

## Describe the script. This is important and will be logged in the Experiment system.
__description__ = \
"""
Test the Pimoroni RGB keypad as a pump input source.

Polls `scope.kp.lines()` over the MicroPython raw REPL, parses the wire protocol
(PUMP <n> POWER|PULSE|SPEED|LIMIT <value>) and applies each command to a
simulated pump. Every command is timestamped into an Experiment measurement
stream so the whole session can be replayed.

    POWER  fast mode  -- full speed on/off
    PULSE  slow mode  -- continuous run at the stored speed
    SPEED  0-100 %    -- adjusts both modes
    POWER overrides PULSE while it is on.

Pumps are simulated (`SimPump`). To go live, swap the constructor in
`add_pumps()` for the Pico motor proxy -- the verb set is identical.
"""

### Quick explainer
print("[bold]keypad pump test[/bold] -- simulated motors")
print("  create_exp()   make the experiment context")
print("  add_pumps()    bind to the pumps (auto: real if mounted, else simulated)")
print("  which()        what PUMPSET is actually driving")
print("  start()        poll the keypad with a live view; Ctrl-C stops it")
print("  start(scheduled=True)  run in exp.schedule instead; prompt stays free")
print("  animate()      watch the pumps live")
print("  status()       one-shot table of pump state")
print("  stop_jobs()    end polling, keep the experiment open")
print("  stop()         safe-state everything and close the experiment")
print("  panic()        everything off now (Ctrl-C does not stop scheduled jobs)")


## ---------------------------------------------------------------- simulated pump
## SimPump mirrors pico_firmware.actuators.peristaltic.PeristalticPump method for
## method, and SimPumpSet mirrors PumpSet. Nothing in this script calls anything
## outside that shared surface, so `add_pumps(simulated=False)` swaps in the real
## firmware pumps with no other change. `check_api()` proves the surfaces match.
##
## Differences that are simulation-only, and additive:
##   flow_ml_min()  volume_ml()  runtime_s()   -- integrated delivery
## The firmware pumps do not have these; the live view degrades gracefully.

class SimPump():
	"""Simulated peristaltic pump with the PeristalticPump API.

	Fast mode overrides pulse mode. Pulse mode either duty-cycles (5 s on /
	55 s off by default) or, when continuous, runs steadily -- matching the
	DFR0523 channel on the real board.
	"""

	def __init__(self, name="pump", ml_per_min=45.0,
					fast_speed=0.5,
					slow_min=0.03, slow_max=0.2,
					pulse_on_s=5, pulse_off_s=55,
					continuous=False, slow_speed=None):
		self.name = name
		self.devicetype = "sim.pump"
		self.description = "Simulated peristaltic pump"
		self.ml_per_min = ml_per_min

		self.fast_speed_ = fast_speed
		self.slow_min_ = slow_min
		self.slow_max_ = slow_max
		self.pulse_on_s_ = pulse_on_s
		self.pulse_off_s_ = pulse_off_s
		self.continuous_ = continuous

		self.fast_ = False
		self.pulse_ = False
		self.level_ = 0.5
		self.phase_ = "idle"
		self.cycles_ = 0
		self.dir = +1

		self._phase_t0 = time.time()
		self._t_last = time.time()
		self._volume_ml = 0.0
		self._runtime_s = 0.0

		if slow_speed is not None:
			self.set_slow_speed(slow_speed)

	## -- tunables ---------------------------------------------------------------
	def set_fast_speed(self, speed):
		self.fast_speed_ = min(1.0, max(0.0, float(speed)))
		return self.fast_speed_

	def fast_speed(self):
		return self.fast_speed_

	def set_slow_limits(self, low, high):
		low = min(1.0, max(0.0, float(low)))
		high = min(1.0, max(0.0, float(high)))
		if high < low:
			low, high = high, low
		self.slow_min_, self.slow_max_ = low, high
		return (self.slow_min_, self.slow_max_)

	def slow_limits(self):
		return (self.slow_min_, self.slow_max_)

	def set_pwm_freq(self, hz):
		"""No-op in simulation; present so the API matches."""
		return int(hz)

	def set_pulse_duty(self, on_s, off_s):
		self.pulse_on_s_ = max(0, int(on_s))
		self.pulse_off_s_ = max(0, int(off_s))
		self._phase_t0 = time.time()
		return (self.pulse_on_s_, self.pulse_off_s_)

	def pulse_duty(self):
		return (self.pulse_on_s_, self.pulse_off_s_)

	def set_continuous(self, flag):
		self.continuous_ = bool(flag)
		if self.continuous_ and self.pulse_:
			self.phase_ = "on"
			self._phase_t0 = time.time()
		return self.continuous_

	def is_continuous(self):
		return self.continuous_

	## -- speed within the slow band ---------------------------------------------
	def set_level(self, level):
		self._integrate()
		self.level_ = min(1.0, max(0.0, float(level)))
		return self.level_

	def set_percent(self, pct):
		return self.set_level(float(pct) / 100.0)

	def level(self):
		return self.level_

	def percent(self):
		return int(round(self.level_ * 100))

	def slow_speed(self):
		return self.slow_min_ + (self.slow_max_ - self.slow_min_) * self.level_

	def set_slow_speed(self, unit_speed):
		span = self.slow_max_ - self.slow_min_
		if span <= 0:
			return self.set_level(0.0)
		return self.set_level((float(unit_speed) - self.slow_min_) / span)

	def speed_up(self, step=0.05):
		return self.set_level(self.level_ + step)

	def speed_down(self, step=0.05):
		return self.set_level(self.level_ - step)

	## -- modes -------------------------------------------------------------------
	def fast_on(self):
		self._integrate()
		self.fast_ = True
		return True

	def fast_off(self):
		self._integrate()
		self.fast_ = False
		return False

	def set_fast(self, on):
		return self.fast_on() if on else self.fast_off()

	def toggle_fast(self):
		return self.set_fast(not self.fast_)

	def is_fast(self):
		return self.fast_

	def pulse_on(self):
		self._integrate()
		self.pulse_ = True
		self.phase_ = "on"
		self._phase_t0 = time.time()
		return True

	def pulse_off(self):
		self._integrate()
		self.pulse_ = False
		self.phase_ = "idle"
		return False

	def set_pulse(self, on):
		return self.pulse_on() if on else self.pulse_off()

	def toggle_pulse(self):
		return self.set_pulse(not self.pulse_)

	def is_pulse(self):
		return self.pulse_

	def stop(self):
		self._integrate()
		self.fast_ = False
		self.pulse_ = False
		self.phase_ = "idle"

	def prime(self, seconds=5, speed=None):
		"""Blocking prime, as on the firmware."""
		was = (self.fast_, self.pulse_)
		self.stop()
		self._forced = 1.0 if speed is None else float(speed)
		time.sleep(seconds)
		self._forced = None
		self.fast_, self.pulse_ = was

	## -- state ---------------------------------------------------------------------
	def mode(self):
		if self.fast_:
			return "fast"
		if self.pulse_:
			return "slow" if self.continuous_ else "pulse"
		return "idle"

	def speed(self):
		self._advance()
		if self.fast_:
			return self.fast_speed_
		if self.pulse_ and (self.continuous_ or self.phase_ == "on"):
			return self.slow_speed()
		return 0.0

	def running(self):
		return self.speed() > 0.0

	def seconds_left(self):
		self._advance()
		if not self.pulse_ or self.continuous_ or self.fast_:
			return 0
		total = self.pulse_on_s_ if self.phase_ == "on" else self.pulse_off_s_
		return max(0, int(total - (time.time() - self._phase_t0)))

	def state(self):
		"""Same keys as PeristalticPump.state(), plus the simulation extras."""
		return {"name": self.name,
				"mode": self.mode(),
				"fast": self.fast_,
				"pulse": self.pulse_,
				"phase": self.phase_,
				"level": round(self.level_, 3),
				"percent": self.percent(),
				"speed": round(self.speed(), 4),
				"fast_speed": self.fast_speed_,
				"slow_limits": (self.slow_min_, self.slow_max_),
				"pulse_duty": (self.pulse_on_s_, self.pulse_off_s_),
				"continuous": self.continuous_,
				"cycles": self.cycles_,
				"dir": self.dir,
				## simulation-only
				"flow_ml_min": round(self.flow_ml_min(), 2),
				"volume_ml": round(self.volume_ml(), 3),
				"runtime_s": round(self.runtime_s(), 1)}

	def deinit(self):
		self.stop()

	def close(self):
		"""ScopeAssembly calls close() on every device at exit."""
		self.stop()

	def __getstate__(self):
		return self.state()

	## -- simulation bookkeeping -----------------------------------------------------
	def _advance(self):
		"""Move the pulse phase along using wall clock -- no Timer on the host."""
		if not self.pulse_ or self.continuous_ or self.fast_:
			return
		now = time.time()
		while True:
			total = self.pulse_on_s_ if self.phase_ == "on" else self.pulse_off_s_
			if total <= 0 or (now - self._phase_t0) < total:
				break
			self._phase_t0 += total
			if self.phase_ == "on":
				self.phase_ = "off"
				self.cycles_ += 1
			else:
				self.phase_ = "on"

	def _integrate(self):
		"""Accumulate delivered volume for the interval just ended."""
		now = time.time()
		dt = now - self._t_last
		self._t_last = now
		s = self.speed()
		if s > 0.0:
			self._runtime_s += dt
			self._volume_ml += self.ml_per_min * s * dt / 60.0

	def flow_ml_min(self):
		return self.ml_per_min * self.speed()

	def volume_ml(self):
		self._integrate()
		return self._volume_ml

	def runtime_s(self):
		self._integrate()
		return self._runtime_s

	def __repr__(self):
		return "<SimPump {} {} {:.0f}%>".format(
			self.name, self.mode(), self.speed() * 100)


class SimPumpSet():
	"""Mirrors pico_firmware.actuators.peristaltic.PumpSet."""

	def __init__(self, pumps):
		self.pumps = pumps

	def __getitem__(self, n):
		return self.pumps[n]

	def get(self, n):
		return self.pumps.get(n)

	def numbers(self):
		return sorted(self.pumps)

	def command(self, line):
		"""Apply one keypad wire line. Identical semantics to the firmware."""
		parts = str(line).strip().upper().split()
		if len(parts) != 4 or parts[0] != "PUMP":
			return None
		try:
			n = int(parts[1])
		except ValueError:
			return None
		pump = self.pumps.get(n)
		if pump is None:
			return None

		verb, arg = parts[2], parts[3]
		if verb == "POWER":
			pump.set_fast(arg == "ON")
		elif verb == "PULSE":
			pump.set_pulse(arg == "ON")
		elif verb == "SPEED":
			try:
				pump.set_percent(int(arg))
			except ValueError:
				return None
		elif verb == "LIMIT":
			return pump.state()
		else:
			return None
		return pump.state()

	def commands(self, lines):
		return [self.command(line) for line in (lines or [])]

	def stop_all(self):
		for pump in self.pumps.values():
			pump.stop()

	def set_fast_speed(self, speed):
		return [p.set_fast_speed(speed) for p in self.pumps.values()]

	def set_slow_limits(self, low, high):
		return [p.set_slow_limits(low, high) for p in self.pumps.values()]

	def set_pulse_duty(self, on_s, off_s):
		return [p.set_pulse_duty(on_s, off_s) for p in self.pumps.values()]

	def set_continuous(self, flag):
		return [p.set_continuous(flag) for p in self.pumps.values()]

	def state(self):
		return dict((n, p.state()) for n, p in self.pumps.items())

	def deinit(self):
		for pump in self.pumps.values():
			pump.deinit()


class RemotePumpSet():
	"""PumpSet-shaped facade over the firmware's own pumpset, via the proxy.

	Lets add_pumps(simulated=False) hand the rest of this script something that
	behaves exactly like SimPumpSet while the commands actually execute on the
	Pico. One serial round trip per command line.
	"""

	def __init__(self, numbers=(1, 2, 3)):
		self._numbers = list(numbers)

	def _remote(self):
		return ScopeAssembly.current.pumpset

	def __getitem__(self, n):
		return getattr(ScopeAssembly.current, "pump{}".format(n))

	def get(self, n):
		return self[n] if n in self._numbers else None

	def numbers(self):
		return sorted(self._numbers)

	def command(self, line):
		return self._remote().command(str(line))

	def commands(self, lines):
		return [self.command(ln) for ln in (lines or [])]

	def stop_all(self):
		return self._remote().stop_all()

	def set_fast_speed(self, speed):
		return self._remote().set_fast_speed(speed)

	def set_slow_limits(self, low, high):
		return self._remote().set_slow_limits(low, high)

	def set_pulse_duty(self, on_s, off_s):
		return self._remote().set_pulse_duty(on_s, off_s)

	def set_continuous(self, flag):
		return self._remote().set_continuous(flag)

	def state(self):
		return self._remote().state()

	def deinit(self):
		return self._remote().stop_all()


## ---------------------------------------------------------------- keypad access
## The keypad is reached as `ScopeAssembly.current.kp` -- always resolved fresh,
## never cached, so a reconnect or a re-`add_device()` is picked up without
## restarting the script.
##
## What comes back depends on the transport. Over the MicroPython proxy the call
## is sent as a printed expression and the repr is parsed, so `lines()` (a list
## of plain strings) survives but `drain()` (a list of Command objects) does not
## -- it arrives as unparseable "<PUMP 1 POWER ON #5>" text. `_read_keypad()`
## probes once for the best method available and remembers the choice.

def parse_line(line):
	"""'PUMP 2 SPEED 45' -> (2, 'SPEED', 45). None if it is not a command.

	Only used for logging and snapshot diffing -- the pumps themselves are
	driven through PUMPSET.command(), which does its own parsing.
	"""
	parts = str(line).strip().upper().split()
	if len(parts) != 4 or parts[0] != "PUMP":
		return None
	try:
		n = int(parts[1])
	except ValueError:
		return None
	verb, arg = parts[2], parts[3]
	if verb in ("POWER", "PULSE"):
		return (n, verb, arg == "ON")
	if verb == "SPEED":
		try:
			return (n, verb, int(arg))
		except ValueError:
			return None
	if verb == "LIMIT":
		return (n, verb, arg)
	return None


_READ_METHOD = None       ## "lines" | "drain_repr" | "poll_state"

## repr of a Command, e.g. "<PUMP 1 SPEED 45 #7>"
_CMD_REPR = None


def kp():
	"""The keypad device. Raises AttributeError if it is not mounted."""
	return ScopeAssembly.current.kp


def _reprs_to_lines(blob):
	"""Salvage wire lines out of any mangled blob.

	Handles a repr'd list of Command objects ("[<PUMP 1 SPEED 45 #7>, ...]") and
	a repr'd list of strings ("['PUMP 1 SPEED 45', ...]") equally -- both lose
	their structure crossing the raw REPL, but the payload is still in there.
	"""
	global _CMD_REPR
	import re
	if _CMD_REPR is None:
		_CMD_REPR = re.compile(r"PUMP\s+(\d+)\s+([A-Z]+)\s+([A-Za-z0-9]+)")
	return ["PUMP {} {} {}".format(*m.groups()) for m in _CMD_REPR.finditer(str(blob))]


def _read_keypad():
	"""Return a list of wire lines pending on the keypad. Never raises."""
	global _READ_METHOD
	device = kp()

	if _READ_METHOD is None:
		## Probe, cheapest and most reliable first.
		for name in ("lines", "drain", "snapshot_lines"):
			if hasattr(device, name):
				_READ_METHOD = {"lines": "lines",
								"drain": "drain_repr",
								"snapshot_lines": "poll_state"}[name]
				break
		else:
			## A bare proxy exposes nothing to hasattr -- assume lines().
			_READ_METHOD = "lines"
		log.info("keypad read method: %s", _READ_METHOD)

	try:
		if _READ_METHOD == "lines":
			out = device.lines()
			if out is None:
				return []
			if isinstance(out, str):
				## Proxy returned one repr'd blob rather than a real list.
				return _reprs_to_lines(out)
			return [str(ln) for ln in out]

		if _READ_METHOD == "drain_repr":
			return _reprs_to_lines(device.drain())

		## Last resort: diff the full snapshot each poll.
		return _snapshot_diff(device)

	except AttributeError:
		## Method missing on this build -- fall back one rung and retry next poll.
		_READ_METHOD = "drain_repr" if _READ_METHOD == "lines" else "poll_state"
		log.error("keypad read method fell back to %s", _READ_METHOD)
		return []


_LAST_SNAPSHOT = {}


def _snapshot_diff(device):
	"""Poll full state and synthesise command lines for whatever changed."""
	lines = []
	for line in (device.snapshot_lines() or []):
		parsed = parse_line(line)
		if parsed is None:
			continue
		n, verb, value = parsed
		key = (n, verb)
		if _LAST_SNAPSHOT.get(key) != value:
			_LAST_SNAPSHOT[key] = value
			lines.append(str(line))
	return lines


def set_read_method(method):
	"""Force the read strategy: 'lines', 'drain_repr' or 'poll_state'."""
	global _READ_METHOD
	_READ_METHOD = method
	print("[green]Keypad read method set to[/] {}".format(method))


## ---------------------------------------------------------------- setup
## PUMPSET is whatever the rest of this script talks to: SimPumpSet on the host,
## or RemotePumpSet if the pumps live on the Pico. Both expose PumpSet's API, so
## nothing below this line knows or cares which it is.
PUMPSET = None
SIMULATED = True

## Defaults mirrored from circuits/2ch_peristat_kitroniks_vx_shield.py
FAST_SPEED  = 0.5
SLOW_MIN    = 0.03      ## pump1, pump2 -- kitronik channels
SLOW_MAX    = 0.2
PULSE_ON_S  = 5
PULSE_OFF_S = 55
P3_SLOW_MIN = 0.05      ## pump3 -- DFR0523, continuous
P3_SLOW_MAX = 0.3
P3_SLOW_START = 0.1

## Roles: pumps 1 and 2 perfuse media through the microfluidic devices and are
## calibrated in mL; pump 3 aerates and is never measured volumetrically, so the
## displays show "aeration" rather than a meaningless millilitre figure.
PUMP_ROLES = {1: "perfusion", 2: "perfusion", 3: "aeration"}
CALIBRATED = (1, 2)          ## pumps whose params shelve holds a calibration


def role(n):
	return PUMP_ROLES.get(n, "perfusion")


def is_aeration(n):
	return role(n) == "aeration"




def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["keypad", "pump", "test"],
								user=True, eid=True, date=True, time=True, scopeid=True)
	exp.new_measurementstream("keypress",
								measurements=["pump", "verb", "value", "applied_speed"])
	exp.attribs["pumps"] = [1, 2, 3]
	exp.attribs["fast_speed"] = FAST_SPEED
	exp.attribs["slow_limits"] = (SLOW_MIN, SLOW_MAX)
	exp.attribs["pulse_duty"] = (PULSE_ON_S, PULSE_OFF_S)
	exp.attribs["pump3_slow_limits"] = (P3_SLOW_MIN, P3_SLOW_MAX)
	exp.attribs["ml_per_min"] = 45.0
	exp.attribs["poll_period_s"] = 0.05
	exp.attribs["autosync_dir"] = True    ## sync on stop() if a destination exists
	print("[green]Experiment ready.[/] Now run add_pumps().")


def add_pumps(simulated=None, names=("pump1", "pump2", "pump3")):
	"""Point PUMPSET at the pumps, real or simulated.

	simulated=None (default) auto-detects: real pumps if scope.pumpset is
	mounted, simulated otherwise.

	Simulated pumps are NEVER registered while real ones are present -- a
	shadow copy of a live device is how you end up watching an animation while
	the real pumps sit idle, or worse, thinking you are in simulation when you
	are not. If you ask for simulation on a rig with real pumps, this refuses
	and tells you why.

	Which backend is in use is recorded in exp.attribs and noted in the event
	log, so the experiment record says whether fluid actually moved.
	"""
	global scope, exp, PUMPSET, SIMULATED
	scope = ScopeAssembly.current
	remote_present = getattr(scope, "pumpset", None) is not None

	if simulated is None:
		simulated = not remote_present
		print("[dim]auto: {} ({}).[/dim]".format(
				"real pumps" if not simulated else "simulated pumps",
				"scope.pumpset found" if remote_present else "no scope.pumpset"))

	if simulated and remote_present:
		print("[yellow]Real pumps are mounted -- not adding simulated ones.[/]")
		print("  [dim]Simulating alongside live hardware would shadow it. "
				"Use add_pumps(simulated=False), or unmount the pump Pico "
				"first.[/dim]")
		return None

	if not simulated:
		if not remote_present:
			print("[red]scope.pumpset not found -- is the pump Pico mounted?[/]")
			return None
		SIMULATED = False
		PUMPSET = RemotePumpSet(numbers=(1, 2, 3))
		print("[green]Using REAL pumps[/] via scope.pumpset -> {}".format(
				PUMPSET.numbers()))
		_record_backend()
		which()
		return PUMPSET

	## -- simulated, and no real pumps in the way ---------------------------
	SIMULATED = True
	rate = exp.attribs["ml_per_min"] if exp is not None else 45.0
	pumps = {}
	for i, name in enumerate(names):
		n = i + 1
		if n == 3:
			## pump3 is the DFR0523 channel: continuous, wider band, starts at 0.1
			pump = SimPump(name, ml_per_min=rate, fast_speed=FAST_SPEED,
							slow_min=P3_SLOW_MIN, slow_max=P3_SLOW_MAX,
							continuous=True, slow_speed=P3_SLOW_START)
		else:
			pump = SimPump(name, ml_per_min=rate, fast_speed=FAST_SPEED,
							slow_min=SLOW_MIN, slow_max=SLOW_MAX,
							pulse_on_s=PULSE_ON_S, pulse_off_s=PULSE_OFF_S)
		if getattr(scope, name, None) is None:
			scope.add_device(name, pump,
								description="Simulated peristaltic pump {}".format(n))
		pumps[n] = pump

	PUMPSET = SimPumpSet(pumps)
	if getattr(scope, "pumpset", None) is None:
		scope.add_device("pumpset", PUMPSET, description="Simulated pump set")

	print(scope.draw_tree())
	print("[green]Simulated pumps ready:[/] {}".format(PUMPSET.numbers()))
	print("  pump1/2 slow {}-{} duty {}s/{}s | pump3 slow {}-{} continuous @ {}".format(
			SLOW_MIN, SLOW_MAX, PULSE_ON_S, PULSE_OFF_S,
			P3_SLOW_MIN, P3_SLOW_MAX, P3_SLOW_START))
	_record_backend()
	which()
	return PUMPSET


def _record_backend():
	"""Put the real-vs-simulated fact into the experiment record.

	attribs is the machine-readable half (it lands in the experiment yaml);
	note() is the human-readable half and timestamps it in the event log. Not
	exp.write() -- that opens an interactive prompt.
	"""
	if exp is None:
		return None
	backend = type(PUMPSET).__name__ if PUMPSET is not None else None
	exp.attribs["simulated"] = bool(SIMULATED)
	exp.attribs["pump_backend"] = backend
	exp.attribs["pumps"] = PUMPSET.numbers() if PUMPSET is not None else []
	exp.attribs["fluid_moved"] = not SIMULATED
	try:
		exp.note("Pumps: {} via {} -- {}".format(
			"SIMULATED (no fluid moved)" if SIMULATED else "REAL hardware",
			backend,
			"scope.pumpset on the pump Pico" if not SIMULATED
			else "host-side SimPump objects"))
	except Exception as err:
		log.error("could not note the pump backend: %s", err)
	return backend


def which():
	"""Say plainly what PUMPSET is bound to, and what is on the scope tree.

	Worth calling any time you are unsure whether you are about to move fluid.
	Deliberately avoids touching attributes on a remote pump: `proxy.name` would
	fire a serial round trip and return the Pico's idea of the name.
	"""
	scope_ = ScopeAssembly.current
	if PUMPSET is None:
		print("[red]PUMPSET is not bound -- run add_pumps().[/]")
		return None

	kind = type(PUMPSET).__name__
	if SIMULATED:
		print("PUMPSET -> {} ([dim]simulated -- no fluid will move[/dim])".format(kind))
	else:
		print("PUMPSET -> {} ([yellow]REAL PUMPS[/])".format(kind))

	for n in PUMPSET.numbers():
		try:
			obj = PUMPSET[n]
		except Exception as err:
			print("  {} -> [red]unreachable ({})[/red]".format(n, err))
			continue
		if SIMULATED:
			name = getattr(obj, "name", "pump{}".format(n))
			on_tree = getattr(scope_, str(name), None)
			if on_tree is obj:
				note = "[green]same object as scope.{}[/green]".format(name)
			elif on_tree is not None:
				note = "[red]NOT the scope.{} object -- you would be watching a " \
						"simulation while the real pump idles[/red]".format(name)
			else:
				note = "[dim]local only, not on the tree[/dim]"
			print("  {} -> {} {}".format(n, name, note))
		else:
			name = "pump{}".format(n)
			on_tree = getattr(scope_, name, None)
			note = "[green]scope.{} (remote proxy)[/green]".format(name) \
					if on_tree is obj else "[red]does not match scope.{}[/red]".format(name)
			print("  {} -> {}".format(n, note))
	return kind


def sync_from_keypad():
	"""Adopt the keypad's own view of the world. Use after a reconnect."""
	if PUMPSET is None:
		print("[red]Run add_pumps() first.[/]")
		return
	try:
		lines = kp().snapshot_lines()
	except Exception as err:
		log.error("keypad snapshot unavailable (%s) -- keeping local state", err)
		return
	for line in (lines or []):
		PUMPSET.command(line)
		parsed = parse_line(line)
		if parsed:
			_LAST_SNAPSHOT[(parsed[0], parsed[1])] = parsed[2]
	print("[green]Synced[/] from keypad snapshot.")
	status()


## ---------------------------------------------------------------- push back
## Changes made through the API rather than the keys -- pump1.set_fast_speed(),
## a scripted dose, stop_all() -- are invisible to the keypad unless we tell it.
## push_to_keypad() mirrors pump state onto the LEDs using the keypad's quiet
## sync path, so nothing bounces back as a fresh command.

MIRROR = True          ## keep the keypad LEDs in step during start()
MIRROR_PERIOD_S = 0.5  ## how often start() pushes pump state to the keypad


def push_to_keypad(states=None):
	"""Reflect pump state onto the keypad LEDs. Returns the pumps touched."""
	if PUMPSET is None:
		return []
	if states is None:
		states = PUMPSET.state() or {}
	try:
		return kp().sync(states)
	except AttributeError:
		## Older keypad firmware without sync(): fall back to wire lines.
		lines = []
		for n, st in states.items():
			if not st:
				continue
			lines.append("PUMP {} POWER {}".format(
					n, "ON" if st.get("fast") else "OFF"))
			lines.append("PUMP {} PULSE {}".format(
					n, "ON" if st.get("pulse") else "OFF"))
			lines.append("PUMP {} SPEED {}".format(n, int(st.get("percent", 0))))
		try:
			kp().apply_lines(lines)
			return sorted(states)
		except AttributeError:
			log.error("keypad has no sync()/apply_lines() -- cannot mirror state")
			return []
	except Exception as err:
		log.error("keypad mirror failed: %s", err)
		return []


def set_fast_speed(speed, mirror=True):
	"""Retune fast speed on every pump, then update the keypad."""
	out = PUMPSET.set_fast_speed(speed)
	if mirror:
		push_to_keypad()
	return out


def set_slow_limits(low, high, mirror=True):
	out = PUMPSET.set_slow_limits(low, high)
	if mirror:
		push_to_keypad()
	return out


def set_pulse_duty(on_s, off_s, mirror=True):
	return PUMPSET.set_pulse_duty(on_s, off_s)


def stop_all(mirror=True):
	"""Stop every pump AND clear the keypad, so the LEDs do not lie."""
	out = PUMPSET.stop_all()
	if mirror:
		push_to_keypad()
	return out


## ---------------------------------------------------------------- swap check
## The point of this script is that the simulated pumps and the firmware pumps
## are interchangeable. check_api() proves it rather than assuming it: it diffs
## SimPump against PeristalticPump and SimPumpSet against PumpSet, reading the
## firmware source straight out of the pico_firmware checkout.

FIRMWARE_PERISTALTIC = "pico_firmware/pico_firmware/actuators/peristaltic.py"


def check_api(path=None, verbose=True):
	"""Compare the simulated API against the firmware's, method by method.

	Pass the path to pico_firmware/actuators/peristaltic.py, or set
	FIRMWARE_PERISTALTIC. Returns True when the simulation covers everything the
	firmware exposes.
	"""
	import ast
	import os

	path = path or FIRMWARE_PERISTALTIC
	if not os.path.exists(path):
		print("[yellow]Firmware source not found at[/] {}".format(path))
		print("  pass check_api('/path/to/actuators/peristaltic.py')")
		return None

	with open(path) as f:
		tree = ast.parse(f.read())

	firmware = {}
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			firmware[node.name] = set(
				n.name for n in node.body
				if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))

	pairs = [("PeristalticPump", SimPump), ("PumpSet", SimPumpSet),
				("PumpSet", RemotePumpSet)]
	ok = True
	for fw_name, sim_cls in pairs:
		want = firmware.get(fw_name, set())
		have = set(m for m in dir(sim_cls) if not m.startswith("_"))
		missing = sorted(want - have)
		extra = sorted(have - want)
		if missing:
			ok = False
		if verbose:
			mark = "[green]ok[/]" if not missing else "[red]MISSING[/]"
			print("{} {:<14} vs {:<14} {} firmware methods".format(
					mark, sim_cls.__name__, fw_name, len(want)))
			if missing:
				print("   [red]missing:[/] {}".format(", ".join(missing)))
			if extra:
				print("   [dim]extra (simulation-only): {}[/dim]".format(
						", ".join(extra)))
	if verbose:
		print("[bold]{}[/bold]".format(
			"Simulated and real pumps are swappable." if ok
			else "Simulation does NOT cover the firmware API."))
	return ok


## ---------------------------------------------------------------- persistence
## Calibrations live on the DEVICE, not the experiment: proxy.params is a
## PhysicalObject backed by a shelve at ~/<name>.db, so a calibration follows the
## hardware across sessions. ScopeAssembly.get_config() serialises it via
## Proxy.__getstate__, and stop() writes that into exp.logs -- so every run
## carries the calibration that was live when it happened.

def persist(numbers=CALIBRATED, force=False):
	"""Make the pump proxies persistent so calibrations survive the session.

	Only the perfusion pumps: the aeration pump has no volumetric calibration to
	keep. A proxy only attaches its shelve at construction if ~/<name>.db already
	exists, so this must be called once per machine to create it.
	"""
	scope_ = ScopeAssembly.current
	out = {}
	for n in numbers:
		name = "pump{}".format(n)
		proxy = getattr(scope_, name, None)
		if proxy is None:
			print("[red]scope.{} not found.[/]".format(name))
			continue
		if getattr(proxy, "params", None) is not None and not force:
			print("[dim]{} already persistent ({} keys).[/dim]".format(
					name, len(proxy.params.__getstate__())))
			out[n] = proxy.params
			continue
		try:
			proxy.make_persist()
			proxy.params["role"] = role(n)
			proxy.params["kind"] = "peristaltic.PeristalticPump"
			print("[green]{} now persistent[/] -> ~/{}.db".format(name, name))
			out[n] = proxy.params
		except Exception as err:
			log.error("could not persist %s: %s", name, err)
	return out


def calibration(n=None):
	"""Read back the stored calibration for a pump, or for all of them."""
	scope_ = ScopeAssembly.current
	if n is None:
		return dict((i, calibration(i)) for i in CALIBRATED)
	proxy = getattr(scope_, "pump{}".format(n), None)
	params = getattr(proxy, "params", None)
	if params is None:
		return None
	return dict((k, v) for k, v in params.__getstate__().items()
				if k.startswith("calib") or k in ("role", "kind", "created"))


def show_calibration():
	"""Table of what each perfusion pump currently believes about itself."""
	table = Table(title="stored calibrations (~/pumpN.db)")
	for col in ("pump", "role", "fast ml/min", "pulse ml/cycle", "duty", "when"):
		table.add_column(col)
	for n in CALIBRATED:
		c = calibration(n) or {}
		table.add_row(
			"pump{}".format(n),
			str(c.get("role", role(n))),
			str(c.get("calib_fast_ml_min", "[dim]-[/dim]")),
			str(c.get("calib_pulse_ml_per_cycle", "[dim]-[/dim]")),
			str(c.get("calib_pulse_duty", "[dim]-[/dim]")),
			str(c.get("calib_dt", "[dim]never[/dim]")),
		)
	print(table)


## ---------------------------------------------------------------- live view
ROTOR    = "|/-\\"
TUBE_W   = 22
SLUG     = "█"
TUBE_BG  = "·"
SLUG_GAP = 5


def _flow_style(frac):
	if frac <= 0.0:
		return "grey35"
	if frac < 0.34:
		return "blue"
	if frac < 0.67:
		return "cyan"
	if frac < 0.9:
		return "bright_cyan"
	return "bright_yellow"


def _tube(frac, direction, phase):
	from rich.text import Text
	if frac <= 0.0:
		return Text(TUBE_BG * TUBE_W, style="grey30")
	offset = int(phase) % SLUG_GAP
	cells = []
	for i in range(TUBE_W):
		pos = (i - offset) if direction > 0 else (i + offset)
		cells.append(SLUG if pos % SLUG_GAP == 0 else TUBE_BG)
	return Text("".join(cells), style=_flow_style(frac))


def _bar(speed, full_scale, slow_min, slow_max, width=16):
	"""Absolute speed bar.

	The scale is the pump's own usable maximum (its fast speed or the top of its
	slow band, whichever is higher), so a pump that only ever runs at 0.03-0.2 is
	still readable instead of being a sliver of a 0-1 bar. The slow band is drawn
	as a dotted region behind the bar, so you can see where the current speed sits
	relative to the limits.
	"""
	from rich.text import Text
	if full_scale <= 0:
		full_scale = 1.0
	t = Text()
	style = _flow_style(speed / full_scale)
	for i in range(width):
		pos = (i + 0.5) / width * full_scale
		if pos <= speed:
			t.append("━", style=style)
		elif slow_min <= pos <= slow_max:
			t.append("┄", style="grey42")      ## the adjustable band
		else:
			t.append("━", style="grey27")
	return t


def _frame(t0):
	"""One frame of the live view, built from state() dicts only.

	Uses nothing beyond PumpSet.state(), so it renders identically for simulated
	and real pumps -- the simulation-only volume column just shows a dash.
	"""
	from rich.table import Table as _T
	from rich.text import Text
	from rich.console import Group
	from rich.panel import Panel

	elapsed = time.time() - t0
	states = {}
	if PUMPSET is not None:
		try:
			raw = PUMPSET.state()
			states = raw if isinstance(raw, dict) else {}
		except Exception as err:
			log.error("pumpset.state() failed: %s", err)

	grid = _T.grid(padding=(0, 1))
	for _ in range(9):
		grid.add_column()

	## header row, so the bare numbers are self-describing
	_h = lambda s_: Text(s_, style="grey50")
	grid.add_row(_h("pump"), _h(""), _h("mode"), _h("speed bar"), _h("speed"),
					_h("band"), _h("fast"), _h("flow"), _h("volume"))

	total_ml = 0.0
	has_volume = False
	for n in sorted(states):
		st = states[n] or {}
		frac = float(st.get("speed", 0.0))
		mode = st.get("mode", "idle")
		direction = st.get("dir", 1)

		if frac > 0:
			rotor = Text(ROTOR[int(elapsed * frac * 24) % len(ROTOR)],
							style=_flow_style(frac))
		else:
			rotor = Text("o", style="grey30")

		if mode == "fast":
			mode_txt = Text("FAST", style="bold green")
		elif mode == "slow":
			mode_txt = Text("slow", style="bright_cyan")     ## continuous
		elif mode == "pulse":
			left = st.get("seconds_left")
			label = "pulse {}".format(st.get("phase", ""))
			mode_txt = Text(label, style="cyan")
		else:
			mode_txt = Text("idle", style="grey30")

		if is_aeration(n):
			## No volumetric meaning for the aeration line -- say so instead of
			## printing a millilitre figure nobody should trust.
			vol = Text("  aeration ", style="grey50")
		elif "volume_ml" in st:
			has_volume = True
			total_ml += float(st["volume_ml"])
			vol = Text("{:>7.2f} ml".format(st["volume_ml"]),
						style="white" if frac else "grey50")
		else:
			vol = Text("      -   ", style="grey30")

		## Everything below is an absolute PWM unit speed (0.0 - 1.0), not a
		## percentage of the band -- percentages hid how slow "slow" really is.
		lo, hi = st.get("slow_limits", (0.0, 1.0))
		fast_speed = st.get("fast_speed", 1.0)
		full_scale = max(fast_speed, hi) or 1.0

		grid.add_row(
			Text(str(st.get("name", n)), style="bold" if frac > 0 else "grey50"),
			rotor,
			mode_txt,
			_bar(frac, full_scale, lo, hi),
			Text("{:>5.3f}".format(frac),
					style=_flow_style(frac / full_scale) if frac else "grey30"),
			Text("{:.2f}-{:.2f}".format(lo, hi), style="grey42"),
			Text("f{:.2f}".format(fast_speed), style="grey42"),
			_tube(frac, direction, elapsed * frac * 34),
			vol,
		)

	footer = Text.assemble(
		("elapsed ", "grey50"), ("{:>6.1f}s".format(elapsed), "white"),
		("   total ", "grey50"),
		("{:.2f} ml".format(total_ml) if has_volume else "n/a", "bright_white"),
		("   ", "grey50"),
		("simulated" if SIMULATED else "REAL PUMPS",
			"grey50" if SIMULATED else "bold yellow"),
		("   ctrl-c to stop", "grey50"))
	return Panel(Group(grid, Text(""), footer),
					title="[bold]pumps[/bold] -- live (absolute PWM unit speed)",
					border_style="grey37")


def animate(fps=12, duration_s=None):
	"""Watch the pumps without touching the keypad. Ctrl-C to exit."""
	from rich.live import Live
	if PUMPSET is None:
		print("[red]Run add_pumps() first.[/]")
		return
	t0 = time.time()
	try:
		with Live(_frame(t0), refresh_per_second=fps) as live:
			while True:
				time.sleep(1.0 / fps)
				live.update(_frame(t0))
				if duration_s is not None and time.time() - t0 > duration_s:
					break
	except KeyboardInterrupt:
		print("[yellow]Animation stopped.[/] "
				"(the display only -- polling and pumps keep running)")
		if is_running():
			print("  [dim]stop_jobs() to end polling, panic() to stop everything.[/dim]")


## ---------------------------------------------------------------- main loop
## ---------------------------------------------------------------- polling
## The experiment owns the cadence. exp.schedule (ExpScheduler) already runs its
## own thread calling run_pending() every 0.01 s, so a job registered at
## every(0.05).seconds really does fire at 20 Hz -- the same responsiveness as a
## hand-rolled loop, but non-blocking, logged as a periodic_task event, and
## stoppable without Ctrl-C.
##
## start()             -> schedules the jobs, returns to the prompt
## start(scheduled=False) -> the old blocking loop, for bench work
## animate()           -> watch the pumps; run it whenever, jobs keep running

_CONSOLE = None        ## set to Live's console while the live view is up

def _emit(msg):
	"""Print a log line without fighting the live display.

	While Live is running, plain print() writes straight over the panel; Live's
	own console prints ABOVE it and keeps the panel pinned to the bottom.
	"""
	if _CONSOLE is not None:
		_CONSOLE.print(msg)
	else:
		print(msg)


JOBS = []              ## scheduled jobs owned by this script
JOB_TAG = "keypad_pump_test"    ## every job we register carries this tag
N_COMMANDS = 0         ## commands applied since start()

## Ctrl-C does NOT stop scheduled polling: the jobs run in exp.schedule's own
## thread, so KeyboardInterrupt only interrupts whatever is in the foreground.
## Use stop_jobs(), stop(), or panic(). Because ScriptEngine re-execs this file
## into the CLI globals, JOBS is reset on every re-run while the previously
## registered jobs keep firing -- so cancellation goes through the TAG, which
## survives the re-exec, rather than through the JOBS list alone.


def poll_once():
	"""One poll: drain the keypad, apply to the pumps, log. Never raises.

	Hard requirement, not politeness: exp.schedule's run_pending() does not
	catch job exceptions, so anything escaping here kills the scheduler thread
	and silently stops every other periodic task in the experiment.
	"""
	try:
		return _poll_once()
	except Exception as err:
		log.error("poll_once failed: %s", err)
		return 0


def _poll_once():
	global N_COMMANDS
	if PUMPSET is None:
		return 0
	try:
		lines = _read_keypad()
	except Exception as err:
		log.error("keypad read failed: %s", err)
		return 0

	stream = exp.mstreams["keypress"] if exp is not None else None
	applied = 0
	for line in (lines or []):
		try:
			st = PUMPSET.command(line)
		except Exception as err:
			log.error("pump command failed on %r: %s", line, err)
			continue
		if st is None:
			continue
		applied += 1
		N_COMMANDS += 1
		_emit("  [cyan]{}[/cyan] -> {} {:.3f}".format(
				line, st.get("mode", "?"), st.get("speed", 0.0)))
		if stream is not None:
			parsed = parse_line(line)
			if parsed:
				try:
					stream(pump=parsed[0], verb=parsed[1], value=parsed[2],
							applied_speed=round(st.get("speed", 0.0), 4))
				except Exception as err:
					log.error("measurement stream write failed: %s", err)
	return applied


def mirror_once():
	"""Push pump state onto the keypad LEDs. Never raises."""
	try:
		return push_to_keypad()
	except Exception as err:
		log.error("keypad mirror failed: %s", err)
		return []


def start(poll_s=None, mirror_s=None, duration_min=None, scheduled=False,
			live=True, fps=12):
	"""Start polling the keypad and driving the pumps.

	Default is the inline loop: it owns the terminal, renders the live view, and
	Ctrl-C stops it and prints the closing table. This is the one you want while
	testing the keypad.

	scheduled=True instead registers jobs on exp.schedule and RETURNS, leaving
	the prompt free -- good for a long run you want to leave going. There is no
	live view in that mode (nothing owns the terminal); call animate() to watch,
	and stop_jobs() / panic() to end it, since Ctrl-C will not.
	"""
	global exp, scope, JOBS, N_COMMANDS
	scope = ScopeAssembly.current

	if PUMPSET is None:
		print("[red]No pumps registered. Run add_pumps() first.[/]")
		return
	try:
		kp()
	except AttributeError:
		print("[red]ScopeAssembly.current.kp is not mounted.[/]")
		return

	if poll_s is None:
		poll_s = exp.attribs["poll_period_s"] if exp is not None else 0.05
	if mirror_s is None:
		mirror_s = MIRROR_PERIOD_S

	print("[bold green]Keypad -> {} pumps.[/bold green] {}".format(
			"simulated" if SIMULATED else "[yellow]REAL[/yellow]",
			"Ctrl-C to stop." if not scheduled else ""))
	sync_from_keypad()
	N_COMMANDS = 0

	if not scheduled:
		return _blocking_loop(poll_s, duration_min, live, fps)


	if exp is None:
		print("[red]No experiment -- run create_exp(), or use scheduled=False.[/]")
		return
	orphans = stop_jobs(quiet=True)
	if orphans:
		print("[yellow]Cancelled {} job(s) left over from a previous run.[/]".format(
				orphans))

	poll_job = exp.schedule.every(poll_s).seconds
	mirror_job = exp.schedule.every(mirror_s).seconds
	if duration_min is not None:
		poll_job = poll_job.until(timedelta(minutes=duration_min))
		mirror_job = mirror_job.until(timedelta(minutes=duration_min))
	JOBS = [poll_job.do(poll_once).tag(JOB_TAG)]
	if MIRROR:
		JOBS.append(mirror_job.do(mirror_once).tag(JOB_TAG))

	exp.attribs["poll_period_s"] = poll_s
	exp.attribs["mirror_period_s"] = mirror_s
	exp.attribs["scheduled"] = True

	print("[green]Scheduled[/] poll every {}s, mirror every {}s{}.".format(
			poll_s, mirror_s,
			"" if duration_min is None else ", for {} min".format(duration_min)))
	print("  [dim]prompt is free -- animate() to watch, status() for a snapshot.[/dim]")
	print("  [yellow]Ctrl-C will NOT stop this[/] (it runs in exp.schedule's "
			"thread): use [bold]stop_jobs()[/bold], stop(), or panic().")
	return JOBS


def stop_jobs(quiet=False):
	"""Cancel this script's scheduled jobs, leaving the experiment open.

	Clears by TAG, not by the JOBS list, so it also kills orphans left behind by
	an earlier run of this script -- re-running via ScriptEngine resets JOBS but
	not the scheduler.
	"""
	global JOBS
	killed = 0
	if exp is not None:
		before = len(exp.schedule.get_jobs())
		try:
			exp.schedule.clear(JOB_TAG)
		except Exception:
			for job in JOBS:
				try:
					exp.schedule.cancel_job(job)
				except Exception:
					pass
		killed = before - len(exp.schedule.get_jobs())
	JOBS = []
	if killed and not quiet:
		print("[dim]Cancelled {} scheduled job(s).[/dim]".format(killed))
	return killed


def jobs():
	"""Scheduled jobs currently registered by this script."""
	if exp is None:
		return []
	return [j for j in exp.schedule.get_jobs() if JOB_TAG in getattr(j, "tags", ())]


def panic():
	"""Everything off, now. Cancels jobs, stops pumps, clears the keypad.

	The one call to reach for when Ctrl-C did not do what you wanted.
	"""
	stop_jobs()
	try:
		if PUMPSET is not None:
			PUMPSET.stop_all()
	except Exception as err:
		log.error("stop_all failed: %s", err)
	try:
		kp().stop_all()
	except Exception:
		pass
	mirror_once()
	print("[bold red]PANIC[/bold red] -- jobs cancelled, pumps stopped.")
	status()


def is_running():
	"""True when a poll job is registered -- including one from an earlier run."""
	return bool(jobs())


def _blocking_loop(period, duration_min, live, fps):
	"""Inline loop: live view, Ctrl-C to stop, closing table on the way out."""
	global _CONSOLE
	deadline = None if duration_min is None else time.time() + duration_min * 60
	t0 = time.time()
	display = None
	try:
		if live:
			from rich.live import Live
			display = Live(_frame(t0), refresh_per_second=fps,
							transient=False, redirect_stdout=False,
							redirect_stderr=False)
			display.start()
			_CONSOLE = display.console

		next_frame = 0.0
		next_mirror = 0.0
		while True:
			poll_once()
			now = time.time()
			if MIRROR and now >= next_mirror:
				next_mirror = now + MIRROR_PERIOD_S
				mirror_once()
			if display is not None and now >= next_frame:
				next_frame = now + 1.0 / fps
				display.update(_frame(t0))
			if deadline is not None and now > deadline:
				print("[yellow]Duration reached.[/]")
				break
			time.sleep(period)
	except KeyboardInterrupt:
		pass
	finally:
		## Tear the display down FIRST, so the closing report is not swallowed
		## by the live region or overwritten when it repaints.
		if display is not None:
			try:
				display.stop()
			except Exception:
				pass
		_CONSOLE = None
		print("\n[yellow]Keypad polling stopped.[/]")
		try:
			PUMPSET.stop_all()
			mirror_once()
		except Exception as err:
			log.error("stopping pumps failed: %s", err)
		print("[dim]All pumps stopped. {} commands processed in {:.0f}s.[/dim]".format(
				N_COMMANDS, time.time() - t0))
		status()


def _states_or_warn():
	"""PUMPSET.state() as a dict, or None after complaining.

	A remote pumpset can hand back a repr string the proxy failed to parse; the
	display code must not explode on it.
	"""
	try:
		states = PUMPSET.state()
	except Exception as err:
		log.error("pumpset.state() failed: %s", err)
		return None
	if states is None:
		return {}
	if not isinstance(states, dict):
		print("[red]pumpset.state() returned {} rather than a dict[/] -- "
				"the proxy could not parse the reply.".format(type(states).__name__))
		return None
	return states


def status():
	"""One-shot table of pump state."""
	if PUMPSET is None:
		print("[red]Run add_pumps() first.[/]")
		return
	table = Table(title="pumps ({})".format("simulated" if SIMULATED else "real"))
	for col in ("n", "name", "role", "mode", "speed", "band", "fast", "duty",
				"cont", "lvl%", "vol ml"):
		table.add_column(col)

	states = _states_or_warn()
	if states is None:
		return
	for n, st in sorted(states.items()):
		st = st or {}
		mode = st.get("mode", "?")
		style = {"fast": "[green]fast[/green]", "slow": "[bright_cyan]slow[/bright_cyan]",
					"pulse": "[cyan]pulse[/cyan]"}.get(mode, "[dim]idle[/dim]")
		lo, hi = st.get("slow_limits", (0.0, 0.0))
		table.add_row(
			str(n), str(st.get("name", "")),
			"[cyan]aeration[/cyan]" if is_aeration(n) else "[dim]perfusion[/dim]",
			style,
			"{:.3f}".format(st.get("speed", 0.0)),
			"{:.2f}-{:.2f}".format(lo, hi),
			"{:.2f}".format(st.get("fast_speed", 0.0)),
			"[dim]n/a[/dim]" if st.get("continuous")
				else "{}s/{}s".format(*st.get("pulse_duty", ("-", "-"))),
			"[bright_cyan]yes[/bright_cyan]" if st.get("continuous") else "[dim]no[/dim]",
			str(st.get("percent", "-")),
			"[dim]n/a[/dim]" if is_aeration(n)
				else ("{:.3f}".format(st["volume_ml"]) if "volume_ml" in st else "-"),
		)
	print(table)


def _sync_dir():
	"""rsync the experiment payload to exp.destination_dir, when there is one.

	destination_dir is None unless the experiment yaml declared it, and
	ExpSync.sync_dir() raises if the directory has gone missing -- so this is
	guarded rather than called blind. Skipped if attribs["autosync_dir"] is
	explicitly False.
	"""
	if exp is None:
		return None
	dest = getattr(exp, "destination_dir", None)
	if not dest:
		print("[dim]No exp.destination_dir declared -- nothing to sync.[/dim]")
		return None
	if exp.attribs.get("autosync_dir") is False:
		print("[dim]autosync_dir is off -- skipping sync to {}[/dim]".format(dest))
		return None
	try:
		out = exp.sync_dir()
		print("[green]Synced[/] experiment directory -> {}".format(dest))
		return out
	except Exception as err:
		## Never let a failed copy take down the shutdown path: the pumps are
		## already stopped by this point and that matters more.
		log.error("sync_dir failed: %s", err)
		print("[red]Sync failed:[/] {}".format(err))
		return None


def stop():
	"""Cancel the jobs, safe-state the pumps, sync, close the experiment."""
	global exp
	stop_jobs()
	if PUMPSET is not None:
		PUMPSET.stop_all()
		mirror_once()
		if exp is not None:
			exp.logs["totals"] = PUMPSET.state()
			exp.logs["commands_applied"] = N_COMMANDS
	if exp is not None:
		exp.logs.update(ScopeAssembly.current.get_config())
		exp.__save__()
		_sync_dir()
		exp.close()
	print("[green]Stopped.[/] Pumps safe, experiment closed.")


## End of initalization message
print("Script initalization finished.")

if __name__ == "__main__":
	create_exp()
	add_pumps(simulated=True)
	check_api()
	print("[bold]Ready.[/bold] start() polls the keypad; animate() just watches.")
