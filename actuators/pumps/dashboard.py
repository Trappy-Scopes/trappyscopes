"""The live view, the status table, and the volume integrator.

One dashboard, used by every pump script. It reads nothing but PumpSet.state(),
so it renders identically for real and simulated pumps.

Two things it does that are not obvious:

  * the SET speed is always shown, not just the live one. In pulse mode the live
    speed drops to zero between bursts; the number you tuned is the one you want
    on screen, so the bar empties but a caret marks where it will run.

  * volume is integrated HERE, from the stored calibration, because the firmware
    does not track it -- state() has no volume_ml. With no calibration it falls
    back to run time, which needs none and is exactly what you need to
    reconstruct the volume once a calibration exists.
"""

import logging as log
import time

from rich import print
from rich.table import Table

from hive.assembly import ScopeAssembly


PUMPSET = None
SIMULATED = False
PUMP_ROLES = {}

## Optional hooks. The dashboard does not own the serial link -- a script that
## cares can point these at actuators.pumps.remote.relink() and friends, and a
## script that does not gets plain logging.
ON_LINK_ERROR = None
ON_LINK_OK = None


def _link_error(where, err):
	if ON_LINK_ERROR is not None:
		return ON_LINK_ERROR(where, err)
	log.error("%s failed: %s", where, err)
	return False


def _link_ok():
	if ON_LINK_OK is not None:
		return ON_LINK_OK()
	return None


def role(n):
	return PUMP_ROLES.get(n, "perfusion")


def is_aeration(n):
	return role(n) == "aeration"


def _setpoint_default():
	return 0.0


## ---------------------------------------------------------------- volume
## The firmware pumps do not integrate volume -- state() has no volume_ml, which
## is why that column read "-" against real hardware. Nothing was broken; there
## was simply nothing to show. So the host integrates it here, from the stored
## calibration, and says "no calib" when there is none rather than showing a
## number it cannot justify.

_VOL = {}                  ## pump -> ml delivered since the last reset
_RUN = {}                  ## pump -> seconds actually pumping since the reset
_VOL_T = {}                ## pump -> last sample time
_CALIB_CACHE = {}          ## pump -> calibration dict, read once


def load_calibration(pumpset, refresh=False):
	"""Cache each pump's stored calibration so the frame loop is not doing IO."""
	global _CALIB_CACHE
	if _CALIB_CACHE and not refresh:
		return _CALIB_CACHE
	out = {}
	scope_ = ScopeAssembly.current
	for n in (pumpset.numbers() if pumpset is not None else ()):
		proxy = getattr(scope_, "pump{}".format(n), None)
		params = getattr(proxy, "params", None)
		if params is None:
			continue
		try:
			state = params.__getstate__()
		except Exception:
			continue
		out[n] = dict((k, v) for k, v in state.items() if k.startswith("calib"))
	_CALIB_CACHE = out
	return out


def rate_ml_min(n, st):
	"""Instantaneous delivery rate implied by the calibration, or None.

	fast mode  -- scale the measured prime rate by speed / calib_fast_speed
	pulse mode -- a burst delivers (a*speed + b) ml over on_s seconds, so while
	              the burst is running the rate is that over on_s
	"""
	calib = _CALIB_CACHE.get(n)
	if not calib or not st:
		return None
	speed = float(st.get("speed") or 0.0)
	if speed <= 0:
		return 0.0

	if st.get("mode") == "fast":
		ref = calib.get("calib_fast_ml_min")
		at = calib.get("calib_fast_speed") or 1.0
		return None if ref is None else ref * speed / float(at)

	slope = calib.get("calib_pulse_slope")
	if slope is None:
		return None
	per_cycle = slope * speed + (calib.get("calib_pulse_intercept") or 0.0)
	on_s = float((st.get("pulse_duty") or (5, 55))[0]) or 5.0
	return max(0.0, per_cycle) * 60.0 / on_s


def _accrue(states):
	"""Integrate delivered volume for every pump, once per frame."""
	now = time.time()
	for n, st in (states or {}).items():
		last = _VOL_T.get(n)
		_VOL_T[n] = now
		if last is None:
			continue
		dt = now - last
		## Run time is measurable without any calibration at all -- it only
		## needs to know whether the pump is turning. It is what the volume
		## column falls back to, so an uncalibrated rig still shows something
		## true and useful rather than a dash.
		if float(st.get("speed") or 0.0) > 0:
			_RUN[n] = _RUN.get(n, 0.0) + dt
		rate = rate_ml_min(n, st)
		if rate:
			_VOL[n] = _VOL.get(n, 0.0) + rate * dt / 60.0


def volumes():
	"""Delivered volume per pump since the last reset, in ml."""
	return dict(_VOL)


def runtimes():
	"""Seconds each pump has actually been turning since the last reset.

	Always available -- no calibration needed. Multiply by a rate later and an
	uncalibrated run is still recoverable.
	"""
	return dict(_RUN)


def reset_volumes():
	"""Zero the integrators -- call it when you swap the reservoir."""
	_VOL.clear()
	_RUN.clear()
	_VOL_T.clear()
	print("[green]Volume and run-time counters reset.[/]")


def _setpoint(st):
	"""The speed this pump WILL run at, whether or not it is running now.

	In pulse mode the live speed drops to zero between bursts; the set speed is
	the number you actually tuned, so it stays on screen.
	"""
	if not st:
		return 0.0
	if st.get("mode") == "fast":
		return float(st.get("fast_speed") or 0.0)
	lo, hi = (st.get("slow_limits") or (0.0, 1.0))[:2]
	level = st.get("level")
	if level is None:
		level = float(st.get("percent") or 0) / 100.0
	return float(lo) + (float(hi) - float(lo)) * float(level)


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


def _bar(speed, full_scale, slow_min, slow_max, width=16, setpoint=None):
	"""Absolute speed bar, with the set speed marked.

	The bar is the LIVE speed; the caret is where it is set to run. Between
	bursts the bar empties but the caret stays, so a pump that is merely idle
	between pulses does not look like a pump that is switched off.
	"""
	from rich.text import Text
	if full_scale <= 0:
		full_scale = 1.0
	t = Text()
	style = _flow_style(speed / full_scale)
	mark = int(round((setpoint or 0.0) / full_scale * width))
	for i in range(width):
		pos = (i + 0.5) / width * full_scale
		if setpoint and i == min(width - 1, max(0, mark - 1)) and pos > speed:
			t.append("\u2502", style="bright_white")      ## set-speed caret
		elif pos <= speed:
			t.append("\u2501", style=style)
		elif slow_min <= pos <= slow_max:
			t.append("\u2504", style="grey42")            ## the adjustable band
		else:
			t.append("\u2501", style="grey27")
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
			_link_ok()
		except Exception as err:
			_link_error("pumpset.state()", err)

	grid = _T.grid(padding=(0, 1))
	for _ in range(10):
		grid.add_column()

	## header row, so the bare numbers are self-describing
	_h = lambda s_: Text(s_, style="grey50")
	grid.add_row(_h("pump"), _h(""), _h("mode"), _h("speed bar  \u2502=set"),
					_h("now"), _h("set"), _h("band"), _h("fast"), _h("flow"),
					_h("volume"))

	_accrue(states)
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
			## simulated pumps integrate their own
			has_volume = True
			total_ml += float(st["volume_ml"])
			vol = Text("{:>7.2f} ml".format(st["volume_ml"]),
						style="white" if frac else "grey50")
		elif n in _CALIB_CACHE:
			## integrated here from the stored calibration
			ml = _VOL.get(n, 0.0)
			has_volume = True
			total_ml += ml
			vol = Text("{:>7.2f} ml".format(ml),
						style="white" if frac else "grey50")
		else:
			## No calibration: show run time instead. Honest, and it is exactly
			## what you need to reconstruct the volume once a calibration exists.
			secs = _RUN.get(n, 0.0)
			vol = Text("{:>6.0f} s run".format(secs),
						style="grey58" if secs else "grey30")

		## Everything below is an absolute PWM unit speed (0.0 - 1.0), not a
		## percentage of the band -- percentages hid how slow "slow" really is.
		lo, hi = st.get("slow_limits", (0.0, 1.0))
		fast_speed = st.get("fast_speed", 1.0)
		full_scale = max(fast_speed, hi) or 1.0
		setpoint = _setpoint(st)

		grid.add_row(
			Text(str(st.get("name", n)), style="bold" if frac > 0 else "grey50"),
			rotor,
			mode_txt,
			_bar(frac, full_scale, lo, hi, setpoint=setpoint),
			Text("{:>5.3f}".format(frac),
					style=_flow_style(frac / full_scale) if frac else "grey30"),
			Text("{:>5.3f}".format(setpoint),
					style="white" if setpoint else "grey30"),
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
		print("[red]Run connect() first.[/]")
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
def _states_or_warn():
	"""PUMPSET.state() as a dict, or None after complaining.

	A remote pumpset can hand back a repr string the proxy failed to parse; the
	display code must not explode on it.
	"""
	try:
		states = PUMPSET.state()
	except Exception as err:
		_link_error("pumpset.state()", err)
		return None
	_link_ok()
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
		print("[red]Run connect() first.[/]")
		return
	table = Table(title="pumps ({})".format(
			"simulated" if SIMULATED else "real hardware"))
	for col in ("n", "name", "role", "mode", "now", "set", "band", "fast",
				"duty", "cont", "lvl%", "vol ml"):
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
			"{:.3f}".format(_setpoint(st)),
			"{:.2f}-{:.2f}".format(lo, hi),
			"{:.2f}".format(st.get("fast_speed", 0.0)),
			"[dim]n/a[/dim]" if st.get("continuous")
				else "{}s/{}s".format(*st.get("pulse_duty", ("-", "-"))),
			"[bright_cyan]yes[/bright_cyan]" if st.get("continuous") else "[dim]no[/dim]",
			str(st.get("percent", "-")),
			"[dim]n/a[/dim]" if is_aeration(n)
				else ("{:.3f}".format(st["volume_ml"]) if "volume_ml" in st
					## a calibrated pump that has not moved yet is 0.000, not
					## "no calib" -- only an uncalibrated one cannot be counted
					else ("{:.3f}".format(_VOL.get(n, 0.0)) if n in _CALIB_CACHE
						else "[dim]{:.0f}s run[/dim]".format(_RUN.get(n, 0.0)))),
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




class Dashboard:
	"""Live view + status table + integrators for one pump set.

	    dash = Dashboard(pumpset, roles={1:"perfusion", 3:"aeration"})
	    dash.load_calibration()
	    dash.live(fps=12)          # blocking, ctrl-c
	    dash.status()
	"""

	def __init__(self, pumpset, roles=None, simulated=False):
		self.pumpset = pumpset
		self.roles = roles or {}
		self.simulated = simulated
		self.reset()

	## -- wiring to the module-level implementation ---------------------------
	def _bind(self):
		global PUMPSET, SIMULATED, PUMP_ROLES
		PUMPSET = self.pumpset
		SIMULATED = self.simulated
		PUMP_ROLES = self.roles

	def reset(self):
		"""Zero the volume and run-time counters."""
		self._bind()
		_VOL.clear()
		_RUN.clear()
		_VOL_T.clear()

	def load_calibration(self, refresh=True):
		self._bind()
		return load_calibration(self.pumpset, refresh=refresh)

	def volumes(self):
		return dict(_VOL)

	def runtimes(self):
		return dict(_RUN)

	def calibrated(self):
		return sorted(_CALIB_CACHE)

	## -- rendering -----------------------------------------------------------
	def frame(self, t0):
		self._bind()
		return _frame(t0)

	def status(self):
		self._bind()
		return status()

	def live(self, fps=12, duration_s=None):
		"""Blocking live view. Ctrl-C returns."""
		from rich.live import Live
		self._bind()
		t0 = time.time()
		try:
			with Live(self.frame(t0), refresh_per_second=fps) as live:
				while True:
					time.sleep(1.0 / fps)
					live.update(self.frame(t0))
					if duration_s is not None and time.time() - t0 > duration_s:
						break
		except KeyboardInterrupt:
			print("[yellow]Live view stopped.[/] "
					"(the display only -- the pumps keep running)")
