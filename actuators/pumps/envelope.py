"""Pushing the speed envelope to the board, and reading it back.

The host is authoritative: the firmware constants in
``circuits/2ch_peristat_kitroniks_vx_shield.py`` are only defaults for a cold
boot with no host attached. Every connect() pushes this envelope over them.

Which means a wrong number here silently overrides a correctly flashed board --
and a preflight that compares the board against the same envelope it just pushed
will happily agree with itself. ``diff()`` exists to catch the other direction:
``Proxy.__getattr__`` manufactures an attribute for ANY name, so a board running
older firmware ACCEPTS a setter that does not exist and quietly keeps its own
value. Nothing raises. Reading back is the only way to know.

Push order matters: limits before speed, because ``set_slow_speed()`` clamps
into the *current* band.
"""

import logging as log

## Push order. (envelope key, firmware method, args-from-spec).
## A key with method None is consumed by a later row -- slow_min is pushed as
## part of set_slow_limits, not on its own.
PUSH_ORDER = (
	("continuous", "set_continuous", lambda s: (s["continuous"],)),
	("pulse_duty", "set_pulse_duty", lambda s: tuple(s["pulse_duty"])),
	("fast_speed", "set_fast_speed", lambda s: (s["fast_speed"],)),
	("slow_min",   None,             None),
	("slow_max",   "set_slow_limits", lambda s: (s["slow_min"], s["slow_max"])),
	("kick",       "set_kick",       lambda s: tuple(s["kick"])),
	("slow_speed", "set_slow_speed", lambda s: (s["slow_speed"],)),
)

KEYS = ("fast_speed", "slow_min", "slow_max", "slow_speed",
		"pulse_duty", "continuous", "kick")


def _num(value):
	"""Normalise for comparison. Whole floats become ints so mismatch messages
	read '(5, 55)' rather than '(5.0, 55.0)'. 5 == 5.0 either way, so this
	cannot change a verdict."""
	try:
		out = round(float(value), 4)
	except (TypeError, ValueError):
		return value
	return int(out) if out == int(out) else out


def _tup(value):
	if value is None:
		return None
	try:
		return tuple(_num(x) for x in value)
	except TypeError:
		return value


## Which fields the board reports back, and how to line them up with the spec.
READBACK = (
	("fast_speed",  lambda st: _num(st.get("fast_speed")),
					lambda sp: _num(sp.get("fast_speed"))),
	("slow_limits", lambda st: _tup(st.get("slow_limits")),
					lambda sp: _tup((sp.get("slow_min"), sp.get("slow_max")))),
	("pulse_duty",  lambda st: _tup(st.get("pulse_duty")),
					lambda sp: _tup(sp.get("pulse_duty"))),
	("continuous",  lambda st: st.get("continuous"),
					lambda sp: sp.get("continuous")),
	("kick",        lambda st: _tup(st.get("kick")),
					lambda sp: _tup(sp.get("kick"))),
)


def diff(envelope, states, numbers=None):
	"""{n: [(field, wanted, on_board), ...]} for everything that disagrees.

	{} means it all landed. None means the board could not be read. Fields the
	host does not set for a pump -- pump3 has no pulse_duty -- are skipped
	rather than reported as mismatches.
	"""
	if not isinstance(states, dict):
		return None
	out = {}
	for n in (numbers or sorted(envelope)):
		spec, st = envelope.get(n), states.get(n)
		if not spec or not isinstance(st, dict):
			continue
		rows = []
		for field, from_board, from_spec in READBACK:
			want = from_spec(spec)
			if want is None or (isinstance(want, tuple) and None in want):
				continue
			got = from_board(st)
			if got is None:
				rows.append((field, want, "not reported"))
			elif got != want:
				rows.append((field, want, got))
		if rows:
			out[n] = rows
	return out


def push(envelope, pumpset, supervisor, numbers=None, emit=print):
	"""Push the envelope through the supervisor's lock. Never raises.

	Returns (applied, missing) -- applied is {n: {key: result}}, missing is
	{n: [method, ...]} for calls the board did not take.
	"""
	applied, missing = {}, {}
	for n in (numbers or pumpset.numbers()):
		spec = envelope.get(n)
		if not spec:
			continue
		pump = pumpset[n]
		done, absent = {}, []
		for key, method, args in PUSH_ORDER:
			if method is None or key not in spec:
				continue
			ok, result = supervisor.call(
					"pump{}.{}".format(n, method), getattr(pump, method), *args(spec))
			if ok:
				done[key] = result
			else:
				absent.append(method)
		applied[n] = done
		if absent:
			missing[n] = absent
			emit("  [yellow]pump{}: board did not take {}[/] -- firmware may be "
				 "older than this script".format(n, ", ".join(absent)))
		else:
			emit("  pump{}: fast {} slow {}-{} @ {}{}".format(
					n, spec.get("fast_speed"), spec.get("slow_min"),
					spec.get("slow_max"), spec.get("slow_speed"),
					"  kick {}".format(spec["kick"])
					if spec.get("kick", (0,))[0] else ""))
	return applied, missing


def verify(envelope, states, numbers=None, emit=print):
	"""Read-back check. True if the board agrees, False if it does not,
	None if it could not be read."""
	rows = diff(envelope, states, numbers)
	if rows is None:
		emit("  [yellow]could not read the board back -- envelope UNVERIFIED[/]")
		return None
	if not rows:
		emit("  [green]verified against the board[/]")
		return True
	for n, fields in sorted(rows.items()):
		for field, want, got in fields:
			emit("  [red]pump{} {} did not take[/] -- asked {}, board has "
				 "{}".format(n, field, want, got))
	emit("  [dim]A field that will not take usually means the board is running "
		 "older firmware than this script. Reflash actuators/peristaltic.py + "
		 "the circuit file, then reset.[/dim]")
	log.error("envelope mismatch: %s", rows)
	return False


def update(envelope, n, **kwargs):
	"""Change one pump's envelope in place. Returns the new spec, or None."""
	unknown = [k for k in kwargs if k not in KEYS]
	if unknown:
		raise ValueError("unknown envelope keys: {}".format(unknown))
	spec = envelope.setdefault(n, {})
	spec.update(kwargs)
	return dict(spec)
