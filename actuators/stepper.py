"""AI Generated -- a generic stepper axis whose position is counted on the host.

Written by Claude (Anthropic), 2026-10, for the Poseidon syringe pumps, but
nothing here knows about syringes or Arduinos. Any stepper whose controller
gives no position feedback can subclass StepperAxis and implement two hooks:

	_drive(steps)  start a relative move; return (eta_s, progress) where
	               progress(elapsed_s) -> steps done so far, or None
	_halt()        stop the motor now

The host is the only source of truth for position, so it is persisted:
MotorState is a persistent PhysicalObject (a shelve under
~/trappyverse/state/), synced after every change. A move marks the shelf
`moving` before it starts; if the program dies before the move is booked as
finished, the next load finds `moving` still set and flags the position as
uncertain until it is re-zeroed or explicitly accepted.

Directions: positive steps are "forward". Limits are positions in steps; a
move that would cross one raises LimitError, a jog is clamped to it.
"""

import logging as log
import threading
import time

from hive.physical import PhysicalObject


class LimitError(ValueError):
	"""The move would leave the travel range set with set_limit()."""


class BusyError(RuntimeError):
	"""The axis (or its controller) is still executing a move."""


class MotorState(PhysicalObject):
	"""Persistent bookkeeping for one axis. Never seeded from kwargs: what is
	on the shelf wins, and only missing keys get defaults."""

	DEFAULTS = {"position_steps": 0, "limit_lo": None, "limit_hi": None,
				"moving": False, "target_steps": None,
				"uncertain": False, "uncertain_reason": None}

	_open = {}		## name -> MotorState; a shelve cannot be opened twice

	@classmethod
	def get(cls, name, persistent=True):
		"""The open state for this name, opening it once per process."""
		existing = cls._open.get(name)
		if existing is not None and existing.persistent == persistent:
			return existing
		state = cls(name, persistent=persistent)
		cls._open[name] = state
		return state

	def __init__(self, name, persistent=True):
		self.state_name = name
		super().__init__(name, persistent=persistent, kind="actuators.stepper.MotorState")
		for key, value in self.DEFAULTS.items():
			if key not in self.attribs:
				self.attribs[key] = value
		if self.attribs["moving"]:
			self.attribs["moving"] = False
			self.attribs["uncertain"] = True
			self.attribs["uncertain_reason"] = (
				f"interrupted mid-move (was heading to {self.attribs['target_steps']})")
			log.warning(f"{name}: {self.attribs['uncertain_reason']} -- position uncertain.")
		self.sync()

	def sync(self):
		if self.persistent:
			self.attribs.sync()

	def close(self):
		if MotorState._open.get(self.state_name) is self:
			del MotorState._open[self.state_name]
		if self.persistent:
			self.attribs.sync()
			self.attribs.close()


class StepperAxis:
	"""One stepper, position counted on the host and remembered across sessions."""

	def __init__(self, name, persistent=True, steps_per_unit=None, unit="steps"):
		self.name = name
		self.persistent = persistent
		self.steps_per_unit = steps_per_unit
		self.unit = unit
		self.mstate = MotorState.get(name, persistent)
		self._move = None
		self._lock = threading.RLock()

	## -- hooks ----------------------------------------------------------------
	def _drive(self, steps):
		raise NotImplementedError

	def _halt(self):
		raise NotImplementedError

	## -- reading --------------------------------------------------------------
	def position(self):
		self.poll()
		return int(self.mstate["position_steps"])

	def position_units(self):
		if not self.steps_per_unit:
			return float(self.position())
		return self.position() / self.steps_per_unit

	def limits(self):
		return (self.mstate["limit_lo"], self.mstate["limit_hi"])

	def is_uncertain(self):
		return bool(self.mstate["uncertain"])

	def busy(self):
		self.poll()
		return self._move is not None

	def poll(self):
		"""Book a timed move as finished once its eta has passed."""
		with self._lock:
			m = self._move
			if m and m["paused_at"] is None and time.monotonic() >= m["eta"]:
				self._finish()

	def wait(self, timeout=None):
		"""Block until the current move is booked as finished; False on timeout."""
		t_end = None if timeout is None else time.monotonic() + timeout
		while self.busy():
			if t_end is not None and time.monotonic() >= t_end:
				return False
			with self._lock:
				m = self._move
				left = 0.05 if (m is None or m["paused_at"] is not None) \
					else max(0.0, m["eta"] - time.monotonic())
			time.sleep(min(0.05, left) or 0.001)
		return True

	def state(self):
		with self._lock:
			self.poll()
			m = self._move
			if m is None:
				activity = "idle"
			elif m["paused_at"] is not None:
				activity = "paused"
			else:
				activity = "moving"
			return {"name": self.name, "position_steps": self.position(),
					"position": self.position_units(), "unit": self.unit,
					"limits": self.limits(), "activity": activity,
					"eta_s": None if m is None or m["paused_at"] is not None
						else max(0.0, m["eta"] - time.monotonic()),
					"uncertain": self.is_uncertain(),
					"uncertain_reason": self.mstate["uncertain_reason"]}

	## -- limits and origin ----------------------------------------------------
	def check(self, target):
		lo, hi = self.limits()
		if lo is not None and target < lo:
			raise LimitError(f"{self.name}: target {target} is below the lower limit {lo}.")
		if hi is not None and target > hi:
			raise LimitError(f"{self.name}: target {target} is above the upper limit {hi}.")

	def clamp(self, target):
		lo, hi = self.limits()
		if lo is not None:
			target = max(target, lo)
		if hi is not None:
			target = min(target, hi)
		return target

	def set_limit(self, which, at=None):
		"""Save `at` (default: here) as the "lo" or "hi" end of travel."""
		if which not in ("lo", "hi"):
			raise ValueError("which must be 'lo' or 'hi'")
		self._ensure_idle()
		at = self.position() if at is None else int(at)
		lo, hi = self.limits()
		if which == "lo" and hi is not None and at > hi:
			raise LimitError(f"{self.name}: lower limit {at} would be above the upper limit {hi}.")
		if which == "hi" and lo is not None and at < lo:
			raise LimitError(f"{self.name}: upper limit {at} would be below the lower limit {lo}.")
		self.mstate[f"limit_{which}"] = at
		self.mstate.sync()
		return at

	def clear_limits(self):
		self.mstate["limit_lo"] = self.mstate["limit_hi"] = None
		self.mstate.sync()

	def zero(self):
		"""Make here position 0. Limits keep their physical place -- they are
		shifted with the origin -- unless the old position was uncertain, in
		which case they were relative to an unknown origin and are cleared."""
		self._ensure_idle()
		pos = self.position()
		lo, hi = self.limits()
		if self.is_uncertain():
			if lo is not None or hi is not None:
				log.warning(f"{self.name}: limits cleared -- they were set against an "
							"uncertain position.")
			lo = hi = None
		else:
			lo = None if lo is None else lo - pos
			hi = None if hi is None else hi - pos
		self.mstate["position_steps"] = 0
		self.mstate["limit_lo"], self.mstate["limit_hi"] = lo, hi
		self.mstate["uncertain"], self.mstate["uncertain_reason"] = False, None
		self.mstate.sync()

	def accept_position(self):
		"""Trust the current (estimated) position without re-zeroing."""
		self.mstate["uncertain"], self.mstate["uncertain_reason"] = False, None
		self.mstate.sync()

	## -- moving ---------------------------------------------------------------
	def move(self, steps, wait=False):
		"""Relative move. Raises LimitError before anything is sent."""
		steps = int(steps)
		self._ensure_idle()
		self.check(self.position() + steps)
		if steps == 0:
			return 0
		eta, progress = self._drive(steps)
		self._track(steps, eta, progress)
		if wait:
			self.wait()
		return steps

	def forward(self, steps, wait=False):
		return self.move(abs(int(steps)), wait=wait)

	def backward(self, steps, wait=False):
		return self.move(-abs(int(steps)), wait=wait)

	def move_to(self, target, wait=False):
		return self.move(int(target) - self.position(), wait=wait)

	def jog(self, steps, wait=False):
		"""Like move(), but clamped to the limits instead of refused; returns
		the steps actually commanded (0 at a limit)."""
		steps = int(steps)
		pos = self.position()
		steps = self.clamp(pos + steps) - pos
		return self.move(steps, wait=wait) if steps else 0

	def stop(self):
		with self._lock:
			if self._move is None:
				return
		self._halt()
		self._abort("stopped mid-move; position estimated from elapsed time")

	## -- bookkeeping (also used by controllers that move several axes at once)
	def _ensure_idle(self):
		if self.busy():
			raise BusyError(f"{self.name}: still moving.")

	def _track(self, steps, eta, progress=None):
		with self._lock:
			start = int(self.mstate["position_steps"])
			self._move = {"start": start, "steps": int(steps), "t0": time.monotonic(),
						  "eta": time.monotonic() + max(0.0, eta), "progress": progress,
						  "paused_at": None, "paused_s": 0.0}
			self.mstate["moving"] = True
			self.mstate["target_steps"] = start + int(steps)
			self.mstate.sync()
			if eta <= 0:
				self._finish()

	def _finish(self):
		with self._lock:
			m = self._move
			if m is None:
				return
			self.mstate["position_steps"] = m["start"] + m["steps"]
			self.mstate["moving"] = False
			self.mstate["target_steps"] = None
			self.mstate.sync()
			self._move = None

	def _abort(self, reason):
		with self._lock:
			m = self._move
			if m is None:
				return
			now = m["paused_at"] or time.monotonic()
			elapsed = now - m["t0"] - m["paused_s"]
			done = m["progress"](elapsed) if m["progress"] else None
			if done is None:
				done = 0
				reason += " (no progress model -- assumed no motion)"
			done = max(0, min(abs(m["steps"]), int(round(done))))
			sign = 1 if m["steps"] > 0 else -1
			self.mstate["position_steps"] = m["start"] + sign * done
			self.mstate["moving"] = False
			self.mstate["target_steps"] = None
			self.mstate["uncertain"], self.mstate["uncertain_reason"] = True, reason
			self.mstate.sync()
			self._move = None
			log.warning(f"{self.name}: {reason}.")

	def _pause(self):
		with self._lock:
			if self._move and self._move["paused_at"] is None:
				self._move["paused_at"] = time.monotonic()

	def _resume(self):
		with self._lock:
			m = self._move
			if m and m["paused_at"] is not None:
				dt = time.monotonic() - m["paused_at"]
				m["paused_s"] += dt
				m["eta"] += dt
				m["paused_at"] = None
