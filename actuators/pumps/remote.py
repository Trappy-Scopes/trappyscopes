"""The pumps as they appear from the host: a PumpSet over the raw REPL.

The board owns the pumps. This is only a facade -- every call is one serial
round trip to scope.pumpset, and the method names match
pico_firmware.actuators.peristaltic.PumpSet exactly, so host code cannot tell a
real pump from a simulated one.

Also here: the health of that serial link, because it is the part that breaks.
pyboard.exec_raw() waits 10 s, reads until \\x04 and expects a clean ">" prompt.
Two things desynchronise it and neither heals on its own:

    a board-side call that blocks longer than 10 s -- the host gives up, the
    board answers late, and every later call reads the previous reply

    unsolicited output from the board -- a print() in a timer callback, or a
    traceback from a soft IRQ

link_check() detects it, relink() clears it without disturbing the pumps, and
hard_reset() is the bigger hammer for a board that has actually hung.
"""

import logging as log
import time

from hive.assembly import ScopeAssembly


class RemotePumpSet:
	"""PumpSet-shaped facade over the firmware's own pumpset."""

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

	## -- the PumpSet surface -------------------------------------------------
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


## ---------------------------------------------------------------- the link
def pump_device(name="pumpset"):
	"""The SerialMPDevice behind the pumps, not the proxy."""
	proxy = getattr(ScopeAssembly.current, name, None)
	return getattr(proxy, "device", None)


def link_check(name="pumpset", verbose=True):
	"""Ask something whose answer is known, and check we get it back."""
	dev = pump_device(name)
	try:
		echo = dev("1+1") if dev else None
	except Exception as err:
		if verbose:
			print("[red]{} link broken:[/] {}".format(name, err))
		return False
	if echo != 2:
		if verbose:
			print("[red]{} link desynchronised[/] -- asked 1+1, got {!r}".format(
					name, echo))
		return False
	if verbose:
		print("[green]{} link ok.[/]".format(name))
	return True


def relink(name="pumpset", verbose=True):
	"""Clear a desynchronised raw REPL without disturbing the board.

	Drains the stale bytes, re-enters the raw REPL, re-checks. The pumps keep
	running throughout -- the board does not stop because the host lost track.
	"""
	dev = pump_device(name)
	if dev is None:
		print("[red]No {} device to relink.[/]".format(name))
		return False
	try:
		ser = dev.device.serial
		waiting = ser.inWaiting()
		if waiting:
			junk = ser.read(waiting)
			if verbose:
				print("[dim]drained {} stale bytes: {!r}[/dim]".format(
						waiting, junk[:60]))
		dev.device.exit_raw_repl()
		time.sleep(0.2)
		## soft_reset=False. enter_raw_repl() defaults to sending Ctrl-D, and on
		## this stack a soft reset re-runs main.py, which execfile()s the circuit
		## -- so the default turns "resynchronise the link" into "reboot the pump
		## board mid-experiment". The pumps must not stop because the host lost
		## its place in the byte stream. hard_reset() is the deliberate escalation
		## when the board has genuinely hung.
		dev.device.enter_raw_repl(soft_reset=False)
	except Exception as err:
		log.error("relink failed: %s", err)
		print("[red]Relink failed:[/] {} -- reconnect the device.".format(err))
		return False
	return link_check(name, verbose=verbose)


def hard_reset(name="pumpset", wait_s=3.0, verbose=True):
	"""Reboot the board, then reconnect to it.

	The honest way to start a session: the interpreter comes up clean, with no
	leftover timers or half-built objects from whatever the previous host was
	doing, and the circuit restores the pumps from pumpstate.txt on the way up.

	The pumps DO stop for the couple of seconds the board takes to boot. That is
	the cost, and for a 5 s / 55 s perfusion duty it is not a meaningful one.
	"""
	dev = pump_device(name)
	if dev is None:
		print("[red]No {} device to reset.[/]".format(name))
		return False
	try:
		## exec_raw_no_follow: the board vanishes mid-command by design, so
		## there is no reply to wait for.
		dev.device.exec_raw_no_follow("import machine\nmachine.reset()")
	except Exception as err:
		log.debug("reset command returned %s (expected)", err)

	if verbose:
		print("[yellow]Board reset.[/] Waiting {:.0f}s for it to come back...".format(
				wait_s))
	time.sleep(wait_s)

	try:
		dev.device.serial.close()
	except Exception:
		pass
	try:
		dev.connect(dev.port)
		dev.device.enter_raw_repl()
	except Exception as err:
		print("[red]Could not reconnect after reset:[/] {}".format(err))
		print("  [dim]The port name can change across a reset -- "
				"re-mount the device.[/dim]")
		return False

	ok = link_check(name, verbose=verbose)
	if ok and verbose:
		print("[green]Board back up.[/] Pumps resume from pumpstate.txt.")
	return ok
