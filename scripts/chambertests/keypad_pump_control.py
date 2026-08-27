"""Drive the perfusion pumps from the RGB keypad. REAL PUMPS -- fluid moves.

There is no simulation here. The rehearsal twin is scripts/toyexps/keypad_pump_test.py.

	create_exp()     make the experiment record
	connect()        bind the boards, push the envelope, preflight
	start()          live view + keypad polling; Ctrl-C stops it
	status()         one-shot table
	stop()           stop the pumps, close the record
	panic()          stop everything, now, no questions

	link()           link health;  resume()  leaves a DOWN link and retries
	envelope()       show it;  set_envelope(3, fast_speed=0.4)  changes it
	push_to_keypad() mirror pump state onto the LEDs once, by hand

Everything else lives in actuators.pumps. This file used to carry its own fork of
all of it -- 1807 lines, ~700 of them duplicated from the package it did not
import. See "WHAT CHANGED" at the bottom.

--------------------------------------------------------------------- the rules
The board owns the pumps. Hardware PWM and a board-side timer keep them running
through host loss, hangs and reconnects; the board does not stop because the host
went away. Stopping takes an explicit command or pulling power.

The host owns the SPEED ENVELOPE. connect() pushes it, so retuning a pump is an
edit here plus a reconnect -- no reflash. The firmware constants are only defaults
for a cold boot with nobody attached.

Nothing in the render loop is allowed to block. All board access goes through
LinkSupervisor: one lock, recovery on its own thread, bounded, with a terminal
DOWN state. That is the entire fix for the freeze this script used to have.
"""

import logging as log
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from hive.assembly import ScopeAssembly
## expframework.experiment, NOT experiment -- there is no top-level `experiment`
## module in this repo. Every other script here (livetrack.py,
## keypad_pump_test.py, and this file before the rework) uses the full path.
from expframework.experiment import Experiment

from actuators.pumps import RemotePumpSet, KeypadLink, Dashboard, parse_line
from actuators.pumps import envelope as env
from actuators.pumps.remote import hard_reset
from actuators.pumps.supervisor import LinkSupervisor

## ---------------------------------------------------------------- envelope
## PULSE_PERIOD_S is the whole cycle: one 5 s burst per minute, so the off-time
## is the period minus the on-time. Change the period; the duty is derived.
PULSE_ON_S     = 5
PULSE_PERIOD_S = 60
PULSE_OFF_S    = PULSE_PERIOD_S - PULSE_ON_S

ENVELOPE = {
	1: {"fast_speed": 0.5,  "slow_min": 0.03, "slow_max": 0.20,
		"slow_speed": 0.10, "pulse_duty": (PULSE_ON_S, PULSE_OFF_S),
		"continuous": False, "kick": (0.0, 0)},
	2: {"fast_speed": 0.5,  "slow_min": 0.03, "slow_max": 0.20,
		"slow_speed": 0.10, "pulse_duty": (PULSE_ON_S, PULSE_OFF_S),
		"continuous": False, "kick": (0.0, 0)},
	## pump3 (DFR0523, aeration). Do NOT lower these to reduce aeration: the
	## DFR0523 stalls long before it slows down usefully. Below roughly 0.5 the
	## head hums and the rotor stays put under tube occlusion -- that reads as a
	## control fault but it is a torque floor. To aerate less, duty-cycle it
	## (continuous False + pulse_duty): same drive per revolution, fewer
	## revolutions. The kick only has to break stiction, so it sits at full drive.
	3: {"fast_speed": 1.0, "slow_min": 0.45, "slow_max": 1.0,
		## slow_speed at the top of the band: aeration runs flat out in speed
		## control mode. Same drive as POWER mode for this pump, by design --
		## band max and fast_speed are both 1.0. Yatharth, 26 Aug.
		"slow_speed": 1.0, "continuous": True, "kick": (1.0, 1000)},
}

PUMP_NUMBERS = (1, 2, 3)
PUMP_ROLES   = {1: "perfusion", 2: "perfusion", 3: "aeration"}
CALIBRATED   = (1, 2)          ## pumps whose params shelve holds a calibration

## Round-trip budget. These are the numbers that decide how hard the raw REPL is
## being driven, and the raw REPL is the thing that breaks.
##
## KEYPAD board and PUMP board are separate ports, so their rates are separate
## costs. Keypad polling has to stay fast or button presses feel laggy; pump
## state only feeds a display, and a display does not need 10 Hz.
POLL_S       = 0.10            ## keypad drain -- keypad board, 10/s
STATE_S      = 0.50            ## pump state read -- pump board, 2/s
FPS          = 8               ## live view refresh, drawn from the last state

## The host -> keypad LED mirror is GONE from the live loop. See start().
MIRROR_S     = None            ## kept so old calls do not raise; ignored

## ---------------------------------------------------------------- state
scope   = None
exp     = None
PUMPSET = None
LINK    = None                 ## LinkSupervisor
KEYPAD  = None                 ## KeypadLink
BOARD   = None                 ## Dashboard
RUNNING = False

## ONE console for the whole script. The old version passed redirect_stdout=False
## to Live() and then used `from rich import print`, i.e. a second Console with
## its own lock and its own idea of where the cursor is. The two interleaved ANSI
## cursor moves on one TTY, rich fell back to full clear-and-redraws, and because
## transient=False every one of those stayed in the emulator's scrollback. That
## is what made the terminal sluggish before it hung.
CONSOLE = Console()
_LIVE = None


def emit(msg):
	"""Print without fighting the live display. Use this, never bare print()."""
	if _LIVE is not None:
		_LIVE.console.print(msg)
	else:
		CONSOLE.print(msg)


def role(n):
	return PUMP_ROLES.get(n, "perfusion")


def is_aeration(n):
	return role(n) == "aeration"


## ---------------------------------------------------------------- setup
def create_exp():
	global exp, scope
	scope = ScopeAssembly.current
	exp = Experiment.Construct(["keypad", "pump", "control"],
								user=True, eid=True, date=True, time=True,
								scopeid=True)
	exp.new_measurementstream("keypress",
								measurements=["pump", "verb", "value", "applied_speed"])
	exp.attribs["pumps"] = list(PUMP_NUMBERS)
	exp.attribs["simulated"] = False
	exp.attribs["fluid_moved"] = True
	exp.attribs["poll_period_s"] = POLL_S
	exp.attribs["ml_per_min"] = {}
	emit("[green]Experiment ready.[/] Now run connect().")
	return exp


def _on_incident(inc):
	"""Bounded bookkeeping. The old code did
	    exp.logs["link_incidents"] = list(LINK_INCIDENTS)
	on every single incident -- a full copy of an unbounded list, O(n^2), inside
	the render loop. Append to the log, and let the supervisor's deque cap it."""
	if exp is None:
		return
	exp.logs.setdefault("link_incidents", []).append(inc)
	del exp.logs["link_incidents"][:-200]


def connect(numbers=PUMP_NUMBERS):
	"""Bind the boards, push the envelope, preflight.

	Refuses rather than half-starting: without scope.pumpset there is nothing to
	drive, and without scope.kp there is nothing to drive it with.
	"""
	global scope, PUMPSET, LINK, KEYPAD, BOARD
	scope = ScopeAssembly.current

	missing = [name for name in ("pumpset", "kp")
				if getattr(scope, name, None) is None]
	if missing:
		emit("[red]Not connected:[/] scope.{} missing.".format(
				" and scope.".join(missing)))
		emit("  [dim]Mount the Picos first -- pump board running "
				"2ch_peristat_kitroniks_vx_shield, keypad running "
				"pimoroni_rgb_keypad_pumpctrl.[/dim]")
		return None

	if LINK is not None:
		LINK.stop()

	PUMPSET = RemotePumpSet(numbers=numbers)
	LINK = LinkSupervisor(PUMPSET, on_incident=_on_incident).start()
	KEYPAD = KeypadLink()
	BOARD = Dashboard(PUMPSET, roles=PUMP_ROLES)

	emit("[yellow]REAL PUMPS[/] via scope.pumpset -> {}".format(PUMPSET.numbers()))
	if exp is not None:
		exp.attribs["backend"] = "RemotePumpSet"

	emit("[bold]Applying speed envelope[/bold]")
	env.push(ENVELOPE, PUMPSET, LINK, emit=emit)
	env.verify(ENVELOPE, LINK.state(), emit=emit)
	if exp is not None:
		exp.attribs["envelope"] = dict((k, dict(v)) for k, v in ENVELOPE.items())

	cal = BOARD.load_calibration(refresh=True)
	BOARD.reset_volumes()
	if cal:
		emit("[green]Calibration loaded[/] for pump(s) {}".format(sorted(cal)))
	else:
		emit("[dim]No calibration on any pump -- the live view will show "
				"'no calib' instead of a volume. Run the calibration script.[/dim]")
	preflight()
	return PUMPSET


def preflight(verbose=True):
	"""Is this rig fit to start? Reports, never fixes."""
	if LINK is None:
		emit("[red]Run connect() first.[/]")
		return False
	ok = True
	states = LINK.state()
	if not states:
		emit("[red]Pumps did not answer.[/] {}".format(LINK.summary()))
		return False
	if not KEYPAD.available():
		emit("[red]No keypad mounted[/] -- scope.kp is missing.")
		ok = False
	bad = env.diff(ENVELOPE, states)
	if bad:
		ok = False
		if verbose:
			env.verify(ENVELOPE, states, emit=emit)
	running = [n for n, st in states.items() if st.get("fast") or st.get("pulse")]
	if running:
		emit("[yellow]Already running:[/] pump(s) {} -- the board kept them going "
				"across the reconnect, which is by design.".format(sorted(running)))
	if verbose and ok:
		emit("[green]Preflight clear.[/] start() when ready.")
	return ok


## ---------------------------------------------------------------- envelope
def envelope():
	"""What the host will push, beside what the board currently reports."""
	states = LINK.state() if LINK is not None else {}
	table = Table(title="speed envelope -- host vs board")
	for col in ("pump", "role", "fast", "band", "set", "duty", "kick", "board"):
		table.add_column(col)
	bad = env.diff(ENVELOPE, states) or {}
	for n in sorted(ENVELOPE):
		s = ENVELOPE[n]
		table.add_row(str(n), role(n),
						str(s.get("fast_speed")),
						"{}-{}".format(s.get("slow_min"), s.get("slow_max")),
						str(s.get("slow_speed")),
						str(s.get("pulse_duty", "continuous")),
						str(s.get("kick")),
						"[red]MISMATCH[/]" if n in bad else "[green]ok[/]")
	CONSOLE.print(table)
	return dict(ENVELOPE)


def set_envelope(n, apply_now=True, **kwargs):
	"""set_envelope(3, fast_speed=0.4, slow_max=0.45) -- change and push."""
	try:
		spec = env.update(ENVELOPE, n, **kwargs)
	except ValueError as err:
		emit("[red]{}[/]".format(err))
		return None
	if apply_now and LINK is not None:
		env.push(ENVELOPE, PUMPSET, LINK, numbers=[n], emit=emit)
		env.verify(ENVELOPE, LINK.state(), numbers=[n], emit=emit)
	return spec


## ---------------------------------------------------------------- link
def link():
	"""Link health. Never touches the port -- safe to call any time."""
	if LINK is None:
		emit("[red]Not connected.[/]")
		return None
	h = LINK.health()
	emit("[bold]{}[/bold]".format(LINK.summary()))
	if not h["repair_thread"]:
		emit("[red]The repair thread is not alive[/] -- run connect() again.")
	for inc in LINK.incidents(5):
		emit("  [dim]{}  {}  {}[/dim]".format(
				time.strftime("%H:%M:%S", time.localtime(inc["t"])),
				inc["where"], inc["error"][:80]))
	return h


def resume():
	"""Leave a DOWN link and start trying again. Deliberately manual."""
	if LINK is None:
		return False
	emit("[yellow]Retrying the link.[/]")
	return LINK.resume()


def reset_board(wait_s=3.0):
	"""Reboot the pump Pico. The pumps stop for the couple of seconds it takes;
	the circuit restores them from pumpstate.txt on the way up."""
	ok = hard_reset("pumpset", wait_s=wait_s)
	if ok and LINK is not None:
		LINK.resume()
	return ok


## ---------------------------------------------------------------- the loop
def _apply_line(line):
	"""One keypad line -> one pump command. Returns True if it went out."""
	parsed = parse_line(line)
	if parsed is None:
		return False
	n, verb, value = parsed
	if verb == "LIMIT":
		return True                          ## keypad UI feedback, nothing to do
	if not LINK.command(line):
		return False
	if exp is not None:
		try:
			exp.keypress.add(pump=n, verb=verb, value=value, applied_speed=None)
		except Exception as err:
			log.debug("keypress record failed: %s", err)
	return True


def start(duration_min=None, fps=FPS, poll_s=POLL_S, state_s=STATE_S,
			mirror_s=None):
	"""Poll the keypad and render the live view until Ctrl-C.

	Owns the terminal. Nothing in here blocks on serial: LinkSupervisor.state()
	returns the last good snapshot if the board is unwell, and recovery happens
	on its own thread. If the link goes DOWN the view keeps drawing and says so.

	NO LED MIRROR. The loop no longer pushes pump state back onto the keypad.
	While start() owns the terminal the trappyscopes REPL is blocked, so nothing
	can drive the pumps through the API -- the keypad is the only thing changing
	pump state, and it already knows what it sent. The mirror was reflecting the
	keypad's own commands back at it. Yatharth's call, 26 Aug, and it is right:
	it removes the second board from the loop entirely.

	STATE IS POLLED AT 2 Hz, NOT AT LOOP RATE. The previous version called
	LINK.state() on every iteration -- 10 pump round trips a second, feeding a
	display that refreshes at 8 fps. Every round trip is a chance for the raw
	REPL to desynchronise, and desynchronisation is the failure. Pump-board
	traffic per second: was ~11 (10 state + 1 mirror), now 2.
	"""
	global RUNNING, _LIVE
	if LINK is None:
		emit("[red]Run connect() first.[/]")
		return
	if RUNNING:
		emit("[yellow]Already running.[/]")
		return
	if mirror_s is not None:
		emit("[dim]mirror_s is ignored -- the LED mirror was removed from the "
				"live loop. Use push_to_keypad() by hand if you want one.[/dim]")

	RUNNING = True
	t0 = time.monotonic()
	deadline = t0 + duration_min * 60 if duration_min else None
	next_poll = next_state = 0.0
	states = {}
	applied = skipped = 0

	## auto_refresh=False: the old version left Live's own 12 Hz refresh thread
	## running AND called update() at 12 Hz, so every panel was rendered and
	## written twice per frame for no benefit.
	display = Live(BOARD.frame(LINK.state(), t0, banner=LINK.summary()),
					console=CONSOLE, auto_refresh=False, transient=False,
					redirect_stdout=True, redirect_stderr=True)
	display.start()
	_LIVE = display
	try:
		while True:
			now = time.monotonic()
			if deadline and now >= deadline:
				emit("[yellow]Duration reached.[/]")
				break

			## Keypad board: drained fast, because latency here is felt.
			if now >= next_poll:
				next_poll = now + poll_s
				for line in (KEYPAD.lines() or []):
					if _apply_line(line):
						applied += 1
					else:
						skipped += 1

			## Pump board: read slowly, because this only feeds a display.
			## A command sent above already refreshed what matters; the operator
			## sees the button light on the keypad immediately either way.
			if now >= next_state:
				next_state = now + state_s
				states = LINK.state()

			display.update(BOARD.frame(states, t0, banner=LINK.summary()),
							refresh=True)

			if LINK.status() == "down":
				emit("[red]{}[/]".format(LINK.summary()))
				break

			time.sleep(max(0.0, next_poll - time.monotonic()))
	except KeyboardInterrupt:
		emit("\n[yellow]Stopped by hand.[/]")
	finally:
		RUNNING = False
		_LIVE = None
		try:
			display.stop()
		except Exception:
			pass
		## Do NOT touch the board here beyond one bounded call. The old finally
		## block ran stop_all() + mirror_once() + status(), each of which fed
		## straight back into the inline relink -- so the first Ctrl-C escaped the
		## loop and immediately blocked again in the shutdown path. That is why
		## one Ctrl-C appeared not to work.
		emit("[dim]{} commands applied, {} skipped. Pumps are STILL RUNNING -- "
				"stop() or panic() to stop them.[/dim]".format(applied, skipped))
		emit(LINK.summary())


def push_to_keypad():
	"""Mirror pump state onto the keypad LEDs, once, by hand.

	The live loop does NOT do this any more (see start()). This is here for the
	case the loop cannot cover: you changed pump state from the REPL, outside
	start(), and want the LEDs to agree again. Quiet -- it emits no commands, so
	it cannot bounce back as fresh keypad input.
	"""
	if LINK is None:
		emit("[red]Run connect() first.[/]")
		return []
	states = LINK.state()
	if not states:
		emit("[red]No pump state to mirror.[/] {}".format(LINK.summary()))
		return []
	touched = KEYPAD.sync(states)
	emit("[green]Keypad LEDs synced[/] for pump(s) {}".format(touched))
	return touched


def status():
	"""One-shot table. Safe while start() is running."""
	if LINK is None:
		emit("[red]Not connected.[/]")
		return None
	states = LINK.state()
	if not states:
		emit("[red]No answer from the pumps.[/] {}".format(LINK.summary()))
		return None
	CONSOLE.print(BOARD.table(states))
	emit(LINK.summary())
	return states


def stop():
	"""Stop the pumps and close the record."""
	if LINK is None:
		emit("[red]Not connected.[/]")
		return False
	ok = LINK.stop_all()
	emit("[green]Pumps stopped.[/]" if ok else
			"[red]Could not stop the pumps[/] -- {}".format(LINK.summary()))
	if exp is not None:
		try:
			exp.attribs["volumes_ml"] = BOARD.volumes()
			exp.attribs["runtimes_s"] = BOARD.runtimes()
			exp.save()
		except Exception as err:
			log.error("saving the experiment failed: %s", err)
	return ok


def panic():
	"""Stop everything, now. Bypasses the supervisor's DOWN state."""
	emit("[bold red]PANIC[/bold red]")
	try:
		ScopeAssembly.current.pumpset.stop_all()
		emit("[green]Pumps stopped.[/]")
		return True
	except Exception as err:
		emit("[red]Direct stop failed:[/] {}".format(err))
		emit("  [dim]The board keeps pumping without the host. "
				"reset_board(), or pull the pump supply.[/dim]")
		return False


def shutdown():
	"""Release the repair thread. Call before dropping the script."""
	if LINK is not None:
		LINK.stop()
	return True


emit("[bold]keypad_pump_control[/bold] -- REAL PUMPS. "
		"create_exp() -> connect() -> start()")


# ============================================================ WHAT CHANGED
# 1807 lines -> 500, of which ~200 is the WHAT CHANGED note and the docstrings.
#
# THE FREEZE
# `relink()` was called from inside `_frame()`, the render function of the rich
# Live view. It does exit_raw_repl()/enter_raw_repl(), both blocking serial
# reads, and pyserial's timeout was never set. `LINK_FAILS` was only ever reset
# on SUCCESS, so once the raw REPL desynchronised, `LINK_FAILS % RELINK_AFTER`
# fired a fresh blocking relink every third failure, forever, at ~10 Hz. All of
# it on the thread that owned the terminal.
#
# The trigger underneath: `orphans = stop_jobs(quiet=True)` sat AFTER the
# `return _blocking_loop(...)` early return, so scheduler jobs from an earlier
# start(scheduled=True) -- or from a ScriptEngine re-exec, which resets JOBS
# while the registered jobs keep firing -- kept hitting the same serial port at
# 20 Hz. Two threads on one raw REPL, no lock anywhere in the file. They only
# collide when their round trips overlap, which is why onset was random.
#
# Now: every board call goes through LinkSupervisor -- one lock, recovery on a
# dedicated thread, exponential backoff, MAX_REPAIR_ATTEMPTS, then a terminal
# DOWN state that stops touching the port and says so. The loop only reads
# state(), which returns the last good snapshot instead of raising.
#
# THE SLUGGISH TERMINAL
# `redirect_stdout=False` plus `from rich import print` meant two Consoles with
# separate locks writing to one TTY. rich's incremental repaint was computed
# against a cursor that had moved underneath it, so it fell back to full
# clear-and-redraws -- and with transient=False every one stayed in scrollback.
# During a relink storm that was 3-4 rich-formatted lines per relink at ~10/s.
# Now: one Console, everything through emit(), auto_refresh=False.
#
# `LINK_INCIDENTS` was an unbounded list, and every append also did
# `exp.logs["link_incidents"] = list(LINK_INCIDENTS)` -- a full copy, O(n^2),
# in the hot path, each entry holding the board's traceback text. Now a
# deque(maxlen=200) with an append-only hook.
#
# Round-trip budget was ~36/s across two boards at 20-30 ms each, i.e. no
# headroom at all -- one slow board-side moment and replies land outside their
# window. poll 0.05 -> 0.10, fps 12 -> 8, and push_to_keypad() no longer fetches
# state() a second time when the caller already has it. ~36/s -> ~12/s.
#
# Ctrl-C: the finally block ran stop_all() + mirror_once() + status(), each of
# which fed back into the inline relink, so the first Ctrl-C escaped the loop and
# blocked again immediately. The shutdown path no longer touches the board.
#
# DELETED (~700 lines were verbatim forks of actuators/pumps/, which this file
# never imported): RemotePumpSet, parse_line, _reprs_to_lines, _read_keypad,
# _snapshot_diff, link_check, relink, _pump_device, load_calibration,
# rate_ml_min, _accrue, volumes, runtimes, reset_volumes, _setpoint, _flow_style,
# _tube, _bar, _frame, animate, _states_or_warn, status, _sync_dir.
# Dead on top of that: set_read_method, calibrate, find_floor, persist,
# calibration, show_calibration, the module-level set_slow_limits /
# set_fast_speed / set_pulse_duty / stop_all shadows, link_incidents,
# RemotePumpSet.get/commands/set_continuous/deinit, and the geometry/level
# machinery (geometry, _ratio, level_in, level_out, prime).
# The scheduled-jobs path (start(scheduled=True), poll_once, mirror_once,
# stop_jobs, jobs, is_running, _emit's JOBS registry) is gone entirely -- it was
# the source of the second thread, and the inline loop was always the one used.
