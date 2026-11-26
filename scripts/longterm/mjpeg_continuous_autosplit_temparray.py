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

The continuous autosplit recording, with the pico_temp_array sensors logged
alongside it.

	create_exp()             the autosplit's experiment, plus the array: mounts
	                         pico_temp_array and test-reads its sensors
	place("tandh_1", "on the stage")   where each sensor is; once per sensor
	start_acq_blocking()     the autosplit run, with the array logged throughout
	exp.close()

The recording is mjpeg_continuous_autosplit itself, imported and called
unchanged: same parameters (exp.attribs, including sync_files), same files,
same run evidence, same end-of-run sync. This script only adds the array.

The array
---------
Every sensor the board reports in sensorset.all() (3 or 4) is read once per
array_poll_s, from its own thread, into tempsensors.csv:

	wall      unix time of the read, s
	tick      the read's slot number (0, 1, 2, ...)
	read_s    how long the board took to answer
	sensor    tandh_1, tandh_2, tandh_3, temp_mcp
	temp      C
	humidity  %RH, empty for temp_mcp

Every stream_period_s (5 min, as the scope's own tandh stream) one reading of
each sensor also goes into a stream named after it, with the same fields as
the tandh stream plus tick. Those rows are written to the experiment when the
logger stops.

The logger stops a few seconds before the last split ends, so the end-of-run
sync gets a complete tempsensors.csv. A failed read, a missing sensor or a
reading of exactly 0 writes nothing and is counted in the temp_array_summary
event. A hung array Pico stops only the logger, never the recording.

The scope's own T&H sensor is not read here: it stays on the autosplit's
5-min tandh stream. A second thread reading it would talk to the scope's Pico
at the same time as the recorder does, and that serial link has no lock.

Where the sensors are
---------------------
place(sensor, where) records a sensor's location as a sensor_location event
with the time, and in exp.attribs["sensor_locations"]. Call it for each sensor
before start_acq_blocking(). The REPL is blocked during the run, so a sensor
moved mid-run cannot be recorded from here: note the time and the place.
"""

import csv
import logging as log
import os
import threading
import time
from collections import Counter

from rich import print
from rich.panel import Panel
from rich.table import Table

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from scripts.longterm import mjpeg_continuous_autosplit as autosplit
from scripts.calibration import tandh_divergence as td


__description__ = \
"""Continuous autosplit recording with the pico_temp_array sensors logged
alongside: tempsensors.csv every second, a stream per sensor every 5 min.

create_exp(), place("tandh_1", "where") for each sensor,
start_acq_blocking(), exp.close().
"""

CSV_NAME = "tempsensors.csv"

_stop = threading.Event()
_logger = None
_sensors = []            # names the board reported at create_exp()
_counts = {}             # sensor or "array" -> Counter
_rows_written = False    # stream rows go to the experiment once


## --------------------------------------------------------------------------
##  The array
## --------------------------------------------------------------------------

def _read():
	"""{sensor: (temp, humidity) or why not}, or a string if the read failed."""
	try:
		reply = td._read_array()
	except Exception as e:
		return f"{type(e).__name__}: {e}"
	if not isinstance(reply, dict):
		return f"not a reading: {str(reply)[:200]}"
	return {name: td._parse(v) for name, v in reply.items()}


def test_read():
	"""Read the array once and print it. Returns what _read() returns."""
	got = _read()
	if isinstance(got, str):
		print(Panel(f"[red]{got}", title="pico_temp_array"))
		return got
	table = Table("sensor", "temp C", "humidity %RH", title="pico_temp_array")
	for name, r in got.items():
		if isinstance(r, tuple):
			table.add_row(name, f"{r[0]:.3f}", "-" if r[1] is None else f"{r[1]:.2f}")
		else:
			table.add_row(name, f"[red]{r}", "")
	print(table)
	return got


def _log_array(t0, period, n, stream_every, path):
	"""Read the array on the grid t0 + k * period, k < n, into the CSV."""
	k = 0
	next_stream = 0
	with open(path, "a", newline="") as f:
		w = csv.writer(f)
		while k < n:
			slot = t0 + k * period
			if _stop.wait(max(0.0, slot - time.monotonic())):
				break
			late = time.monotonic() - slot
			if late > period:                  # the last read ran over: skip ahead
				skip = int(late // period)
				_counts["array"]["skipped"] += skip
				k += skip
				continue
			wall, t = time.time(), time.monotonic()
			got = _read()
			read_s = round(time.monotonic() - t, 3)
			if isinstance(got, str):
				_counts["array"]["failed"] += 1
				log.error(f"pico_temp_array: {got}")
			else:
				## A stream row is taken in memory now, so it carries this
				## reading's time; a failed read moves it to the next good one.
				stream_now = k >= next_stream
				for name, r in got.items():
					if not isinstance(r, tuple):
						_counts.setdefault(name, Counter())[r] += 1
						continue
					_counts.setdefault(name, Counter())["ok"] += 1
					w.writerow([f"{wall:.3f}", k, read_s, name, r[0],
								"" if r[1] is None else r[1]])
					if stream_now and name in _sensors:
						Experiment.current.mstreams[name](tick=k, read_s=read_s,
														  temp=r[0], humidity=r[1])
				for name in _sensors:
					if name not in got:
						_counts[name]["missing"] += 1
				if stream_now:
					next_stream = k + stream_every
				f.flush()
			k += 1
	_write_streams()


def _write_streams():
	"""The sensor streams' 5-min rows into the experiment, once."""
	global _rows_written
	if _rows_written:
		return
	_rows_written = True
	exp = Experiment.current
	rows = [dict(r) for name in _sensors for r in exp.mstreams[name].readings]
	exp.logs["results"].extend(rows)         # one append: a save never sees half
	exp.log("temp_array_summary", attribs={
		"csv": CSV_NAME, "stream_rows": len(rows),
		"counts": {k: dict(v) for k, v in _counts.items()}})


def start_array(duration_s):
	"""Start logging the array for duration_s, in the background."""
	global _logger, _rows_written
	exp = Experiment.current
	a = exp.attribs
	period = float(a["array_poll_s"])
	_stop.clear()
	_rows_written = False
	_counts.clear()
	_counts["array"] = Counter()
	for name in _sensors:
		_counts[name] = Counter()
	path = os.path.abspath(CSV_NAME)
	if not os.path.exists(path):
		with open(path, "w", newline="") as f:
			csv.writer(f).writerow(["wall", "tick", "read_s", "sensor", "temp", "humidity"])
	n = int(duration_s // period)
	stream_every = max(1, int(round(a["stream_period_s"] / period)))
	_logger = threading.Thread(target=_log_array, daemon=True, name="temp-array",
							   args=(time.monotonic(), period, n, stream_every, path))
	_logger.start()
	exp.log("temp_array_start", attribs={"slots": n, "poll_s": period,
										 "slot0_unix": time.time()})
	print(f"pico_temp_array: {_sensors} every {period} s into {CSV_NAME}, "
		  f"for {duration_s / 3600:.1f} h")


def stop_array():
	"""Stop the logger now and write its stream rows. Safe to call twice."""
	_stop.set()
	if _logger is not None:
		_logger.join(timeout=10)
		if _logger.is_alive():
			log.error("pico_temp_array: the logger is stuck in a read; its Pico is not answering")
			print("[red]pico_temp_array: the board is not answering; stream rows written without it")
	_write_streams()


## --------------------------------------------------------------------------
##  Experiment
## --------------------------------------------------------------------------

def place(sensor, where):
	"""Record where a sensor is, with the time."""
	exp = Experiment.current
	exp.attribs.setdefault("sensor_locations", {})[sensor] = where
	exp.log("sensor_location", attribs={"sensor": sensor, "where": where,
										"unix": time.time()})
	print(f"{sensor}: {where}")


def create_exp():
	"""The autosplit's experiment, plus pico_temp_array and a stream per sensor."""
	global exp, scope
	scope = ScopeAssembly.current
	td.mount_array()                 # before the experiment: no empty run if it fails
	autosplit.create_exp()
	exp = Experiment.current
	exp.copy_payload([os.path.abspath(autosplit.__file__), os.path.abspath(td.__file__)])

	got = test_read()
	if isinstance(got, str):
		raise RuntimeError(f"pico_temp_array did not answer: {got}")
	_sensors[:] = list(got)
	for name in _sensors:
		ms = exp.new_measurementstream(name, monitors=["tick", "read_s"],
									   measurements=["temp", "humidity"])
		ms.auto_update_explogs = False       # written once, when the logger stops
		ms.auto_update_df = False

	exp.attribs["array_poll_s"] = 1.0
	exp.attribs["stream_period_s"] = 300
	exp.attribs["temp_array"] = {"board": dict(td._board), "sensors": list(_sensors),
								 "csv": CSV_NAME}
	exp.attribs.setdefault("sensor_locations", {})
	print(Panel("Record where each sensor is before starting, for example\n"
				+ "\n".join(f'  place("{n}", "...")' for n in _sensors),
				title="sensor locations"))


def start_acq_blocking():
	"""The autosplit run, with the array logged until a few seconds before the
	last split ends."""
	exp = Experiment.current
	a = exp.attribs
	unplaced = [n for n in _sensors if n not in a.get("sensor_locations", {})]
	if unplaced:
		print(f"[yellow]No location recorded for {unplaced}: place(sensor, where)")
	start_array(a["chunk_size_sec"] * a["no_chunks"])
	try:
		autosplit.start_acq_blocking()
	finally:
		stop_array()
		exp.__save__()


if __name__ == "__main__":
	## The same start-up as mjpeg_continuous_autosplit's own.
	scope = ScopeAssembly.current
	try:
		from core.utilities.diskspace import disk_panel
		print(disk_panel())
	except Exception as e:
		print(f"[red]Disk space panel failed: {type(e).__name__}: {e}")
	scope.lit.setVs(0.50, 0, 0)
	print("Lights ready...")
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.off()
