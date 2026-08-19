"""One owner for the serial link: a bounded port, one lock, honest health.

Revised 15 Aug 2026 against 22 recorded runs in ~/Downloads/pumps. The records
overturned the first diagnosis, so read this before changing anything here.

WHAT THE RECORDS SHOW

  * Not one ERROR record in any logs.yaml, across every run, including the 24 h
    run on 12 Aug that froze and then sat untouched for 22 hours. The old
    handlers (`_frame`, `poll_once`, `_link_error`) all call log.error on
    exception, and that logger writes INFO and above into logs.yaml. Zero
    records means the board call never RAISED. It BLOCKED.

  * The earliest documented freeze -- "first round dinished. UI seems to have
    been crashing", 11 Aug, 153.8 min in -- happened on a script version that
    contains NO relink code at all. AUTO_RELINK first appears on 12 Aug. So the
    relink storm cannot be the origin; it was an amplifier added later.

  * poll_period_s = 0.05 in every single run. 20 Hz on the keypad, plus the
    12 fps frame, plus the mirror -- on a Raspberry Pi.

So the freeze is a read that never returns, in a process that is otherwise
healthy. Nothing raises, nothing is logged, nothing recovers, and no amount of
exception handling downstream can help.

WHAT THIS CLASS DOES ABOUT IT

  1. `arm_serial_timeout()` puts a hard read AND write timeout on the port at
     connect time and leaves it there. pyserial defaults to blocking forever and
     nothing in this stack ever set it. This is the fix; everything else is
     instrumentation around it.
  2. `call()` acquires the lock with a TIMEOUT. If another thread is stuck in a
     board call anyway, the render loop gives up, draws the last good frame, and
     says "LINK BLOCKED -- in flight 47s" instead of joining the queue. A
     supervisor that blocks holding its own lock is worse than no supervisor.
  3. One lock for all board access. Two threads interleaving on one raw REPL is
     what desynchronises it -- and the old script's orphaned scheduler jobs did
     exactly that, which is why onset was random rather than at a fixed time.
  4. Recovery is bounded: backoff, MAX_REPAIR_ATTEMPTS, then a terminal DOWN
     state that stops touching the port. A retry loop with no give-up state is a
     hang with extra steps.

Usage:

	sup = LinkSupervisor(RemotePumpSet())
	sup.start()                       # arms the port timeout AND the repair thread
	st = sup.state()                  # {} while the link is down; never raises
	sup.command("PUMP 1 POWER ON")    # through the lock; False if down or blocked
	sup.health()                      # what to render in the status bar
	sup.blocked_s()                   # >0 and climbing = a read is not coming back
	sup.stop()
"""

import logging as log
import threading
import time
from collections import deque

## Recovery policy ------------------------------------------------------------
FAILS_BEFORE_REPAIR = 3      # consecutive failures before the repair thread wakes
MAX_REPAIR_ATTEMPTS = 5      # then DOWN, and we stop touching the port
BACKOFF_S = (1.0, 2.0, 5.0, 10.0, 30.0)
SERIAL_TIMEOUT_S = 5.0       # hard cap on ANY blocking read on this port
SERIAL_WRITE_TIMEOUT_S = 5.0 # ditto for writes -- a full CDC buffer blocks too
LOCK_WAIT_S = 2.0            # how long a caller waits for the lock before
                             # giving up. Bounds the render loop even if the
                             # port timeout could not be armed.
INCIDENTS_MAX = 200          # bounded; the old list was unbounded AND copied
							 # wholesale into exp.logs on every append -- O(n^2)

UP, REPAIRING, DOWN = "up", "repairing", "down"


class LinkSupervisor:
	"""Serialises access to the pump board and owns its recovery."""

	def __init__(self, pumpset, name="pumpset", on_incident=None):
		self._ps = pumpset
		self._name = name
		self._on_incident = on_incident       # fn(dict) -- e.g. append to exp.logs
		self._lock = threading.RLock()

		self._status = UP
		self._fails = 0
		self._attempts = 0
		self._incidents = deque(maxlen=INCIDENTS_MAX)
		self._last_error = ""
		self._last_state = {}
		self._last_state_t = 0.0
		self._calls = 0
		self._inflight = None          # (what, started_monotonic) while in a call
		self._blocked_calls = 0

		self._wake = threading.Event()
		self._stop = threading.Event()
		self._thread = None

	# ---------------------------------------------------------------- lifecycle
	def start(self):
		"""Arm the port timeout and the repair thread. Idempotent."""
		self.arm_serial_timeout()
		if self._thread is not None and self._thread.is_alive():
			return self
		self._stop.clear()
		self._thread = threading.Thread(target=self._repair_loop,
										name="pump-link-repair", daemon=True)
		self._thread.start()
		return self

	def arm_serial_timeout(self, read_s=None, write_s=None):
		"""Put a hard read/write timeout on the port, for the whole session.

		THIS IS THE ONE THAT MATTERS, and the experiment records are why.

		Across 22 recorded runs, logs.yaml contains not a single ERROR record --
		no "pumpset.state() failed", no "poll_once failed" -- including the
		24 h run on 12 Aug that froze and sat there for 22 hours before Yatharth
		reconnected. Those handlers log on exception. Zero records means the
		board call never RAISED. It BLOCKED, inside a serial read, and the
		process sat in a syscall until it was killed.

		Everything downstream of an exception is therefore irrelevant to the
		original freeze -- and that includes the rest of this class. If the read
		blocks forever, call() blocks forever, and it does so HOLDING THE LOCK,
		which is strictly worse than the code it replaced.

		A blocked read cannot be interrupted from another thread. The only place
		it can be bounded is the port itself, before anything reads from it.
		pyserial's default is timeout=None, i.e. block forever; nothing in this
		stack ever set it.
		"""
		if read_s is None:
			read_s = SERIAL_TIMEOUT_S
		if write_s is None:
			write_s = SERIAL_WRITE_TIMEOUT_S
		from .remote import pump_device
		dev = pump_device(self._name)
		ser = getattr(getattr(dev, "device", None), "serial", None)
		if ser is None:
			log.warning("%s: no serial port to arm -- reads are UNBOUNDED", self._name)
			return False
		try:
			ser.timeout = read_s
			ser.write_timeout = write_s
			log.info("%s: serial read timeout %.1fs, write timeout %.1fs",
						self._name, read_s, write_s)
			return True
		except Exception as err:
			log.error("%s: could not set serial timeouts: %s -- reads are "
						"UNBOUNDED and a stalled board will hang the host",
						self._name, err)
			return False

	def stop(self, timeout=2.0):
		"""Ask the repair thread to finish and wait a bounded time for it."""
		self._stop.set()
		self._wake.set()
		t = self._thread
		if t is not None and t.is_alive():
			t.join(timeout)               # bounded: never join() forever
		self._thread = None
		return True

	def alive(self):
		"""False if the repair thread died. Callers should surface this."""
		t = self._thread
		return t is not None and t.is_alive()

	def resume(self):
		"""Leave the terminal DOWN state and try again. Explicit, by hand.

		Deliberately does NOT wait on the lock: resume() exists for the case
		where the link is unwell, which is exactly when the lock may be held by
		a call that has not come back. These three assignments are atomic enough.
		"""
		self._attempts = 0
		self._fails = 0
		self._status = REPAIRING
		self._wake.set()
		return True

	# ---------------------------------------------------------------- calling
	def call(self, what, fn, *args, **kw):
		"""Run one board call under the lock. Never raises, never relinks.

		Returns (ok, result). A failure is counted and, past the threshold,
		wakes the repair thread -- it does NOT repair here, because "here" is
		whatever thread is rendering.
		"""
		if self._status == DOWN:
			return (False, None)

		## Bounded lock acquisition. If another thread is stuck in a board call
		## -- which the experiment records show is the actual failure, a read
		## that blocks rather than raising -- the render loop must NOT queue up
		## behind it. It gives up, draws the last good frame, and says so.
		if not self._lock.acquire(timeout=LOCK_WAIT_S):
			self._blocked(what)
			return (False, None)
		try:
			self._calls += 1
			self._inflight = (what, time.monotonic())
			out = fn(*args, **kw)
		except Exception as err:
			self._fail(what, err)
			return (False, None)
		finally:
			self._inflight = None
			self._lock.release()

		if self._fails:
			self._recovered()
		return (True, out)

	def blocked_s(self):
		"""Seconds the current board call has been in flight, or 0.

		Non-zero and climbing means a read is not coming back. That is the
		signature of the original freeze, and it is now visible instead of
		simply stopping the process.
		"""
		inflight = self._inflight
		if not inflight:
			return 0.0
		return time.monotonic() - inflight[1]

	def command(self, line):
		"""Send one wire line to the pumps. True if it went out."""
		ok, _ = self.call("command", self._ps.command, str(line))
		return ok

	def commands(self, lines):
		sent = 0
		for line in (lines or []):
			if not self.command(line):
				break
			sent += 1
		return sent

	def state(self, max_age_s=None):
		"""Pump state, or the last good one if the link is unwell.

		Returns {} rather than raising, so a render loop can always draw
		something. ``fresh()`` tells you whether to trust it.
		"""
		ok, st = self.call("state", self._ps.state)
		if ok and st:
			self._last_state = st
			self._last_state_t = time.monotonic()
			return st
		if max_age_s is not None and self.age() > max_age_s:
			return {}
		return self._last_state

	def age(self):
		"""Seconds since the last successful state read."""
		if not self._last_state_t:
			return float("inf")
		return time.monotonic() - self._last_state_t

	def fresh(self, max_age_s=3.0):
		return self.age() <= max_age_s

	def stop_all(self):
		ok, _ = self.call("stop_all", self._ps.stop_all)
		return ok

	# ---------------------------------------------------------------- health
	def status(self):
		return self._status

	def health(self):
		"""Everything the status bar needs, in one cheap non-blocking call."""
		return {"status": self._status,
				"fails": self._fails,
				"attempts": self._attempts,
				"incidents": len(self._incidents),
				"last_error": self._last_error,
				"age_s": round(self.age(), 1) if self._last_state_t else None,
				"calls": self._calls,
				"blocked_s": round(self.blocked_s(), 1),
				"blocked_calls": self._blocked_calls,
				"repair_thread": self.alive()}

	def incidents(self, n=None):
		"""Bounded incident history, oldest first."""
		out = list(self._incidents)
		return out if n is None else out[-n:]

	def summary(self):
		h = self.health()
		if h["blocked_s"] > LOCK_WAIT_S:
			return ("LINK BLOCKED -- a board call has been in flight {:.0f}s and "
					"has not returned. {}".format(h["blocked_s"], h["last_error"]))
		if h["status"] == UP:
			return "link ok ({} calls)".format(h["calls"])
		if h["status"] == REPAIRING:
			return "LINK REPAIRING (attempt {}/{}) -- {}".format(
					h["attempts"], MAX_REPAIR_ATTEMPTS, h["last_error"])
		return "LINK DOWN after {} attempts -- {} -- call resume() or hard_reset()".format(
				h["attempts"], h["last_error"])

	# ---------------------------------------------------------------- internals
	def _fail(self, what, err):
		self._fails += 1
		self._last_error = "{}: {}".format(type(err).__name__, err)
		log.error("%s %s failed: %s", self._name, what, err)
		self._record(what, str(err), recovered=False)
		if self._fails >= FAILS_BEFORE_REPAIR and self._status == UP:
			self._status = REPAIRING
			self._wake.set()

	def _blocked(self, what):
		"""Could not get the lock: someone else's call has not come back."""
		self._blocked_calls += 1
		held = self._inflight
		self._last_error = "blocked: {} in flight {:.0f}s".format(
				held[0] if held else "?", self.blocked_s())
		log.error("%s %s skipped -- %s", self._name, what, self._last_error)
		if self._status == UP:
			self._status = REPAIRING
			self._wake.set()

	def _recovered(self):
		if self._status != UP or self._fails:
			self._record("link", "recovered", recovered=True)
		self._fails = 0
		self._attempts = 0
		self._status = UP

	def _record(self, where, error, recovered):
		inc = {"t": time.time(), "where": where, "error": error[:200],
			   "recovered": recovered}
		self._incidents.append(inc)          # bounded deque, no copy, no O(n^2)
		if self._on_incident is not None:
			try:
				self._on_incident(inc)
			except Exception:
				pass                        # bookkeeping must never break the link

	def _repair_loop(self):
		"""Dedicated thread. The only place that is allowed to block on serial."""
		while not self._stop.is_set():
			self._wake.wait(1.0)
			self._wake.clear()
			if self._stop.is_set():
				return
			if self._status != REPAIRING:
				continue

			if self._attempts >= MAX_REPAIR_ATTEMPTS:
				self._status = DOWN
				log.error("%s link DOWN after %d repair attempts",
						  self._name, self._attempts)
				self._record("repair", "gave up after {} attempts".format(
						self._attempts), recovered=False)
				continue

			delay = BACKOFF_S[min(self._attempts, len(BACKOFF_S) - 1)]
			self._attempts += 1
			if self._stop.wait(delay):      # interruptible sleep
				return

			if self._repair_once():
				self._recovered()
			else:
				self._wake.set()            # go round again, backed off further

	def _repair_once(self):
		"""Drain, re-enter the raw REPL, verify. Bounded by SERIAL_TIMEOUT_S."""
		from .remote import pump_device, link_check
		dev = pump_device(self._name)
		if dev is None:
			self._last_error = "no device mounted"
			return False
		try:
			with self._lock:
				ser = dev.device.serial
				## The old code never set this. pyserial defaults can be None,
				## which makes read() block forever -- and that is the actual
				## freeze, as opposed to the slowness around it.
				previous_timeout = getattr(ser, "timeout", None)
				try:
					ser.timeout = SERIAL_TIMEOUT_S
					waiting = ser.inWaiting()
					if waiting:
						junk = ser.read(waiting)
						log.info("drained %d stale bytes: %r", waiting, junk[:60])
					dev.device.exit_raw_repl()
					time.sleep(0.2)
					dev.device.enter_raw_repl()
				finally:
					try:
						ser.timeout = previous_timeout
					except Exception:
						pass
				return bool(link_check(self._name, verbose=False))
		except Exception as err:
			self._last_error = "repair: {}: {}".format(type(err).__name__, err)
			log.error("relink attempt %d failed: %s", self._attempts, err)
			return False
