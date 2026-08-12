"""Reading the RGB keypad, and mirroring pump state back onto its LEDs.

The keypad is one Pico, the pumps are another, and the host is the only thing
that can see both -- so the host closes the loop. Two directions:

    keypad -> host    lines() drained each poll, applied to the pumps
    host -> keypad    sync() pushes pump state onto the LEDs, QUIETLY, so a
                      mirror cannot bounce back as a fresh command

The read path probes for the best method the keypad firmware offers, because
what survives the raw REPL depends on it: lines() returns plain strings and is
fine, drain() returns Command objects whose reprs have to be salvaged, and a
keypad with neither can still be polled by diffing snapshot_lines().
"""

import logging as log
import time

from hive.assembly import ScopeAssembly


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


def kp(name="kp"):
	"""The keypad device. Raises AttributeError if it is not mounted.

	Resolved fresh every call, never cached, so a reconnect or a re-mount is
	picked up without restarting anything.
	"""
	return getattr(ScopeAssembly.current, name)


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


def _read_keypad_for(device):
	"""Return a list of wire lines pending on the keypad. Never raises."""
	global _READ_METHOD

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




class KeypadLink:
	"""Both directions of the keypad conversation, with its read strategy."""

	def __init__(self, name="kp"):
		self.name = name
		self.read_method = None
		self.last_snapshot = {}

	def device(self):
		return kp(self.name)

	def available(self):
		try:
			self.device()
			return True
		except AttributeError:
			return False

	## -- keypad -> host ------------------------------------------------------
	def lines(self):
		"""Wire lines pending on the keypad. Never raises."""
		global _READ_METHOD, _LAST_SNAPSHOT
		_READ_METHOD = self.read_method
		_LAST_SNAPSHOT = self.last_snapshot
		try:
			out = _read_keypad_for(self.device())
		finally:
			self.read_method = _READ_METHOD
			self.last_snapshot = _LAST_SNAPSHOT
		return out

	def snapshot_lines(self):
		try:
			return self.device().snapshot_lines() or []
		except Exception as err:
			log.error("keypad snapshot unavailable: %s", err)
			return []

	## -- host -> keypad ------------------------------------------------------
	def sync(self, states):
		"""Reflect pump state onto the LEDs. Quiet: emits no commands."""
		if not states:
			return []
		device = self.device()
		try:
			return device.sync(states)
		except AttributeError:
			pass
		except Exception as err:
			log.error("keypad mirror failed: %s", err)
			return []
		## older keypad firmware: fall back to wire lines
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
			device.apply_lines(lines)
			return sorted(states)
		except AttributeError:
			log.error("keypad has no sync()/apply_lines() -- cannot mirror")
			return []

	def stop_all(self):
		try:
			return self.device().stop_all()
		except Exception:
			return None
