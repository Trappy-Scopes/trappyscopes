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
print("  add_pumps()    register scope.pump1/2/3 (simulated)")
print("  start()        poll the keypad until Ctrl-C")
print("  status()       one-shot table of pump state")
print("  stop()         safe-state everything and close the experiment")


## ---------------------------------------------------------------- simulated pump
class SimPump():
	"""Simulated peristaltic pump.

	Mirrors `pico_firmware.actuators.dcmotor.DCMotor` so that a real motor proxy
	can be dropped in unchanged: speed()/fwd()/rev()/hold()/release(), plus the
	`duty`, `dir` and `speed_` attributes.
	"""

	def __init__(self, name, ml_per_min=45.0, verbose=True):
		self.name = name
		self.devicetype = "sim.pump"
		self.description = "Simulated peristaltic pump"
		self.ml_per_min = ml_per_min      ## calibrated flow at full speed
		self.verbose = verbose

		self.speed_ = 0.0                 ## 0.0 - 1.0, magnitude only
		self.dir = +1                     ## +1 forward, -1 reverse
		self.duty = 0                     ## 0 - 65535, as the real motor reports
		self.released = True

		self._volume_ml = 0.0             ## integrated delivered volume
		self._runtime_s = 0.0             ## integrated time spent moving
		self._t_last = time.time()
		self._changes = 0

	## -- DCMotor-compatible verbs ------------------------------------------------
	def speed(self, unit_speed=None):
		"""Get or set unit speed (0.0 - 1.0), keeping the current direction."""
		if unit_speed is None:
			return self.speed_
		self._integrate()
		self.speed_ = min(1.0, max(0.0, float(unit_speed)))
		self.duty = int(self.speed_ * 65535)
		self.released = False
		self._changes += 1
		self._announce()
		return self.speed_

	def fwd(self, speed=None):
		self._integrate()
		self.dir = +1
		return self.speed(self.speed_ if speed is None else speed)

	def rev(self, speed=None):
		self._integrate()
		self.dir = -1
		return self.speed(self.speed_ if speed is None else speed)

	def hold(self):
		"""Stop, brakes engaged. The safe state."""
		self._integrate()
		self.speed_ = 0.0
		self.duty = 0
		self.released = False
		self._announce()

	def release(self):
		"""Stop, coasting."""
		self.hold()
		self.released = True

	def min_speed(self):
		return 0.0

	def max_speed(self):
		return 1.0

	## -- simulation bookkeeping --------------------------------------------------
	def _integrate(self):
		"""Accumulate delivered volume for the interval just ended."""
		now = time.time()
		dt = now - self._t_last
		self._t_last = now
		if self.speed_ > 0.0 and not self.released:
			self._runtime_s += dt
			self._volume_ml += self.ml_per_min * self.speed_ * dt / 60.0

	def flow_ml_min(self):
		return self.ml_per_min * self.speed_ * (0.0 if self.released else 1.0)

	def volume_ml(self):
		self._integrate()
		return self._volume_ml

	def runtime_s(self):
		self._integrate()
		return self._runtime_s

	def is_running(self):
		return (self.speed_ > 0.0) and (not self.released)

	def _announce(self):
		if not self.verbose:
			return
		arrow = "[green]>>[/green]" if self.dir > 0 else "[yellow]<<[/yellow]"
		if not self.is_running():
			print("  [dim]{:<6} idle[/dim]".format(self.name))
		else:
			print("  {:<6} {} {:>3.0f}%  {:.1f} ml/min".format(
				self.name, arrow, self.speed_ * 100, self.flow_ml_min()))

	## -- assembly hooks ----------------------------------------------------------
	def state(self):
		return {"speed": round(self.speed_, 3), "dir": self.dir, "duty": self.duty,
				"released": self.released, "flow_ml_min": round(self.flow_ml_min(), 2),
				"volume_ml": round(self.volume_ml(), 3),
				"runtime_s": round(self.runtime_s(), 1)}

	def __getstate__(self):
		return self.state()

	def close(self):
		self.hold()

	def __repr__(self):
		return "<SimPump {} {:.0f}% dir={}>".format(self.name, self.speed_ * 100, self.dir)


## ---------------------------------------------------------------- keypad state
## Mirrors what the keypad believes, so POWER/PULSE precedence is resolved here
## rather than trusting a possibly-missed command.
KEYSTATE = {}
PUMPMAP  = {}       ## keypad pump number -> scope device name
FAST_PCT = 100      ## speed used by POWER (fast mode)


def parse_line(line):
	"""'PUMP 2 SPEED 45' -> (2, 'SPEED', 45). None if it is not a command."""
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


def apply_command(n, verb, value):
	"""Fold one command into KEYSTATE and push the result to the pump."""
	global scope
	st = KEYSTATE.setdefault(n, {"power": False, "pulse": False, "speed": 30})

	if verb == "POWER":
		st["power"] = bool(value)
	elif verb == "PULSE":
		st["pulse"] = bool(value)
	elif verb == "SPEED":
		st["speed"] = min(100, max(0, int(value)))
	elif verb == "LIMIT":
		## UI feedback only -- the keypad hit a rail. Worth logging, not acting on.
		log.debug("keypad pump %s at %s limit", n, value)
		return st

	device = PUMPMAP.get(n)
	if device is None:
		log.error("keypad reported pump %s, which is not registered on the scope", n)
		return st

	pump = getattr(scope, device)
	if st["power"]:
		pct = FAST_PCT
	elif st["pulse"]:
		pct = st["speed"]
	else:
		pct = 0

	if pct <= 0:
		pump.hold()
	else:
		pump.fwd(pct / 100.0)
	return st


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
def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["keypad", "pump", "test", "simulated"],
								user=True, eid=True, date=True, time=True, scopeid=True)
	exp.new_measurementstream("keypress",
								measurements=["pump", "verb", "value", "applied_pct"])
	exp.attribs["pumps"] = [1, 2, 3]
	exp.attribs["fast_pct"] = FAST_PCT
	exp.attribs["ml_per_min"] = 45.0
	exp.attribs["poll_period_s"] = 0.05
	exp.attribs["simulated"] = True
	print("[green]Experiment ready.[/] Now run add_pumps().")


def add_pumps(names=("pump1", "pump2", "pump3")):
	"""Register the simulated pumps and wire them to keypad pump numbers.

	To go live, replace SimPump(...) with the Pico motor proxy -- the verb set
	(fwd/rev/hold/release/speed) is deliberately identical.
	"""
	global scope, exp
	scope = ScopeAssembly.current
	rate = exp.attribs["ml_per_min"] if exp is not None else 45.0

	PUMPMAP.clear()
	KEYSTATE.clear()
	for i, name in enumerate(names):
		n = i + 1
		if getattr(scope, name, None) is None:
			scope.add_device(name, SimPump(name, ml_per_min=rate),
								description="Simulated peristaltic pump {}".format(n))
		PUMPMAP[n] = name
		KEYSTATE[n] = {"power": False, "pulse": False, "speed": 30}

	print(scope.draw_tree())
	print("[green]Mapped[/] keypad -> " + ", ".join(
		"{}:{}".format(k, v) for k, v in sorted(PUMPMAP.items())))


def sync_from_keypad():
	"""Pull the keypad's own view of the world and adopt it.

	Use after a reconnect, or if the host has been away and the pending queue
	overflowed. `snapshot_lines()` is authoritative.
	"""
	global scope
	try:
		lines = kp().snapshot_lines()
	except Exception as err:
		log.error("keypad snapshot unavailable (%s) -- starting from local state", err)
		return
	for line in (lines or []):
		parsed = parse_line(line)
		if parsed:
			apply_command(*parsed)
			_LAST_SNAPSHOT[(parsed[0], parsed[1])] = parsed[2]
	print("[green]Synced[/] from keypad snapshot.")
	status()


## ---------------------------------------------------------------- main loop
def start(duration_min=None, live=True, fps=12):
	"""Poll the keypad and drive the pumps until Ctrl-C (or duration_min).

	The keypad is resolved as `ScopeAssembly.current.kp` on every read, and the
	read strategy is probed once by `_read_keypad()`, so this works whether `kp`
	is a local object, a MicroPython proxy, or something that only offers
	`snapshot_lines()`.
	"""
	global exp, scope
	scope = ScopeAssembly.current

	if not PUMPMAP:
		print("[red]No pumps registered. Run add_pumps() first.[/]")
		return
	try:
		kp()
	except AttributeError:
		print("[red]ScopeAssembly.current.kp is not mounted.[/]")
		return

	period = exp.attribs["poll_period_s"] if exp is not None else 0.05
	stream = exp.mstreams["keypress"] if exp is not None else None
	deadline = None if duration_min is None else time.time() + duration_min * 60

	print("[bold green]Polling keypad.[/bold green] Ctrl-C to stop.")
	sync_from_keypad()

	## Silence the per-change pump chatter -- the live view replaces it.
	for device in PUMPMAP.values():
		getattr(scope, device).verbose = not live

	n_cmds = 0
	t0 = time.time()
	display = None
	try:
		if live:
			from rich.live import Live
			display = Live(_frame(t0), refresh_per_second=fps, transient=False)
			display.start()

		next_frame = 0.0
		while True:
			try:
				lines = _read_keypad()
			except Exception as err:
				## Serial hiccup or the device vanished -- back off, keep the
				## pumps where they are, and try again rather than dying.
				log.error("keypad read failed: %s", err)
				time.sleep(1.0)
				continue

			for line in (lines or []):
				parsed = parse_line(line)
				if parsed is None:
					continue
				n, verb, value = parsed
				apply_command(n, verb, value)
				n_cmds += 1

				device = PUMPMAP.get(n)
				applied = 0.0
				if device is not None:
					pump = getattr(scope, device)
					applied = round(pump.speed() * 100, 1)
				msg = "  [cyan]{}[/cyan] -> {} @ {}%".format(line, device, applied)
				## Log lines scroll ABOVE the live panel rather than fighting it.
				if display is not None:
					display.console.print(msg)
				else:
					print(msg)
				if stream is not None:
					stream(pump=n, verb=verb, value=value, applied_pct=applied)

			now = time.time()
			if display is not None and now >= next_frame:
				next_frame = now + 1.0 / fps
				display.update(_frame(t0))

			if deadline is not None and now > deadline:
				print("[yellow]Duration reached.[/]")
				break
			time.sleep(period)

	except KeyboardInterrupt:
		print("\n[yellow]Keypad polling interrupted.[/]")
	finally:
		if display is not None:
			display.stop()
		for device in PUMPMAP.values():
			getattr(scope, device).verbose = True
		## Safe-state whatever happens -- simulated or not, this is the habit.
		for device in PUMPMAP.values():
			getattr(scope, device).hold()
		print("[dim]All pumps held. {} commands processed.[/dim]".format(n_cmds))
		status()


## ---------------------------------------------------------------- live view
## A real-time terminal animation of the pumps: a rotating pump head whose spin
## rate tracks speed, a tube with fluid slugs travelling along it in the running
## direction, a speed bar, and a running volume total.

ROTOR   = "|/-\\"                     ## pump head, spun at speed
TUBE_W  = 26                          ## characters of tubing drawn per pump
SLUG    = "█"                    ## the fluid slug glyph
TUBE_BG = "·"                    ## empty tubing
SLUG_GAP = 5                          ## characters between slugs

## Fluid colour tracks speed, mirroring the keypad's own blue -> aqua -> hot ramp.
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
	"""One line of animated tubing. `phase` advances with elapsed time."""
	from rich.text import Text
	style = _flow_style(frac)
	if frac <= 0.0:
		return Text(TUBE_BG * TUBE_W, style="grey30")

	offset = int(phase) % SLUG_GAP
	cells = []
	for i in range(TUBE_W):
		pos = (i - offset) if direction > 0 else (i + offset)
		cells.append(SLUG if pos % SLUG_GAP == 0 else TUBE_BG)
	text = Text("".join(cells), style=style)
	return text


def _bar(frac, width=14):
	from rich.text import Text
	filled = int(round(frac * width))
	t = Text()
	t.append("━" * filled, style=_flow_style(frac))
	t.append("━" * (width - filled), style="grey30")
	return t


def _frame(t0):
	"""Build one frame of the live view."""
	from rich.table import Table as _T
	from rich.text import Text
	from rich.console import Group
	from rich.panel import Panel

	scope_ = ScopeAssembly.current
	now = time.time()
	elapsed = now - t0

	grid = _T.grid(padding=(0, 1))
	for _ in range(7):
		grid.add_column()

	total_ml = 0.0
	for n in sorted(PUMPMAP):
		device = PUMPMAP[n]
		pump = getattr(scope_, device)
		st = KEYSTATE.get(n, {})
		frac = pump.speed()
		total_ml += pump.volume_ml()

		## Rotor spins proportionally to speed; 6 rev/s at full tilt.
		if frac > 0:
			idx = int(elapsed * frac * 24) % len(ROTOR)
			rotor = Text(ROTOR[idx], style=_flow_style(frac))
		else:
			rotor = Text("o", style="grey30")

		if st.get("power"):
			mode = Text("FAST", style="bold green")
		elif st.get("pulse"):
			mode = Text("pulse", style="cyan")
		else:
			mode = Text("idle", style="grey30")

		grid.add_row(
			Text("{}".format(device), style="bold" if frac > 0 else "grey50"),
			rotor,
			mode,
			_bar(frac),
			Text("{:>3.0f}%".format(frac * 100),
					style=_flow_style(frac) if frac else "grey30"),
			_tube(frac, pump.dir, elapsed * frac * 34),
			Text("{:>7.2f} ml".format(pump.volume_ml()),
					style="white" if frac else "grey50"),
		)

	footer = Text.assemble(
		("elapsed ", "grey50"), ("{:>6.1f}s".format(elapsed), "white"),
		("   total ", "grey50"), ("{:.2f} ml".format(total_ml), "bright_white"),
		("   ctrl-c to stop", "grey50"))
	return Panel(Group(grid, Text(""), footer),
					title="[bold]pumps[/bold] -- live",
					border_style="grey37")


def animate(fps=12, duration_s=None):
	"""Watch the pumps without touching the keypad. Ctrl-C to exit.

	Useful on its own while you drive the pumps from another prompt, e.g.
	`scope.pump1.fwd(0.4)`.
	"""
	from rich.live import Live
	t0 = time.time()
	try:
		with Live(_frame(t0), refresh_per_second=fps, transient=False) as live:
			while True:
				time.sleep(1.0 / fps)
				live.update(_frame(t0))
				if duration_s is not None and time.time() - t0 > duration_s:
					break
	except KeyboardInterrupt:
		print("[yellow]Animation stopped.[/]")


def status():
	"""One-shot table of keypad intent versus simulated pump state."""
	global scope
	scope = ScopeAssembly.current
	table = Table(title="keypad -> simulated pumps")
	for col in ("kp", "device", "power", "pulse", "set %", "out %",
				"ml/min", "volume ml", "run s"):
		table.add_column(col)

	for n in sorted(PUMPMAP):
		device = PUMPMAP[n]
		pump = getattr(scope, device)
		st = KEYSTATE.get(n, {})
		table.add_row(
			str(n), device,
			"[green]ON[/green]" if st.get("power") else "[red]off[/red]",
			"[cyan]ON[/cyan]" if st.get("pulse") else "[dim]off[/dim]",
			str(st.get("speed", "-")),
			"{:.0f}".format(pump.speed() * 100),
			"{:.2f}".format(pump.flow_ml_min()),
			"{:.3f}".format(pump.volume_ml()),
			"{:.1f}".format(pump.runtime_s()),
		)
	print(table)


def stop():
	"""Safe-state the pumps, log the totals, close the experiment."""
	global exp, scope
	scope = ScopeAssembly.current
	for device in PUMPMAP.values():
		getattr(scope, device).hold()

	if exp is not None:
		exp.logs["totals"] = dict(
			(device, getattr(scope, device).state()) for device in PUMPMAP.values())
		exp.logs.update(scope.get_config())
		exp.__save__()
		exp.close()
	print("[green]Stopped.[/] Pumps held, experiment closed.")


## End of initalization message
print("Script initalization finished.")

if __name__ == "__main__":
	## This part will always run -- ScriptEngine execs into the CLI globals.
	create_exp()
	add_pumps()
	print("[bold]Ready.[/bold] Call start() to begin polling the keypad.")
