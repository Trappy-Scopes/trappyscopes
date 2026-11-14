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

Pico link stress test. Finds every MicroPython board on the scope -- the ones
the scope mounted at start-up (e.g. `pico`) and any other board plugged in --
and drives each one through the path production uses (SerialMPDevice ->
pyboard raw REPL), from exp.schedule: the same thread that reads T&H during a
recording. The main thread only watches.

    create_exp()
    start_acq_blocking()     # runs every step, writes the report, cleans up

Do not run it during an acquisition: it takes over the Pico and the lights.

Steps -- attribs["steps"], in this order by default
-----
ramp                rate steps (1, 2, 5, 10, 20, 50 Hz per board). A board's
                    peak is the highest step with no timeout, error, wrong
                    answer or recovery, and a+b p99 under p99_limit_ms.
burst               back-to-back a+b calls for burst_s: the most the link does.
drill               forced reconnects, one board at a time while the others
                    keep running: close the port and reconnect in place, then
                    machine.reset() and wait for the board to come back.
schedule_exception  a job that raises inside exp.schedule. Does the scheduler
                    thread die, do the Pico jobs stop, do the boards still
                    answer when called directly, does a restart bring it back?
schedule_hang       a job that blocks exp.schedule for schedule_hang_s. How
                    long do the Pico calls stall, and does the schedule resume?
pico_hang           a call that never returns (a loop on the Pico), on each
                    board in turn. Shows what one hung Pico call does to every
                    other job on exp.schedule, and which recovery step clears it.
soak                soak_h hours at soak_fraction x each board's peak.

Calls
-----
a+b (answer checked), "x"*N echo (checked), tandh.read() and lit.setVs(<the
same values>) where the board has them, and time.ticks_ms() every
uptime_every calls -- a smaller value than last time means the board rebooted
on its own.

Watchdog and recovery
---------------------
A call still running after call_timeout_s, an error, or a wrong answer starts
the ladder. The step that brings the board back is logged:

    1 wait          wait for a late reply; the link may be fine on its own
    2 interrupt     Ctrl-C, re-enter the raw REPL
    3 soft_reset    soft reset, rerun main.py, set the lights again
    4 reconnect     explicit disconnect(), then reconnect the SAME object by
                    its search_name (the scope's proxies keep working),
                    main.py, check board name and uid
    5 hard_reset    machine.reset() if the port is open, then wait up to
                    reenumerate_wait_s for the board to come back
    6 fatal         nothing worked: the run ends (end_on_fatal) or the board
                    is dropped

Output
------
calls.csv    one row per call         events.csv  recoveries, drills, resets
system.csv   1 Hz throttled flags and scheduler state
kernel.log   kernel messages; USB lines in the run window go in the report
pico_stress.json, REPORT.md

Left in on purpose: SerialMPDevice.__call__ strips the characters "\\r\\nNone"
from both ends of every answer (True comes back as "Tru"). Every call here
returns a number, a dict, "x"*N or None, which it does not damage.
"""

import csv
import datetime
import json
import logging as log
import os
import random
import re
import subprocess
import threading
import time
from collections import Counter

from rich import print
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
from hive.processorgroups.micropython import SerialMPDevice


__description__ = \
"""Pico link stress test -- every MicroPython board on the scope.

create_exp(), then start_acq_blocking(). Runs every step, recovers or gives up
on each board, writes REPORT.md, and cleans up on its own.
"""


def populate_exp():
	exp = Experiment.current
	a = exp.attribs
	a["steps"] = ["ramp", "burst", "drill", "schedule_exception",
				  "schedule_hang", "pico_hang", "soak"]
	## exp.schedule polls every 10 ms, so 50 Hz is the useful ceiling.
	a["ramp_hz"] = [1, 2, 5, 10, 20, 50]
	a["ramp_step_s"] = 120
	a["p99_limit_ms"] = 100                  # a+b round trip, for "clean"
	a["burst_s"] = 60
	a["drill_hz"] = 5                        # rate of the boards not drilled
	a["drill_settle_s"] = 10
	a["schedule_test_s"] = 20
	a["schedule_hang_s"] = 30
	a["soak_h"] = 1.0
	a["soak_fraction"] = 0.5
	## Relative weights. tandh/light only where the board has them.
	a["mix"] = {"add": 8, "echo": 1, "tandh": 1, "light": 1}
	a["echo_bytes"] = 1024
	a["uptime_every"] = 50
	a["light"] = [0.5, 0.0, 0.0]
	## Watchdog and recovery.
	a["call_timeout_s"] = 5                  # tandh.read() takes ~0.25 s
	a["late_reply_s"] = 5
	a["alive_timeout_s"] = 3
	a["reenumerate_wait_s"] = 30
	a["end_on_fatal"] = True
	a["include_unmounted"] = True            # also boards the scope did not mount
	a["sync_files"] = False
	print(Panel(Pretty(a), title="Experiment Attributes"))


def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["pico_link_stress"])
	exp.new_measurementstream("picos",
		monitors=["device", "port", "board", "uid", "mpy"],
		measurements=["has_tandh", "has_lit"])
	exp.new_measurementstream("steps",
		monitors=["step", "device", "rate_hz"],
		measurements=["n", "ok", "timeouts", "errors", "wrong", "add_p50_ms",
					  "add_p99_ms", "max_ms", "achieved_hz", "recoveries"])
	populate_exp()


## ==========================================================================
##  State
## ==========================================================================

class _Dev:
	"""Test state for one board. Kept outside SerialMPDevice on purpose: its
	__getattr__ turns any unknown attribute into a proxy call on the Pico."""

	def __init__(self, name, dev, owned):
		self.name, self.dev, self.owned = name, dev, owned
		self.port, self.board = dev.port, dev.board_name
		self.uid, self.mpy, self.has = None, "", {}
		self.cycle, self.i, self.rate = ["add"], 0, 0
		self.busy_since, self.call_id, self.stuck_id = None, 0, None
		self.need_recovery, self.recovering, self.paused, self.fatal = None, False, False, False
		self.force_call, self.last_ticks = None, None
		self.rows, self.guards = [], []
		self.recov_total, self.recov_step = Counter(), Counter()
		self.n_recoveries, self.last_recovery = 0, None
		self.peak_hz, self.burst_left = None, 0
		self.steps, self.drills, self.tests = [], [], {}


class _Fatal(Exception):
	pass


global DEVS, A, STEP, REPORT
DEVS, A, STEP, REPORT = [], {}, "", {}
_files, _flock = {}, threading.Lock()
_sys = {"next": 0.0, "throttled": None, "vcgencmd": True, "alive": True, "seen": set()}


def _live():
	return [st for st in DEVS if not st.fatal]


## ==========================================================================
##  Logging
## ==========================================================================

HEADERS = {
	"calls": ["t_wall", "step", "rate_hz", "device", "port", "call",
			  "latency_ms", "outcome", "detail"],
	"events": ["t_wall", "step", "device", "event", "detail"],
	"system": ["t_wall", "throttled", "schedule_alive"],
}


def _open_csvs():
	for name, header in HEADERS.items():
		f = open(f"{name}.csv", "w", newline="", buffering=1)
		w = csv.writer(f)
		w.writerow(header)
		_files[name] = (f, w)


def _close_csvs():
	for f, _ in _files.values():
		try:
			f.close()
		except Exception:
			pass
	_files.clear()


def _row(name, *vals):
	with _flock:
		if name in _files:
			_files[name][1].writerow(vals)


def _event(st, event, detail=""):
	who = st.name if st else "-"
	_row("events", f"{time.time():.3f}", STEP, who, event, detail)
	REPORT.setdefault("events", []).append(
		{"t": round(time.time(), 3), "step": STEP, "device": who, "event": event,
		 "detail": detail})
	colour = "red" if re.search(r"fatal|fail|dead|reset|wrong|stuck", event + detail, re.I) \
		else "cyan"
	print(f"[{colour}]  [{STEP}] {who}: {event} {detail}[/]")


## ==========================================================================
##  One call, and the scheduled jobs
## ==========================================================================

def _call_spec(kind):
	"""The text sent to the board and a check of its answer."""
	if kind == "add":
		a, b = random.randint(1, 10**6), random.randint(1, 10**6)
		return f"{a}+{b}", lambda r: r == a + b
	if kind == "echo":
		n = A["echo_bytes"]
		return f'"x"*{n}', lambda r: r == "x" * n
	if kind == "tandh":
		return "tandh.read()", lambda r: (isinstance(r, dict)
			and -40 < r.get("temp", -99) < 85 and 0 <= r.get("humidity", -1) <= 100)
	if kind == "light":
		v = ", ".join(str(x) for x in A["light"])
		return f"lit.setVs({v})", lambda r: r in ("", None)
	if kind == "uptime":
		return '__import__("time").ticks_ms()', lambda r: isinstance(r, int)
	if kind == "hang":
		## Never returns: a loop on the board. Only Ctrl-C ends it.
		return 'exec("import time\\nwhile True:\\n time.sleep_ms(10)")', lambda r: False
	raise ValueError(kind)


def _one_call(st, kind):
	cmd, check = _call_spec(kind)
	st.call_id += 1
	cid = st.call_id
	t_wall, t0 = time.time(), time.monotonic()
	st.busy_since = t0
	outcome, detail, r = "ok", "", None
	try:
		r = st.dev(cmd)                     # SerialMPDevice.__call__, as production
		if not check(r):
			outcome, detail = "wrong", repr(r)[:120]
	except Exception as e:
		outcome, detail = "error", f"{type(e).__name__}: {e}"[:200]
	finally:
		st.busy_since = None
	ms = (time.monotonic() - t0) * 1000
	if st.stuck_id == cid:
		outcome, detail = "timeout", f"released after {ms / 1000:.1f} s ({outcome}) {detail}".strip()
	if kind == "uptime" and outcome == "ok":
		if st.last_ticks is not None and r < st.last_ticks:
			_event(st, "pico_uptime_reset", f"ticks_ms {st.last_ticks} -> {r}: the board rebooted")
		st.last_ticks = r
	st.rows.append((time.monotonic(), kind, outcome, ms))
	_row("calls", f"{t_wall:.3f}", STEP, st.rate, st.name, st.port, kind,
		 f"{ms:.1f}", outcome, detail)
	if outcome != "ok" and not st.need_recovery:
		st.need_recovery = f"{kind} {outcome}: {detail}"[:200]
	return outcome


def _probe_job(st):
	"""Runs on exp.schedule: one call from the board's mix."""
	if st.paused or st.fatal or st.need_recovery or st.recovering:
		return
	if st.force_call:
		kind, st.force_call = st.force_call, None
	else:
		st.i += 1
		kind = "uptime" if st.i % A["uptime_every"] == 0 else st.cycle[st.i % len(st.cycle)]
	_one_call(st, kind)


def _burst_job(st):
	"""Runs on exp.schedule: back-to-back a+b until burst_left is used up."""
	if st.burst_left <= 0 or st.paused or st.fatal or st.need_recovery or st.recovering:
		return
	t0 = time.monotonic()
	while time.monotonic() - t0 < st.burst_left and not (st.paused or st.need_recovery):
		_one_call(st, "add")
	st.burst_left -= time.monotonic() - t0


def _schedule_probes(rates):
	exp.schedule.clear("pico")
	for st, hz in rates.items():
		if st.fatal or not hz:
			continue
		st.rate = hz
		exp.schedule.every(1.0 / hz).seconds.do(_probe_job, st).tag("pico")


## ==========================================================================
##  Guarded calls from the main thread
## ==========================================================================

def _guarded(st, fn, timeout):
	"""Run fn in a short-lived thread and give up after timeout. A serial read
	has no timeout, so a call made directly could block the main thread for
	good. A guard thread that never returns is kept; _release() frees it."""
	box = {}

	def run():
		try:
			box["v"] = fn()
		except Exception as e:
			box["e"] = f"{type(e).__name__}: {e}"

	t = threading.Thread(target=run, daemon=True, name=f"pico_guard_{st.name}")
	t.start()
	t.join(timeout)
	if t.is_alive():
		st.guards.append(t)
		return False, f"no answer in {timeout} s"
	if "e" in box:
		return False, box["e"]
	return True, box.get("v")


def _idle(st):
	st.guards = [g for g in st.guards if g.is_alive()]
	return st.busy_since is None and not st.guards


def _wait_idle(st, seconds):
	t_end = time.monotonic() + seconds
	while time.monotonic() < t_end:
		if _idle(st):
			return True
		time.sleep(0.05)
	return _idle(st)


def _alive(st):
	"""Does the board answer a checked a+b within alive_timeout_s? Used only
	when the link should be idle and answering."""
	a, b = random.randint(1, 10**6), random.randint(1, 10**6)
	ok, r = _guarded(st, lambda: st.dev(f"{a}+{b}"), A["alive_timeout_s"])
	return ok and r == a + b


def _serial(st):
	d = st.dev.device
	return getattr(d, "serial", None) if d is not None else None


def _restore(st):
	if st.has.get("light"):
		v = ", ".join(str(x) for x in A["light"])
		_guarded(st, lambda: st.dev(f"lit.setVs({v})"), 3)


def _uid(st):
	ok, r = _guarded(st, lambda: st.dev(
		'int.from_bytes(__import__("machine").unique_id(), "big")'), 5)
	return r if ok and isinstance(r, int) else None


def _release(st):
	"""Free the port: wake any blocked read, then an explicit disconnect()
	(which takes the port off the exclusion list)."""
	ser = _serial(st)
	if ser is not None and hasattr(ser, "cancel_read"):
		try:
			ser.cancel_read()
		except Exception:
			pass
	time.sleep(0.2)
	if st.dev.device is not None:
		_guarded(st, st.dev.disconnect, 5)


def _send_machine_reset(st):
	if st.dev.device is not None:
		_guarded(st, lambda: st.dev.device.exec_raw_no_follow(
			"import machine\nmachine.reset()"), 3)


def _reconnect_once(st):
	"""Reconnect the same SerialMPDevice through its own auto_connect."""
	ok, r = _guarded(st, st.dev.auto_connect, 60)
	if not (ok and st.dev.connected):
		return False
	if st.board and st.dev.board_name != st.board:
		_event(st, "wrong_board", f"got {st.dev.board_name!r}, expected {st.board!r}")
		return False
	ok, r = _guarded(st, st.dev.exec_main, 30)
	if not ok:
		_event(st, "exec_main_failed", str(r))
		return False
	uid = _uid(st)
	if st.uid is not None and uid != st.uid:
		_event(st, "wrong_board", f"uid {uid}, expected {st.uid}")
		return False
	if st.dev.port != st.port:
		_event(st, "port_changed", f"{st.port} -> {st.dev.port}")
		st.port = st.dev.port
	_restore(st)
	return _alive(st)


def _wait_and_reconnect(st):
	t_end = time.monotonic() + A["reenumerate_wait_s"]
	while time.monotonic() < t_end:
		time.sleep(2)
		if _reconnect_once(st):
			return True
	return False


## ==========================================================================
##  Recovery ladder
## ==========================================================================

def _r_wait(st):
	return _wait_idle(st, A["late_reply_s"]) and _alive(st)


def _r_interrupt(st):
	ser = _serial(st)
	if ser is None:
		return False
	_guarded(st, lambda: ser.write(b"\r\x03\x03"), 2)
	if not _wait_idle(st, 3):
		return False
	ok, _ = _guarded(st, lambda: st.dev.device.enter_raw_repl(soft_reset=False), 5)
	return ok and _alive(st)


def _r_soft_reset(st):
	if not _idle(st) or st.dev.device is None:
		return False
	ok, _ = _guarded(st, st.dev.device.enter_raw_repl, 10)
	if not ok:
		return False
	ok, _ = _guarded(st, st.dev.exec_main, 30)
	if not ok:
		return False
	_restore(st)
	return _alive(st)


def _r_reconnect(st):
	_release(st)
	_wait_idle(st, 5)
	return _reconnect_once(st)


def _r_hard_reset(st):
	if st.dev.connected:
		_send_machine_reset(st)
	_release(st)
	st.last_ticks = None                    # a hard reset restarts ticks_ms
	return _wait_and_reconnect(st)


LADDER = [("wait", _r_wait), ("interrupt", _r_interrupt),
		  ("soft_reset", _r_soft_reset), ("reconnect", _r_reconnect),
		  ("hard_reset", _r_hard_reset)]


def _recover(st, reason):
	st.recovering, st.paused = True, True
	t0 = time.monotonic()
	_event(st, "recovery_start", reason)
	won = None
	for name, fn in LADDER:
		try:
			ok = fn(st)
		except Exception as e:
			ok = False
			_event(st, f"recovery_{name}_error", f"{type(e).__name__}: {e}")
		_event(st, f"recovery_{name}", "ok" if ok else "failed")
		if ok:
			won = name
			break
	ms = (time.monotonic() - t0) * 1000
	st.n_recoveries += 1
	st.last_recovery = won
	if won:
		st.recov_total[won] += 1
		st.recov_step[won] += 1
		st.need_recovery, st.stuck_id, st.paused = None, None, False
		_event(st, "recovered", f"by {won} in {ms:.0f} ms")
	else:
		st.fatal = True
		st.recov_total["fatal"] += 1
		st.recov_step["fatal"] += 1
		_event(st, "fatal", f"no recovery step worked ({ms:.0f} ms): {reason}")
		_release(st)
	st.recovering = False


## ==========================================================================
##  Main-thread watch loop
## ==========================================================================

def _run(cmd, timeout=10):
	try:
		p = subprocess.run(cmd, shell=True, timeout=timeout,
						   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except subprocess.TimeoutExpired:
		return None, f"<timed out after {timeout}s>"
	except Exception as e:
		return None, f"<{type(e).__name__}: {e}>"


def _system_tick():
	"""1 Hz: throttled flags and whether the scheduler thread is alive."""
	now = time.monotonic()
	if now < _sys["next"]:
		return
	_sys["next"] = now + 1.0
	thr = ""
	if _sys["vcgencmd"]:
		_, out = _run("vcgencmd get_throttled", timeout=2)
		m = re.search(r"throttled=(0x[0-9a-fA-F]+)", out or "")
		if m:
			thr = m.group(1)
		else:
			_sys["vcgencmd"] = False
			_event(None, "vcgencmd_unavailable", (out or "").strip()[:100])
	if thr and thr != _sys["throttled"]:
		if _sys["throttled"] is not None or thr != "0x0":
			_event(None, "throttled_changed", f"{_sys['throttled']} -> {thr}")
		_sys["throttled"] = thr
		_sys["seen"].add(thr)
	th = getattr(exp.schedule, "thread", None)
	alive = bool(th is not None and th.is_alive())
	if alive != _sys["alive"]:
		_event(None, "schedule_thread", "alive" if alive else "DEAD")
		_sys["alive"] = alive
	_row("system", f"{time.time():.3f}", thr, int(alive))


def _supervise(seconds, until=None):
	"""Watch the boards for `seconds` (or until `until()`): flag stuck calls,
	run the ladder, sample the system."""
	t_end = time.monotonic() + seconds
	while time.monotonic() < t_end:
		if until is not None and until():
			return
		now = time.monotonic()
		for st in _live():
			b = st.busy_since
			if b is not None and now - b > A["call_timeout_s"] and st.stuck_id != st.call_id:
				st.stuck_id = st.call_id
				st.need_recovery = f"call stuck > {A['call_timeout_s']} s"
				_event(st, "call_stuck", f"no reply after {A['call_timeout_s']} s")
			if st.need_recovery and not st.recovering:
				_recover(st, st.need_recovery)
				if st.fatal and A["end_on_fatal"]:
					raise _Fatal(st.name)
		_system_tick()
		time.sleep(0.1)


def _quiesce():
	_supervise(A["call_timeout_s"] + 3, until=lambda: all(
		_idle(s) and not s.need_recovery and not s.recovering for s in _live()))


## ==========================================================================
##  Per-step statistics
## ==========================================================================

def _pct(xs, q):
	if not xs:
		return None
	return round(xs[min(len(xs) - 1, int(round(q / 100 * (len(xs) - 1))))], 1)


def _begin(step, hz=0):
	global STEP
	STEP = step
	for st in DEVS:
		st.rows, st.recov_step = [], Counter()
	_event(None, "step_start", f"{step} {hz or ''}".strip())


def _end_stats(st, step, hz):
	rows = list(st.rows)
	n = len(rows)
	cnt = Counter(o for _, _, o, _ in rows)
	add = sorted(ms for _, k, o, ms in rows if k == "add" and o == "ok")
	allms = [ms for _, _, _, ms in rows]
	span = rows[-1][0] - rows[0][0] if n > 1 else 0
	s = {"step": step, "device": st.name, "rate_hz": hz, "n": n, "ok": cnt["ok"],
		 "timeouts": cnt["timeout"], "errors": cnt["error"], "wrong": cnt["wrong"],
		 "add_p50_ms": _pct(add, 50), "add_p99_ms": _pct(add, 99),
		 "max_ms": round(max(allms), 1) if allms else None,
		 "achieved_hz": round((n - 1) / span, 2) if span > 0 else None,
		 "recoveries": sum(st.recov_step.values()), "recovered_by": dict(st.recov_step)}
	s["clean"] = bool(n and s["timeouts"] == s["errors"] == s["wrong"] == 0
					  and s["recoveries"] == 0 and s["add_p99_ms"] is not None
					  and s["add_p99_ms"] <= A["p99_limit_ms"])
	st.steps.append(s)
	try:
		exp.mstreams["steps"](step=step, device=st.name, rate_hz=hz,
			**{k: s[k] for k in ("n", "ok", "timeouts", "errors", "wrong", "add_p50_ms",
								 "add_p99_ms", "max_ms", "achieved_hz", "recoveries")})
	except Exception as e:
		log.error(f"steps stream: {e}")
	print(f"  {st.name:<14} {step:<18} {hz!s:>6} Hz  n={n} ok={s['ok']} "
		  f"timeout={s['timeouts']} error={s['errors']} wrong={s['wrong']} "
		  f"p99={s['add_p99_ms']} ms  {'clean' if s['clean'] else 'NOT clean'}")
	return s


def _gaps(st, t_from, t_to):
	"""Longest wait between finished calls in [t_from, t_to]."""
	ts = [t_from] + [t for t, *_ in list(st.rows) if t_from <= t <= t_to] + [t_to]
	return round(max(b - a for a, b in zip(ts, ts[1:])), 2)


## ==========================================================================
##  Steps
## ==========================================================================

def step_ramp():
	failed = set()
	for hz in A["ramp_hz"]:
		live = _live()
		_begin("ramp", hz)
		_schedule_probes({st: hz for st in live})
		_supervise(A["ramp_step_s"])
		exp.schedule.clear("pico")
		_quiesce()
		for st in live:
			s = _end_stats(st, "ramp", hz)
			if st.name in failed:
				continue
			if s["clean"]:
				st.peak_hz = hz
			else:
				failed.add(st.name)
		if all(st.name in failed for st in _live()):
			break


def step_burst():
	live = _live()
	_begin("burst")
	for st in live:
		st.rate, st.burst_left = "burst", A["burst_s"]
		exp.schedule.every(0.1).seconds.do(_burst_job, st).tag("pico")
	_supervise(A["burst_s"] * len(live) + 60,
			   until=lambda: all(st.burst_left <= 0 or st.fatal for st in live))
	exp.schedule.clear("pico")
	_quiesce()
	for st in live:
		_end_stats(st, "burst", "burst")


def step_drill():
	live = _live()
	for st in live:
		for kind in ("reconnect", "machine_reset"):
			if st.fatal:
				break
			others = [o for o in _live() if o is not st]
			_begin(f"drill_{kind}", A["drill_hz"])
			_schedule_probes({o: A["drill_hz"] for o in others})
			_supervise(A["drill_settle_s"] / 2)
			st.paused = True
			_wait_idle(st, A["call_timeout_s"])
			t0 = time.monotonic()
			if kind == "reconnect":
				_release(st)
				ok = _reconnect_once(st)
			else:
				_send_machine_reset(st)
				_release(st)
				st.last_ticks = None
				ok = _wait_and_reconnect(st)
			ms = round((time.monotonic() - t0) * 1000)
			_event(st, f"drill_{kind}", f"{'ok' if ok else 'FAILED'} in {ms} ms, port {st.port}")
			if ok:
				st.need_recovery = None
			else:
				st.need_recovery = f"drill {kind} failed"
			st.paused = False
			_supervise(A["drill_settle_s"] / 2)
			exp.schedule.clear("pico")
			_quiesce()
			bad = {o.name: sum(1 for *_, oc, _ in list(o.rows) if oc != "ok") for o in others}
			st.drills.append({"kind": kind, "ok": ok, "ms": ms, "port": st.port,
							  "other_boards_failed_calls": bad})
			for o in others:
				_end_stats(o, f"drill_{kind}", A["drill_hz"])


def step_schedule_exception():
	live = _live()
	hz = A["drill_hz"]
	_begin("schedule_exception", hz)
	_schedule_probes({st: hz for st in live})
	_supervise(5)

	def _boom():
		raise RuntimeError("deliberate exception inside exp.schedule (pico_link_stress)")

	t_boom = time.monotonic()
	exp.schedule.every(1).seconds.do(_boom).tag("boom")
	_event(None, "schedule_exception_injected",
		   "a job that raises; a traceback from exp.schedule.loop is expected")
	_supervise(A["schedule_test_s"])
	th = getattr(exp.schedule, "thread", None)
	died = th is not None and not th.is_alive()
	after = {st.name: sum(1 for t, *_ in list(st.rows) if t > t_boom + 2) for st in live}
	answers = {st.name: _alive(st) for st in live} if died else {}
	exp.schedule.clear("boom")
	if died:
		exp.schedule.loop()                 # ExpScheduler starts a new thread
	t_r = time.monotonic()
	_supervise(5)
	resumed = {st.name: sum(1 for t, *_ in list(st.rows) if t > t_r) for st in live}
	exp.schedule.clear("pico")
	_quiesce()
	res = {"thread_died": died, "calls_after_exception": after,
		   "boards_answer_directly": answers, "restarted": died,
		   "calls_after_restart": resumed}
	REPORT["schedule_exception"] = res
	_event(None, "schedule_exception_result", json.dumps(res))
	for st in live:
		_end_stats(st, "schedule_exception", hz)


def step_schedule_hang():
	live = _live()
	hz = A["drill_hz"]
	_begin("schedule_hang", hz)
	_schedule_probes({st: hz for st in live})
	_supervise(5)
	fired = []

	def _sleepy():
		if not fired:
			fired.append(time.monotonic())
			time.sleep(A["schedule_hang_s"])

	exp.schedule.every(1).seconds.do(_sleepy).tag("hang")
	_event(None, "schedule_hang_injected", f"a job that sleeps {A['schedule_hang_s']} s")
	_supervise(A["schedule_hang_s"] + 15)
	exp.schedule.clear("hang")
	exp.schedule.clear("pico")
	_quiesce()
	res = {}
	if fired:
		t0, t1 = fired[0], fired[0] + A["schedule_hang_s"]
		for st in live:
			rows = list(st.rows)
			res[st.name] = {"longest_wait_s": _gaps(st, t0 - 1, t1 + 1),
							"calls_during_block": sum(1 for t, *_ in rows if t0 + 0.5 < t < t1 - 0.5),
							"calls_after_block": sum(1 for t, *_ in rows if t > t1 + 0.5)}
	REPORT["schedule_hang"] = res
	_event(None, "schedule_hang_result", json.dumps(res))
	for st in live:
		_end_stats(st, "schedule_hang", hz)


def step_pico_hang():
	hz = A["drill_hz"]
	res = {}
	for st in _live():
		live = _live()
		_begin("pico_hang", hz)
		_schedule_probes({o: hz for o in live})
		_supervise(3)
		n0 = st.n_recoveries
		t0 = time.monotonic()
		st.force_call = "hang"
		_event(st, "pico_hang_injected", "a call that loops on the board")
		_supervise(A["call_timeout_s"] + A["late_reply_s"] + 90,
				   until=lambda: st.fatal or (st.n_recoveries > n0 and not st.recovering))
		t1 = time.monotonic()
		res[st.name] = {"recovered_by": st.last_recovery if st.n_recoveries > n0 else None,
						"fatal": st.fatal, "seconds": round(t1 - t0, 1),
						"other_boards_longest_wait_s": {o.name: _gaps(o, t0, t1)
														for o in live if o is not st}}
		_supervise(3)
		exp.schedule.clear("pico")
		_quiesce()
		for o in live:
			_end_stats(o, f"pico_hang_{st.name}", hz)
	REPORT["pico_hang"] = res
	_event(None, "pico_hang_result", json.dumps(res))


def step_soak():
	live = _live()
	rates = {st: max(1, round(A["soak_fraction"] * (st.peak_hz or 1), 1)) for st in live}
	_begin("soak", "x".join(str(r) for r in rates.values()))
	_schedule_probes(rates)
	_supervise(A["soak_h"] * 3600)
	exp.schedule.clear("pico")
	_quiesce()
	for st in live:
		_end_stats(st, "soak", rates[st])


STEPS = {"ramp": step_ramp, "burst": step_burst, "drill": step_drill,
		 "schedule_exception": step_schedule_exception,
		 "schedule_hang": step_schedule_hang, "pico_hang": step_pico_hang,
		 "soak": step_soak}


## ==========================================================================
##  Discovery
## ==========================================================================

def _discover():
	devs, ports = [], set()
	for name, d in list(scope.devices.items()):
		if isinstance(d, SerialMPDevice) and d.connected:
			devs.append(_Dev(name, d, owned=False))
			ports.add(d.port)
	if A["include_unmounted"]:
		for i in range(16):
			d = SerialMPDevice(name=f"stress_{i}", connect="autoconnect", search_name=False)
			if not d.connected or d.port in ports:
				break
			## auto_connect only excludes a port on a name match; do it here so
			## the next board is searched for elsewhere, and so a reconnect of
			## this one looks for the same board name.
			SerialMPDevice.exclusion_list.append(d.port)
			d.search_name = d.board_name
			ports.add(d.port)
			name = str(d.board_name or f"stress_{i}")
			while name in {x.name for x in devs}:
				name += "_b"
			st = _Dev(name, d, owned=True)
			_guarded(st, d.exec_main, 30)
			devs.append(st)
	for st in devs:
		st.uid = _uid(st)
		ok, r = _guarded(st, lambda: st.dev('__import__("os").uname().release'), 5)
		st.mpy = str(r) if ok else ""
		for key, glob in (("tandh", "tandh"), ("light", "lit")):
			ok, r = _guarded(st, lambda g=glob: st.dev(f'int("{g}" in globals())'), 5)
			st.has[key] = ok and r == 1
		cyc = []
		for kind, w in A["mix"].items():
			if kind in ("tandh", "light") and not st.has.get(kind):
				continue
			cyc += [kind] * int(w)
		random.Random(st.uid or 0).shuffle(cyc)
		st.cycle = cyc or ["add"]
		_restore(st)
		info = {"port": st.port, "board": st.board, "uid": st.uid, "mpy": st.mpy,
				"owned": st.owned, "has": dict(st.has)}
		REPORT["devices"][st.name] = info
		exp.mstreams["picos"](device=st.name, port=st.port, board=str(st.board),
							  uid=str(st.uid), mpy=st.mpy,
							  has_tandh=int(st.has["tandh"]),
							  has_lit=int(st.has["light"])).panel()
	return devs


def _finish_devices():
	for st in DEVS:
		if not _idle(st):
			_release(st)                    # a call still blocked: free it
		if not st.owned and not st.dev.connected:
			_reconnect_once(st)             # leave the scope's own Pico usable
		if st.dev.connected and st.has.get("light"):
			_guarded(st, lambda s=st: s.dev("lit.setVs(0, 0, 0)"), 3)
		if st.owned and st.dev.device is not None:
			_guarded(st, st.dev.disconnect, 5)


## ==========================================================================
##  Kernel log
## ==========================================================================

global _dmesg_proc
_dmesg_proc = None


def start_kernel_log():
	global _dmesg_proc
	for cmd in (["stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["sudo", "-n", "stdbuf", "-oL", "dmesg", "--follow", "-T"],
				["dmesg", "--follow", "-T"]):
		f = None
		try:
			f = open("kernel.log", "a", buffering=1)
			_dmesg_proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
			time.sleep(0.8)
			with open("kernel.log", errors="replace") as r:
				tail = r.read()[-400:]
			bad = re.search(r"operation not permitted|password is required|not found|"
							r"read kernel buffer failed|invalid option", tail, re.I)
			if _dmesg_proc.poll() is None and not bad:
				return True
			try:
				_dmesg_proc.terminate(); _dmesg_proc.wait(timeout=3)
			except Exception:
				pass
			_dmesg_proc = None
		except Exception as e:
			log.error(f"kernel log ({cmd[0]}): {e}")
		finally:
			if f is not None:
				try:
					f.close()
				except Exception:
					pass
	return False


def stop_kernel_log():
	global _dmesg_proc
	if _dmesg_proc is not None:
		try:
			_dmesg_proc.terminate(); _dmesg_proc.wait(timeout=5)
		except Exception:
			try:
				_dmesg_proc.kill()
			except Exception:
				pass
		_dmesg_proc = None


_KTIME = re.compile(r"^\[(\w{3} \w{3}\s+\d+ \d\d:\d\d:\d\d \d{4})\]")
_KUSB = re.compile(r"usb \d+-[\d.]+:|cdc_acm|ttyACM|xhci|over-current|USB disconnect", re.I)
_KPICO = re.compile(r"cdc_acm|ttyACM|MicroPython|Board in FS mode", re.I)


def kernel_usb_events(text, since):
	"""USB lines in the run window, and the ones that name a Pico."""
	out, t = [], None
	for line in text.splitlines():
		m = _KTIME.match(line)
		if m:
			try:
				t = datetime.datetime.strptime(" ".join(m.group(1).split()),
											   "%a %b %d %H:%M:%S %Y")
			except ValueError:
				t = None
		if t is None or t < since:
			continue
		if _KUSB.search(line):
			out.append(line.strip())
	return out, [l for l in out if _KPICO.search(l)]


## ==========================================================================
##  Run
## ==========================================================================

def _acquisition_running():
	rc, out = _run("pgrep -af 'mjpeg_continuous|intensity_continuous|"
				   "mjpeg_sampling|light_perturbation|sampling_record' | "
				   "grep -v pgrep", timeout=5)
	return out.strip() if rc == 0 and out.strip() else ""


def start_acq_blocking():
	global exp, scope, A, DEVS, REPORT, STEP
	exp = Experiment.current
	scope = ScopeAssembly.current
	A = exp.attribs

	busy = _acquisition_running()
	if busy:
		print(Panel(f"[red]An acquisition appears to be running:\n{busy}\n\n"
					f"Refusing: this test takes over the Pico and the lights.",
					title="refused"))
		return

	exp.schedule.clear()
	th = getattr(exp.schedule, "thread", None)
	if th is None or not th.is_alive():
		exp.schedule.end_thread = False
		exp.schedule.loop()                 # the jobs below need a live scheduler
	_open_csvs()
	start_kernel_log()
	t_started = datetime.datetime.now()
	REPORT = {"started": str(t_started), "attribs": dict(A), "devices": {},
			  "events": [], "end": "completed"}
	DEVS, STEP = [], "discover"
	try:
		DEVS = _discover()
		if not DEVS:
			REPORT["end"] = "no MicroPython board found"
			print(Panel("[red]No MicroPython board found.", title="pico_link_stress"))
		for name in A["steps"]:
			if not _live():
				break
			fn = STEPS.get(name)
			if fn is None:
				_event(None, "unknown_step", name)
				continue
			fn()
	except _Fatal as e:
		REPORT["end"] = f"{e} could not be recovered (end_on_fatal)"
		_event(None, "run_ended", REPORT["end"])
	except KeyboardInterrupt:
		REPORT["end"] = "interrupted"
		print("\n[yellow]Interrupted. Cleaning up...")
	except Exception as e:
		REPORT["end"] = f"error: {type(e).__name__}: {e}"
		log.exception("pico_link_stress")
		_event(None, "run_error", REPORT["end"])
	finally:
		STEP = "cleanup"
		for tag in ("pico", "boom", "hang"):
			exp.schedule.clear(tag)
		try:
			_finish_devices()
		except Exception as e:
			log.error(f"finish devices: {e}")
		stop_kernel_log()
		_close_csvs()

	REPORT["finished"] = str(datetime.datetime.now())
	try:
		with open("kernel.log", errors="replace") as f:
			usb, pico = kernel_usb_events(f.read(), t_started)
	except Exception:
		usb, pico = [], []
	REPORT["kernel_usb_lines"], REPORT["kernel_pico_lines"] = usb, pico
	REPORT["throttled_seen"] = sorted(_sys["seen"])
	for st in DEVS:
		REPORT["devices"][st.name].update({
			"peak_hz": st.peak_hz, "fatal": st.fatal, "recoveries": dict(st.recov_total),
			"drills": st.drills, "steps": st.steps})
	with open("pico_stress.json", "w") as f:
		json.dump(REPORT, f, indent=2, default=str)
	_write_report(REPORT)
	cleanup()


def _write_report(R):
	L = [f"# Pico link stress -- {os.uname().nodename}", "",
		 f"- **Started** {R['started']}", f"- **Finished** {R.get('finished')}",
		 f"- **End** {R.get('end')}",
		 f"- **Steps** {', '.join(R['attribs'].get('steps', []))}", ""]
	for name, d in R["devices"].items():
		burst = next((s for s in d.get("steps", []) if s["step"] == "burst"), None)
		L += [f"## {name}", "",
			  f"- **Port** {d['port']}  **Board** {d['board']}  **uid** {d['uid']}  "
			  f"**MicroPython** {d['mpy']}  **Mounted by the scope** {'no' if d['owned'] else 'yes'}",
			  f"- **Peak (ramp)** {d.get('peak_hz') or 'no clean step'} Hz"
			  + (f"; **burst** {burst['achieved_hz']} calls/s, a+b p50 {burst['add_p50_ms']} ms, "
				 f"p99 {burst['add_p99_ms']} ms" if burst else ""),
			  f"- **Recoveries** {d.get('recoveries') or 'none'}; **fatal** "
			  f"{'YES' if d.get('fatal') else 'no'}"]
		for dr in d.get("drills", []):
			L.append(f"- **Drill {dr['kind']}** {'ok' if dr['ok'] else 'FAILED'} in "
					 f"{dr['ms']} ms (port {dr['port']}); failed calls on the other "
					 f"boards: {dr['other_boards_failed_calls'] or 'none'}")
		L += ["", "| step | Hz | n | ok | timeouts | errors | wrong | a+b p50 ms | "
			  "a+b p99 ms | max ms | achieved Hz | recoveries |",
			  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
		L += [f"| {s['step']} | {s['rate_hz']} | {s['n']} | {s['ok']} | {s['timeouts']} | "
			  f"{s['errors']} | {s['wrong']} | {s['add_p50_ms']} | {s['add_p99_ms']} | "
			  f"{s['max_ms']} | {s['achieved_hz']} | {s['recovered_by'] or '-'} |"
			  for s in d.get("steps", [])]
		L.append("")
	L += ["## exp.schedule", ""]
	if "schedule_exception" in R:
		x = R["schedule_exception"]
		L.append(f"- **A job raised:** scheduler thread died: "
				 f"{'YES' if x['thread_died'] else 'no'}; calls after it: "
				 f"{x['calls_after_exception']}; boards answered when called directly: "
				 f"{x['boards_answer_directly'] or '-'}; calls after restart: "
				 f"{x['calls_after_restart']}")
	if "schedule_hang" in R:
		L.append(f"- **A job blocked {R['attribs'].get('schedule_hang_s')} s:** "
				 f"{R['schedule_hang']}")
	if "pico_hang" in R:
		for name, x in R["pico_hang"].items():
			L.append(f"- **Hung call on {name}:** recovered by {x['recovered_by'] or 'nothing'} "
					 f"after {x['seconds']} s; longest wait on the other boards meanwhile: "
					 f"{x['other_boards_longest_wait_s'] or '-'}")
	L += ["", "## System", "",
		  f"- **Throttled flags seen** {', '.join(R.get('throttled_seen') or []) or 'none read'}",
		  f"- **Kernel USB lines in the run window** {len(R.get('kernel_usb_lines', []))} "
		  f"(naming a Pico: {len(R.get('kernel_pico_lines', []))})", ""]
	L += [f"    {l}" for l in R.get("kernel_usb_lines", [])[:200]]
	L += ["", "Every call in `calls.csv`; recoveries, drills and resets in `events.csv`; "
		  "1 Hz throttled flags and scheduler state in `system.csv`; kernel messages in "
		  "`kernel.log`."]
	with open("REPORT.md", "w") as f:
		f.write("\n".join(L) + "\n")


def cleanup():
	"""Save, offload, stop the schedule. Does NOT close -- exp.close() joins
	the scheduler thread. Type exp.close() afterwards."""
	global exp
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True
	exp.__save__()
	try:
		print(exp.mstreams["steps"].tabulate("step", "device", "rate_hz", "n", "timeouts",
											 "errors", "wrong", "add_p99_ms"))
	except Exception:
		pass
	exp.sync_dir()
	exp.note(f"Pico link stress run finished: {REPORT.get('end')}.")
	print(Panel("[yellow]Done. The experiment is still OPEN -- type "
				"[bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel("create_exp() -> start_acq_blocking()\n\n"
				"Stress-tests every MicroPython board on the scope through exp.schedule.",
				title="pico_link_stress"))
