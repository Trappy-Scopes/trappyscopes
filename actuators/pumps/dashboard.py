"""The live view, the status table, and the volume integrator.

One dashboard, used by every pump script. It reads nothing but ``PumpSet.state()``
dicts, so it renders identically for real and simulated pumps.

Two things it does that are not obvious:

  * the SET speed is always shown, not just the live one. In pulse mode the live
    speed drops to zero between bursts; the number you tuned is the one you want
    on screen, so the bar empties but a caret marks where it will run.

  * volume is integrated HERE, from the stored calibration, because the firmware
    does not track it -- state() has no volume_ml. With no calibration it falls
    back to run time, which needs none and is exactly what you need to
    reconstruct the volume once a calibration exists.

And one thing it deliberately does NOT do: touch the serial link. ``frame()``
and ``table()`` take a states dict and return a renderable. The previous version
fetched ``PUMPSET.state()`` inside ``_frame()`` and called an ``ON_LINK_ERROR``
hook on failure -- which the control script pointed at ``relink()``, so a blocking
serial reconnect ran inside the render function of a rich Live view. That was the
freeze. Rendering is now pure.
"""

import logging as log
import time

from hive.assembly import ScopeAssembly


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


def setpoint(st):
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


def _bar(speed, full_scale, slow_min, slow_max, width=16, mark_at=None):
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
	mark = int(round((mark_at or 0.0) / full_scale * width))
	for i in range(width):
		pos = (i + 0.5) / width * full_scale
		if mark_at and i == min(width - 1, max(0, mark - 1)) and pos > speed:
			t.append("│", style="bright_white")      ## set-speed caret
		elif pos <= speed:
			t.append("━", style=style)
		elif slow_min <= pos <= slow_max:
			t.append("┄", style="grey42")            ## the adjustable band
		else:
			t.append("━", style="grey27")
	return t


class Dashboard:
	"""Live view + status table + integrators for one pump set.

	    board = Dashboard(pumpset, roles={1: "perfusion", 3: "aeration"})
	    board.load_calibration()
	    board.frame(states, t0)      # a renderable; caller owns the Live
	    board.table(states)
	"""

	def __init__(self, pumpset, roles=None, simulated=False):
		self.pumpset = pumpset
		self.roles = dict(roles or {})
		self.simulated = simulated
		## pump -> ml delivered / seconds turning / last sample time / calibration.
		## All keyed by pump number, so at most len(numbers) entries -- these are
		## caches, not logs, and they do not grow.
		self._vol = {}
		self._run = {}
		self._t = {}
		self._calib = {}

	def role(self, n):
		return self.roles.get(n, "perfusion")

	def is_aeration(self, n):
		return self.role(n) == "aeration"

	## ---------------------------------------------------------------- volume
	def load_calibration(self, refresh=True):
		"""Cache each pump's stored calibration so the frame loop does no IO."""
		if self._calib and not refresh:
			return self._calib
		out = {}
		scope = ScopeAssembly.current
		for n in (self.pumpset.numbers() if self.pumpset is not None else ()):
			proxy = getattr(scope, "pump{}".format(n), None)
			params = getattr(proxy, "params", None)
			if params is None:
				continue
			try:
				state = params.__getstate__()
			except Exception as err:
				log.debug("no params for pump%s: %s", n, err)
				continue
			out[n] = dict((k, v) for k, v in state.items() if k.startswith("calib"))
		self._calib = out
		return out

	def calibrated(self):
		return sorted(self._calib)

	def rate_ml_min(self, n, st):
		"""Instantaneous delivery rate implied by the calibration, or None.

		fast mode  -- scale the measured prime rate by speed / calib_fast_speed
		pulse mode -- a burst delivers (a*speed + b) ml over on_s seconds, so
		              while the burst runs the rate is that over on_s
		"""
		calib = self._calib.get(n)
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

	def accrue(self, states):
		"""Integrate delivered volume and run time. Called once per frame.

		Stale states (the link is down and the caller is re-rendering the last
		good snapshot) are NOT integrated: the sample gap is reset instead, so a
		ten-minute outage does not appear as ten minutes of delivery.
		"""
		now = time.monotonic()
		for n, st in (states or {}).items():
			last = self._t.get(n)
			self._t[n] = now
			if last is None:
				continue
			dt = now - last
			if dt > 5.0:            ## a gap this long means we were not looking
				continue
			## Run time is measurable without any calibration at all -- it only
			## needs to know whether the pump is turning. It is what the volume
			## column falls back to, so an uncalibrated rig still shows something
			## true and useful rather than a dash.
			if float(st.get("speed") or 0.0) > 0:
				self._run[n] = self._run.get(n, 0.0) + dt
			rate = self.rate_ml_min(n, st)
			if rate:
				self._vol[n] = self._vol.get(n, 0.0) + rate * dt / 60.0

	def volumes(self):
		"""Delivered volume per pump since the last reset, in ml."""
		return dict(self._vol)

	def runtimes(self):
		"""Seconds each pump has actually been turning since the last reset.

		Always available -- no calibration needed. Multiply by a rate later and
		an uncalibrated run is still recoverable.
		"""
		return dict(self._run)

	def reset_volumes(self):
		"""Zero the integrators -- call it when you swap the reservoir."""
		self._vol.clear()
		self._run.clear()
		self._t.clear()
		return True

	## ---------------------------------------------------------------- render
	def frame(self, states, t0, banner=None):
		"""One frame of the live view. Pure: states in, renderable out."""
		from rich.table import Table
		from rich.text import Text
		from rich.console import Group
		from rich.panel import Panel

		elapsed = time.monotonic() - t0
		states = states if isinstance(states, dict) else {}
		self.accrue(states)

		grid = Table.grid(padding=(0, 1))
		for _ in range(10):
			grid.add_column()
		head = lambda s: Text(s, style="grey50")
		grid.add_row(head("pump"), head(""), head("mode"),
						head("speed bar  │=set"), head("now"), head("set"),
						head("band"), head("fast"), head("flow"), head("volume"))

		total_ml = 0.0
		has_volume = False
		for n in sorted(states):
			st = states[n] or {}
			frac = float(st.get("speed", 0.0))
			mode = st.get("mode", "idle")

			rotor = (Text(ROTOR[int(elapsed * frac * 24) % len(ROTOR)],
							style=_flow_style(frac)) if frac > 0
						else Text("o", style="grey30"))

			if mode == "fast":
				mode_txt = Text("FAST", style="bold green")
			elif mode == "slow":
				mode_txt = Text("slow", style="bright_cyan")     ## continuous
			elif mode == "pulse":
				mode_txt = Text("pulse {}".format(st.get("phase", "")), style="cyan")
			else:
				mode_txt = Text("idle", style="grey30")

			if self.is_aeration(n):
				## No volumetric meaning for the aeration line -- say so instead
				## of printing a millilitre figure nobody should trust.
				vol = Text("  aeration ", style="grey50")
			elif "volume_ml" in st:
				has_volume = True
				total_ml += float(st["volume_ml"])
				vol = Text("{:>7.2f} ml".format(st["volume_ml"]),
							style="white" if frac else "grey50")
			elif n in self._calib:
				ml = self._vol.get(n, 0.0)
				has_volume = True
				total_ml += ml
				vol = Text("{:>7.2f} ml".format(ml),
							style="white" if frac else "grey50")
			else:
				secs = self._run.get(n, 0.0)
				vol = Text("{:>6.0f} s run".format(secs),
							style="grey58" if secs else "grey30")

			## Everything below is an absolute PWM unit speed (0.0-1.0), not a
			## percentage of the band -- percentages hid how slow "slow" really is.
			lo, hi = st.get("slow_limits", (0.0, 1.0))
			fast_speed = st.get("fast_speed", 1.0)
			full_scale = max(fast_speed, hi) or 1.0
			point = setpoint(st)

			grid.add_row(
				Text(str(st.get("name", n)), style="bold" if frac > 0 else "grey50"),
				rotor,
				mode_txt,
				_bar(frac, full_scale, lo, hi, mark_at=point),
				Text("{:>5.3f}".format(frac),
						style=_flow_style(frac / full_scale) if frac else "grey30"),
				Text("{:>5.3f}".format(point), style="white" if point else "grey30"),
				Text("{:.2f}-{:.2f}".format(lo, hi), style="grey42"),
				Text("f{:.2f}".format(fast_speed), style="grey42"),
				_tube(frac, st.get("dir", 1), elapsed * frac * 34),
				vol,
			)

		footer = Text.assemble(
			("elapsed ", "grey50"), ("{:>6.1f}s".format(elapsed), "white"),
			("   total ", "grey50"),
			("{:.2f} ml".format(total_ml) if has_volume else "n/a", "bright_white"),
			("   ", "grey50"),
			("simulated" if self.simulated else "REAL PUMPS",
				"grey50" if self.simulated else "bold yellow"),
			("   ctrl-c to stop", "grey50"))

		parts = [grid, Text("")]
		if banner:
			style = "grey50" if banner.startswith("link ok") else "bold red"
			parts.append(Text(banner, style=style))
		parts.append(footer)
		return Panel(Group(*parts),
						title="[bold]pumps[/bold] -- live (absolute PWM unit speed)",
						border_style="grey37")

	def table(self, states):
		"""One-shot status table. Pure: states in, renderable out."""
		from rich.table import Table
		table = Table(title="pumps ({})".format(
				"simulated" if self.simulated else "real hardware"))
		for col in ("n", "name", "role", "mode", "now", "set", "band", "fast",
					"duty", "cont", "lvl%", "vol ml"):
			table.add_column(col)
		for n, st in sorted((states or {}).items()):
			st = st or {}
			mode = st.get("mode", "?")
			style = {"fast": "[green]fast[/green]",
						"slow": "[bright_cyan]slow[/bright_cyan]",
						"pulse": "[cyan]pulse[/cyan]"}.get(mode, "[dim]idle[/dim]")
			lo, hi = st.get("slow_limits", (0.0, 0.0))
			if self.is_aeration(n):
				vol = "[dim]n/a[/dim]"
			elif "volume_ml" in st:
				vol = "{:.3f}".format(st["volume_ml"])
			elif n in self._calib:
				## a calibrated pump that has not moved yet is 0.000, not
				## "no calib" -- only an uncalibrated one cannot be counted
				vol = "{:.3f}".format(self._vol.get(n, 0.0))
			else:
				vol = "[dim]{:.0f}s run[/dim]".format(self._run.get(n, 0.0))
			table.add_row(
				str(n), str(st.get("name", "")),
				"[cyan]aeration[/cyan]" if self.is_aeration(n)
					else "[dim]perfusion[/dim]",
				style,
				"{:.3f}".format(st.get("speed", 0.0)),
				"{:.3f}".format(setpoint(st)),
				"{:.2f}-{:.2f}".format(lo, hi),
				"{:.2f}".format(st.get("fast_speed", 0.0)),
				"[dim]n/a[/dim]" if st.get("continuous")
					else "{}s/{}s".format(*st.get("pulse_duty", ("-", "-"))),
				"[bright_cyan]yes[/bright_cyan]" if st.get("continuous")
					else "[dim]no[/dim]",
				str(st.get("percent", "-")),
				vol,
			)
		return table


# ============================================================ WHAT CHANGED
# 538 lines -> 389, and the module-level fork of every method is gone -- there
# was a full procedural copy (PUMPSET/_VOL/_RUN globals, _frame, status,
# _states_or_warn, animate, _sync_dir) sitting under a Dashboard class that
# rebound those globals on every call via _bind().
#
# * frame()/table() no longer fetch state() or call ON_LINK_ERROR. Rendering
#   used to reach the serial link, and the control script pointed the hook at
#   relink() -- a blocking serial reconnect inside a rich Live render function.
#   The caller now passes states in and owns the link.
# * ON_LINK_ERROR / ON_LINK_OK / _link_error / _link_ok: removed with it.
# * _sync_dir() referenced a global `exp` that this module never defines or
#   imports -- it raised NameError on first call. Removed; the control script
#   does its own saving.
# * animate() and Dashboard.live(): two more copies of the same Live loop, both
#   with refresh_per_second AND an explicit update() (double render per frame).
#   The control script owns the one loop now.
# * accrue() skips samples more than 5 s apart, so an outage is no longer
#   integrated as delivery. It also uses time.monotonic(), not time.time() --
#   an NTP step used to move the volume.
# * Dead: `left = st.get("seconds_left")` (assigned, never used),
#   _setpoint_default(), the module-level role()/is_aeration() shadows.
