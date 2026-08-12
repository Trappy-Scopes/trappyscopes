"""Simulated pumps: the PeristalticPump API, host side, moving no fluid.

Kept deliberately in step with pico_firmware/actuators/peristaltic.py. Anything
the firmware exposes is here with the same name and the same semantics, so a
script written against one runs against the other unchanged. The extras --
flow_ml_min(), volume_ml(), runtime_s() -- are additive, and the dashboard
degrades gracefully when they are missing.
"""

import time


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


