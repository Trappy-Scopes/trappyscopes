#!/usr/bin/env python3
# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : November 2026                                                  |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+

"""
AI Generated -- new file, Claude (Anthropic), 2026-11.

T&H sensor divergence. The scope's own T&H sensor and the four sensors of the
pico_temp_array board, read together at 1 Hz for 5 min: how far apart do
sensors read the same air?

	create_exp()    mounts pico_temp_array, test-reads every sensor
	start()         5 min at 1 Hz (blocks), then cleanup() straight away
	exp.close()

	test_read()     one reading of every sensor, any time
	mount_array()   (re)mount the board on its own: mount_array(remount=True)

Ctrl-C during start() stops early and keeps what was read. cleanup() runs
right after the acquisition however it ended (done, Ctrl-C, a hung Pico or an
error): it stops the schedule, saves and syncs. It does not close the
experiment; type exp.close() afterwards.

The seat
--------
A triangular seat. Three AHT20 boards stand on its edges as walls, sensor side
facing in: the triad. An MCP9808 lies flat in the middle.

	stream     sensor                 board              where
	tandh      AHT10/20, the scope's  the scope's Pico   triad wall, in tandh_3's place
	tandh_1    AHT20                  pico_temp_array    triad wall
	tandh_2    AHT20                  pico_temp_array    triad wall
	temp_mcp   MCP9808                pico_temp_array    centre, lying flat
	tandh_3    AHT20                  pico_temp_array    outside the seat, hanging free

The triad puts the scope's sensor next to two of its kind in the same air.
The MCP9808 is a different kind of sensor (temperature only, 0.0625 C steps)
at the centre of the triad, so every temperature is compared with it. tandh_3
reads the air outside the seat. All of this is in exp.attribs["sensor_layout"].

Streams
-------
One stream per sensor, all with the same fields, each like the scope's usual
tandh stream:

	monitors      tick      the 1 Hz slot, shared by all five streams
	              read_s    how long that board's read took
	measurements  temp      C
	              humidity  %RH (None for temp_mcp)

Rows with the same tick come from the same second: pair on tick. Rows are kept
in memory and written to the experiment once, at the end; one YAML save per
reading would be 1500 saves.

A failed read, a sensor missing from the reply, or a reading of exactly 0 (never
real) writes no row. Each is counted in the divergence_summary event.

Reading
-------
The two boards are read in parallel, one thread each, on the same 1 Hz grid.
A hung Pico then stops only its own sensors (a serial exec to a Pico has no
timeout). The AHT20 driver triggers three conversions per read(), so the
array's read of three AHT20s takes most of a second: read_s shows how long.
A slot that is more than one period late is skipped and counted.

Mounting
--------
pico_temp_array is found by its board name among the Picos on USB that the
scope has not already claimed. Its main.py runs, the board goes into the scope
tree as scope.pico_temp_array, and its objects become scope.sensorset,
scope.tandh_1 and so on. A name the scope already uses is never overwritten: it
is skipped with a warning.
"""

import logging as log
import math
import statistics
import threading
import time
from collections import Counter

from rich import print
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from hive.processorgroups.micropython import SerialMPDevice


__description__ = \
"""T&H sensor divergence: the scope's T&H sensor and pico_temp_array's four
sensors at 1 Hz for 5 min.

create_exp() mounts the board and test-reads it, start() runs, exp.close()
finishes.
"""

PROTOCOL = "tandh_divergence/1"
BOARD = "pico_temp_array"

## stream -> where it sits. The scope's sensor takes tandh_3's place in the
## triad; tandh_3 hangs outside the seat.
LAYOUT = {
	"tandh":    {"sensor": "AHT10/20", "board": "scope", "position": "triad",
				 "note": "the scope's own T&H sensor, in tandh_3's place"},
	"tandh_1":  {"sensor": "AHT20", "board": BOARD, "position": "triad"},
	"tandh_2":  {"sensor": "AHT20", "board": BOARD, "position": "triad"},
	"temp_mcp": {"sensor": "MCP9808", "board": BOARD, "position": "centre",
				 "note": "lies flat in the middle of the triad; temperature only"},
	"tandh_3":  {"sensor": "AHT20", "board": BOARD, "position": "outside",
				 "note": "hangs free outside the seat"},
}
STREAMS = tuple(LAYOUT)
ARRAY = ("tandh_1", "tandh_2", "temp_mcp", "tandh_3")
TRIAD = ("tandh", "tandh_1", "tandh_2")
REFERENCE = "temp_mcp"

_board = {}              # what mount_array() learnt about the board
_method = "all"          # sensorset's read-everything method on the board
_stop = threading.Event()
_data = {}               # stream -> {tick: (temp, humidity)}
_counts = {}             # stream or board -> Counter
_done = set()            # eids already written: rows are appended, never twice
_warned = set()          # boards whose extra sensors were already reported


## --------------------------------------------------------------------------
##  Mounting
## --------------------------------------------------------------------------

def _q(dev, expr):
	"""Evaluate expr on the board and return its value.

	Wrapped in a list because main's serial reply strips the characters of
	"None" from both ends of the printed text: True comes back as "Tru".
	"""
	r = dev.exec_cleanup(f"[{expr}]")
	if not isinstance(r, list) or len(r) != 1:
		raise RuntimeError(f"{dev.name}: {expr} -> {str(r)[:200]}")
	return r[0]


def _connect():
	"""A new SerialMPDevice on the Pico whose board.name is BOARD."""
	scope = ScopeAssembly.current
	## auto_connect() probes every free port, and a probe of the wrong board
	## ends with exit_raw_repl() on it. Never probe one the scope already uses.
	for d in scope.devices.values():
		if isinstance(d, SerialMPDevice) and d.connected \
				and d.port not in SerialMPDevice.exclusion_list:
			SerialMPDevice.exclusion_list.append(d.port)
	dev = SerialMPDevice(name=BOARD, search_name=BOARD, connect="autoconnect",
						 exec_main=True, handshake=False)
	if not dev.connected:
		raise RuntimeError(f"{BOARD} not found on USB. Is it plugged in, and "
						   f"does its board.py say name = {BOARD!r}?")
	return dev


def _handshake(dev):
	"""Put the board's objects in the scope tree, never over an existing name."""
	scope = ScopeAssembly.current
	names = dev.exec_cleanup("Handshake.obj_list(globals_=globals())")
	if not isinstance(names, list):
		raise RuntimeError(f"{BOARD}: obj_list() -> {str(names)[:200]}")
	added, skipped = [], []
	for n in names:
		have = scope.devices.get(n)
		ours = getattr(getattr(have, "device", None), "name", None) == BOARD
		taken = (have is not None and not ours) or (have is None and hasattr(scope, n))
		if taken:
			skipped.append(n)
			continue
		proxy = dev.emit_proxy(n)
		proxy.config = dev.device_config(n)
		scope.add_device(n, proxy, description=f"{BOARD} proxy peripheral.")
		added.append(n)
	if skipped:
		log.warning(f"{BOARD}: names already in the scope, not mounted: {skipped}")
		print(f"[yellow]{BOARD}: already in the scope, not mounted from it: {skipped}")
	if "sensorset" not in added:
		raise RuntimeError(f"{BOARD}: sensorset not mounted (board offers {names})")
	return added


def mount_array(remount=False):
	"""Find pico_temp_array on USB, run its main.py, and put the board and its
	objects in the scope tree. Returns the board's SerialMPDevice."""
	global _method
	scope = ScopeAssembly.current
	dev = scope.devices.get(BOARD)
	if dev is not None and getattr(dev, "connected", False) and remount:
		try:
			dev.disconnect()
		except Exception as e:
			log.warning(f"{BOARD}: disconnect before remount failed: {e}")
	if dev is None or not getattr(dev, "connected", False):
		dev = _connect()
		scope.add_device(BOARD, dev, description="Pico: 3 AHT20 and 1 MCP9808 "
						 "(multi_temp_sensor_array).")
	mounted = _handshake(dev)

	if _q(dev, "hasattr(sensorset, 'all')"):
		_method = "all"
	elif _q(dev, "hasattr(sensorset, 'read_all')"):
		_method = "read_all"
	else:
		raise RuntimeError(f"{BOARD}: sensorset has neither all() nor read_all()")

	_board.clear()
	_board.update({"name": BOARD, "port": dev.port, "mounted": mounted,
				   "read_method": f"sensorset.{_method}()"})
	for key, expr in (("uid", "Handshake.uuid"), ("circuit", "board.circuit_id"),
					  ("state", "sensorset.state() if hasattr(sensorset, 'state') else None")):
		try:
			_board[key] = _q(dev, expr)
		except Exception as e:
			log.warning(f"{BOARD}: {expr} failed: {e}")
	print(Panel(Pretty(_board), title=f"{BOARD} mounted"))
	return dev


## --------------------------------------------------------------------------
##  Reading
## --------------------------------------------------------------------------

def _read_scope():
	return {"tandh": ScopeAssembly.current.tandh.read()}


def _read_array():
	return getattr(ScopeAssembly.current.sensorset, _method)()


def _num(x):
	if isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x):
		return None
	return float(x)


def _parse(v):
	"""(temp, humidity) from one sensor's entry, or why there is none.

	Takes {"temp", "humidity"} or (temp, humidity). A 0 is never real.
	"""
	if v is None:
		return "missing"
	if isinstance(v, dict):
		t, h = v.get("temp"), v.get("humidity")
	elif isinstance(v, (list, tuple)) and len(v) == 2:
		t, h = v
	else:
		return "failed"
	t, h = _num(t), _num(h)
	if t is None:
		return "failed"
	if t == 0 or h == 0:
		return "zero"
	return t, h


def _record(board, sensors, tick, read_s, reply):
	"""Turn one board's reply into one row per sensor."""
	if not isinstance(reply, dict):
		if reply is not None:
			log.error(f"{board}: not a reading: {str(reply)[:200]}")
		for s in sensors:
			_counts[s]["failed"] += 1
		return
	extra = set(reply) - set(sensors)
	if extra and board not in _warned:
		_warned.add(board)
		log.warning(f"{board}: sensors not in this protocol, ignored: {sorted(extra)}")
	for s in sensors:
		r = _parse(reply.get(s))
		if isinstance(r, str):
			_counts[s][r] += 1
			continue
		_data[s][tick] = r
		_counts[s]["ok"] += 1
		Experiment.current.mstreams[s](tick=tick, read_s=read_s,
									   temp=r[0], humidity=r[1])


def _reader(board, read, sensors, t0, period, n):
	"""Read one board on the shared grid t0 + k * period, k < n."""
	k = 0
	while k < n:
		slot = t0 + k * period
		if _stop.wait(max(0.0, slot - time.monotonic())):
			return
		late = time.monotonic() - slot
		if late > period:                  # the last read ran over: skip ahead
			skip = int(late // period)
			_counts[board]["skipped"] += skip
			k += skip
			continue
		t = time.monotonic()
		reply = None
		try:
			reply = read()
		except Exception as e:
			log.error(f"{board}: read failed: {type(e).__name__}: {e}")
		_record(board, sensors, k, round(time.monotonic() - t, 3), reply)
		k += 1


def _reset():
	_stop.clear()
	_data.clear()
	_counts.clear()
	for key in STREAMS + ("scope", "array"):
		_counts[key] = Counter()
	for s in STREAMS:
		_data[s] = {}


def test_read():
	"""Read every sensor once and print it. Returns {stream: (temp, humidity) or why not}."""
	got = {}
	for read, sensors in ((_read_scope, ("tandh",)), (_read_array, ARRAY)):
		try:
			reply = read()
		except Exception as e:
			reply = f"{type(e).__name__}: {e}"
		for s in sensors:
			got[s] = _parse(reply.get(s)) if isinstance(reply, dict) else f"failed: {reply}"
	table = Table("stream", "position", "temp C", "humidity %RH", title="test read")
	for s in STREAMS:
		r = got[s]
		if isinstance(r, tuple):
			table.add_row(s, LAYOUT[s]["position"], f"{r[0]:.3f}",
						  "-" if r[1] is None else f"{r[1]:.2f}")
		else:
			table.add_row(s, LAYOUT[s]["position"], f"[red]{escape(str(r)[:60])}", "")
	print(table)
	bad = [s for s in STREAMS if not isinstance(got[s], tuple)]
	if bad:
		print(Panel(f"[red]No reading from {bad}.[/red] On the board: "
					f"scope.sensorset.scan() lists the I2C addresses on each bus "
					f"(AHT20 0x38, MCP9808 0x18); build errors are in "
					f"{escape(str(_board.get('state')))}", title="test read"))
	return got


## --------------------------------------------------------------------------
##  Experiment
## --------------------------------------------------------------------------

def populate_exp():
	exp = Experiment.current
	exp.attribs["protocol"] = PROTOCOL
	exp.attribs["duration_s"] = 300
	exp.attribs["period_s"] = 1.0
	exp.attribs["reference"] = REFERENCE
	exp.attribs["sensor_layout"] = LAYOUT
	exp.attribs["seat"] = ("triangular seat; three AHT20 boards stand as its "
						   "walls, sensor side in (the triad); MCP9808 lies flat "
						   "in the middle")
	exp.attribs["array_board"] = dict(_board)
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	if "tandh" not in scope.devices:
		raise RuntimeError("this scope has no tandh device: is its Pico mounted?")
	mount_array()                # before the experiment: no empty run if it fails
	exp = Experiment.Construct(["tandh_divergence"])
	for s in STREAMS:
		ms = exp.new_measurementstream(s, monitors=["tick", "read_s"],
									   measurements=["temp", "humidity"])
		ms.auto_update_explogs = False       # written once, at the end
		ms.auto_update_df = False            # main appends to a DataFrame per row
	populate_exp()
	_reset()
	test_read()


def _progress(t0, end, threads):
	"""Wait for the readers, printing the row counts every 30 s."""
	note = t0 + 30
	while any(t.is_alive() for t in threads):
		now = time.monotonic()
		if now > end + 15:
			log.error("a board is still being read 15 s after the end: its Pico is not answering")
			return
		if now >= note:
			print(f"{int(now - t0)} s: " + ", ".join(f"{s} {len(_data[s])}" for s in STREAMS))
			note += 30
		time.sleep(0.5)


def start():
	"""Read every sensor at 1 Hz for duration_s, then save and sync."""
	global exp
	exp = Experiment.current
	a = exp.attribs
	exp.logs["attribs"] = a          # main writes attribs only on close()
	if exp.eid in _done:
		print(Panel("[red]This experiment already has its readings. "
					"Close it and run create_exp() again.", title="refused"))
		return
	exp.schedule.clear()             # nothing else talks to the Picos
	_reset()
	period = float(a["period_s"])
	n = int(round(a["duration_s"] / period))
	t0 = time.monotonic() + 1.0      # both boards start on the same slot
	exp.log("divergence_start", attribs={"protocol": PROTOCOL, "slots": n,
				"period_s": period, "slot0_unix": time.time() + 1.0})
	threads = [threading.Thread(target=_reader, daemon=True, name=f"read-{b}",
								args=(b, read, sensors, t0, period, n))
			   for b, read, sensors in (("scope", _read_scope, ("tandh",)),
										("array", _read_array, ARRAY))]
	for t in threads:
		t.start()
	print(f"Reading {len(STREAMS)} sensors every {period} s for {n * period:.0f} s. Ctrl-C stops early.")
	stopped_early = False
	try:
		_progress(t0, t0 + n * period, threads)
	except KeyboardInterrupt:
		stopped_early = True
		print("[yellow]Stopped early; keeping what was read.")
	finally:
		_stop.set()
		for t in threads:
			t.join(timeout=5)
		hung = [t.name for t in threads if t.is_alive()]
		try:
			_finish(stopped_early, hung)
		finally:
			cleanup()            # right after the acquisition, whatever happened


def _finish(stopped_early, hung):
	exp = Experiment.current
	rows = {}
	for s in STREAMS:
		readings = [dict(r) for r in exp.mstreams[s].readings]
		exp.logs["results"].extend(readings)
		rows[s] = len(readings)
	_done.add(exp.eid)
	summary = summarise()
	exp.log("divergence_summary", attribs={
		"protocol": PROTOCOL, "stopped_early": stopped_early, "hung": hung,
		"rows": rows, "counts": {k: dict(v) for k, v in _counts.items()},
		**summary})
	if hung:
		print(Panel(f"[red]Still reading when the run ended: {hung}. That Pico "
					f"is not answering; its rows stop where it hung.", title="hung"))


## --------------------------------------------------------------------------
##  Summary
## --------------------------------------------------------------------------

def _r(x, nd=3):
	return None if x is None else round(x, nd)


def _mean(v):
	return statistics.fmean(v) if v else None


def _sd(v):
	return statistics.stdev(v) if len(v) > 1 else None


def summarise():
	"""Per sensor: mean and SD, and its difference from the reference on the
	same tick. Plus the triad's spread (max - min) per tick, over the triad
	sensors that gave readings at all, on the ticks where all of them did."""
	ref = _data[REFERENCE]
	sensors = {}
	for s in STREAMS:
		d = _data[s]
		temps = [t for t, _ in d.values()]
		hums = [h for _, h in d.values() if h is not None]
		diff = [t - ref[k][0] for k, (t, _) in d.items() if k in ref] if s != REFERENCE else []
		sensors[s] = {"position": LAYOUT[s]["position"], "n": len(d),
					  "temp_mean": _r(_mean(temps)), "temp_sd": _r(_sd(temps)),
					  "minus_ref_mean": _r(_mean(diff)), "minus_ref_sd": _r(_sd(diff)),
					  "humidity_mean": _r(_mean(hums), 2)}
	present = [s for s in TRIAD if _data[s]]
	ticks = set.intersection(*(set(_data[s]) for s in present)) if len(present) > 1 else set()
	spread = [max(_data[s][k][0] for s in present) - min(_data[s][k][0] for s in present)
			  for k in ticks]
	triad = {"members": present, "n": len(spread), "mean": _r(_mean(spread)),
			 "max": _r(max(spread) if spread else None)}

	table = Table("stream", "position", "n", "temp C", "SD", f"minus {REFERENCE}",
				  "SD", "humidity %RH", title="T&H divergence")
	for s, v in sensors.items():
		table.add_row(s, v["position"], str(v["n"]),
					  *(("-" if v[k] is None else str(v[k])) for k in
						("temp_mean", "temp_sd", "minus_ref_mean", "minus_ref_sd",
						 "humidity_mean")))
	print(table)
	print(f"Triad spread ({', '.join(present) or 'no sensors'}; max - min, same tick): "
		  f"mean {triad['mean']} C, "
		  f"max {triad['max']} C over {triad['n']} ticks")
	return {"sensors": sensors, "triad_spread_c": triad}


## --------------------------------------------------------------------------
##  Cleanup
## --------------------------------------------------------------------------

def _step(what, fn):
	"""One cleanup step. A failure is logged and the next step still runs."""
	try:
		return fn()
	except Exception as e:
		log.error(f"cleanup: {what} failed: {type(e).__name__}: {e}")
		print(f"[red]cleanup: {what} failed: {type(e).__name__}: {e}")


def cleanup():
	"""Stop the schedule, save and sync. start() calls it right after the
	acquisition; call it yourself only if start() never got that far. Does NOT
	close the experiment: type exp.close() after."""
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True
	_step("save", exp.__save__)
	_step("sync", exp.sync_dir)
	print(Panel("[yellow]Done. The experiment is still OPEN -- type "
				"[bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel("create_exp()    # mounts pico_temp_array, test-reads every sensor\n"
				"start()         # 5 min at 1 Hz, then cleanup(): saves and syncs\n"
				"exp.close()", title="T&H divergence"))
