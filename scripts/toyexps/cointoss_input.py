"""
AI Generated -- new file, Claude (Anthropic), 2026-10-10.

Coin-toss experiment driven by hand-entered measurements -- the third
cointoss fixture, alongside cointoss.py (ScriptEngine) and
cointoss_protocol.py (Protocol engine). This one exists to exercise
MeasurementStream.input(), the dialog-box entry path added in
expframework/measurement.py, and core.idioms.formdialog underneath it.

Coin tosses are the right test subject precisely because nothing here is
instrumented: every value is typed by a person, which is the case input()
is for.

author: Claude (Anthropic), for Yatharth Bhasin
date: 2026-10-10
"""

import random

import yaml
from rich import print
from rich.panel import Panel
from rich.table import Table

from expframework.experiment import Experiment


__description__ = """
Test fixture for MeasurementStream.input(). Tosses a coin and logs each
toss through the dialog box rather than through code, then reads the
experiment back off disk with a plain yaml.safe_load to confirm every
typed value survived the round trip.

    create_exp()      build the experiment and its two streams
    link()            rebind tosses/runs after exp = findexp()
    toss()            log one toss through the dialog
    record_run()      log a whole run as a list -- the tuple/list case
    simulate(n)       log n tosses in code, as a reference for the shapes
    summary()         tally what was recorded
    verify()          THE TEST -- can a plain read get the values back?
    cleanup()         save, and leave the experiment open to inspect
"""

def link():
	"""Rebind the `exp`, `tosses` and `runs` globals to the CURRENT experiment.

	Call this after `exp = findexp()`. Reopening an experiment rebuilds
	exp.mstreams from expstate.pickle, so the globals bound by create_exp()
	point at orphaned stream objects -- readings keep going into those while
	exp.mstreams holds fresh, empty ones with the same measureid. The symptom
	is exp.mstreams["tosses"] reporting readings: 0 while toss() is plainly
	recording.

	The functions in this script do not need it: they call stream() and look
	the stream up each time. This is for typing `tosses.edit()` at the prompt.
	"""
	global exp, tosses, runs
	exp = Experiment.current
	tosses, runs = stream("tosses"), stream("runs")
	print(f"Linked to {exp.eid}: tosses ({len(tosses.readings)} readings), "
		  f"runs ({len(runs.readings)} readings)")


def stream(name):
	"""Look a stream up on the CURRENT experiment, every time.

	Deliberately not a cached global. findexp() closes the open experiment and
	rebuilds exp.mstreams from expstate.pickle, so any stream object a script
	captured at create_exp() time is orphaned: readings keep going into the old
	object while exp.mstreams holds a fresh, empty one carrying the same
	measureid. The result looks like data loss -- exp.mstreams["tosses"] reports
	readings: 0 while toss() is plainly recording -- when in fact there are two
	objects and the script is holding the wrong one.

	metaexperiment.py works around the same trap with link_objects(), which
	rebinds the globals by hand. Looking up each time needs no remembering.
	"""
	return Experiment.current.mstreams[name]


def field(reading, key, default=None):
	"""Read one field out of a Measurement.

	`reading.get(key)` does NOT work. Measurement subclasses dict (via
	ExpEvent -> TSEvent(dict)) but overrides `get` with a zero-argument method
	that returns self (expframework/measurement.py), so the inherited
	dict.get(key, default) is shadowed and any normal use raises
	`TypeError: get() takes 1 positional argument but 2 were given`.

	Calling the unbound dict.get explicitly goes around the override. Plain
	dicts -- anything read back from YAML -- can use .get() normally.
	"""
	return dict.get(reading, key, default)


print("Use create_exp(), then toss() to log a toss through the dialog box.")
print("After exp = findexp(), call link() to rebind tosses/runs to it.")
print("Use verify() afterwards to check the values survived the YAML round trip.")


def create_exp():
	"""Two streams, chosen to exercise different parts of the dialog.

	`tosses` mixes measurements with monitors and declares a unit, so the
	dialog has something to group, label and annotate. Its monitors are the
	fields that repeat across a session, which is what carry_forward is for.

	`runs` holds a sequence typed as a literal -- the case that used to be
	written as a !!python/tuple and become unreadable on a plain load.
	"""
	global exp, tosses, runs
	exp = Experiment.Construct(["test", "measurement_input", "coin_toss"])

	tosses = exp.new_measurementstream("tosses")
	tosses.add_measurement("outcome", axis_label="outcome", description="H or T")
	tosses.add_measurement("rotations", axis_label="rotations", unit="turns",
						   description="full rotations before landing")
	tosses.add_monitor("tosser", description="who flipped it")
	tosses.add_monitor("coin", description="which coin")
	tosses.add_monitor("surface", description="what it landed on")

	runs = exp.new_measurementstream("runs")
	runs.add_measurement("sequence", axis_label="sequence",
						 description="the whole run, e.g.  'H','T','H','H'")
	runs.add_measurement("n_heads", axis_label="n_heads")
	runs.add_monitor("tosser")

	print(Panel("tosses : outcome, rotations [turns] | tosser, coin, surface\n"
				"runs   : sequence, n_heads | tosser",
				title="streams"))


def toss(carry_forward=True):
	"""Log one toss through the dialog box.

	carry_forward is on by default here because tosser / coin / surface do
	not change between tosses in a session, and retyping them is exactly
	where a transcription error would come from. outcome and rotations are
	measurements, so they are never carried -- repeating a measured value
	would be fabrication, and you should see them blank every time.
	"""
	tosses = stream("tosses")
	reading = tosses.input(carry_forward=carry_forward)
	if reading is None:
		print("[yellow]Cancelled -- nothing recorded.")
		return None
	print(f"Toss #{len(tosses.readings)}: [bold]{field(reading, 'outcome')}[/bold]")
	return reading


def record_run():
	"""Log a whole run as a typed sequence.

	Type the sequence as a literal, e.g.   'H','T','H','H'
	ast.literal_eval reads that as a tuple; parse_value coerces it to a
	list, because yaml.dump writes a tuple as !!python/tuple and
	yaml.safe_load cannot construct one -- which is why `cell_counts.counts`
	is unreadable without extended parsing today. verify() below is what
	proves the coercion is doing its job.
	"""
	runs = stream("runs")
	reading = runs.input()
	if reading is None:
		print("[yellow]Cancelled -- nothing recorded.")
		return None
	seq = field(reading, "sequence")
	print(f"Run of {len(seq) if hasattr(seq, '__len__') else '?'}: {seq!r} "
		  f"({type(seq).__name__})")
	return reading


def simulate(n=5, tosser="simulator"):
	"""Log n tosses in code, bypassing the dialog.

	Not a shortcut -- a reference. These rows are written through the same
	__call__ the dialog ends in, so comparing a typed row against a
	simulated one shows whether the dialog produced the same shapes and
	types, independently of whether it looked right on screen.
	"""
	tosses = stream("tosses")
	for _ in range(n):
		tosses(outcome=random.choice(["H", "T"]),
			   rotations=random.randint(2, 9),
			   tosser=tosser, coin="2 euro", surface="bench")
	print(f"Simulated {n} tosses as {tosser}.")


def summary():
	"""Tally what was recorded, and show the typed and simulated rows
	side by side so a shape mismatch is visible."""
	tosses, runs = stream("tosses"), stream("runs")
	table = Table(title="tosses")
	for column in ("#", "outcome", "rotations", "tosser", "coin", "surface"):
		table.add_column(column)
	for i, r in enumerate(tosses.readings):
		table.add_row(str(i), *[f"{field(r, k)!r}" for k in
								("outcome", "rotations", "tosser", "coin", "surface")])
	print(table)

	outcomes = [field(r, "outcome") for r in tosses.readings]
	heads = sum(1 for o in outcomes if str(o).upper().startswith("H"))
	print(Panel(f"{len(outcomes)} tosses -- {heads} heads, {len(outcomes)-heads} tails",
				title="tally"))

	for r in runs.readings:
		seq = field(r, "sequence")
		print(f"run: {seq!r}  ({type(seq).__name__})")


def verify():
	"""THE TEST: read experiment.yaml back with a plain yaml.safe_load and
	check every recorded value survived.

	This is the check that matters. A value can be written without error and
	still be unrecoverable: yaml.dump happily writes a numpy scalar or a
	tuple with a !!python/ tag that safe_load refuses or silently drops. The
	failure shows up not at write time but weeks later, when the column
	reads as None.

	Compares what is in memory against what a plain reader gets back,
	matching rows on (measureid, measureidx).
	"""
	global exp
	exp = Experiment.current
	tosses, runs = stream("tosses"), stream("runs")
	exp.__save__()
	path = exp.log_file

	try:
		with open(path) as f:
			on_disk = yaml.safe_load(f)
	except Exception as e:
		print(Panel(f"[red]experiment.yaml cannot be read with yaml.safe_load at all:\n"
					f"{type(e).__name__}: {e}\n\n"
					f"Something was written with a !!python/ tag. Nothing in this "
					f"file is safely readable until that value is fixed.",
					title="verify :: FAIL"))
		return False

	rows = {(r.get("measureid"), r.get("measureidx")): r
			for r in (on_disk.get("results") or [])}

	problems = []
	checked = 0
	for stream in (tosses, runs):
		declared = stream.fields()
		for reading in stream.readings:
			key = (field(reading, "measureid"), field(reading, "measureidx"))
			row = rows.get(key)
			if row is None:
				problems.append(f"{stream.name} #{key[1]}: row missing from disk")
				continue
			for name in declared:
				want = field(reading, name)
				if want != want or want is None:      ## Nan or absent in memory
					continue
				checked += 1
				got = row.get(name)   ## plain dict from YAML -- .get() is fine here
				if got is None:
					problems.append(f"{stream.name} #{key[1]} {name}: "
									f"{want!r} in memory, None on disk "
									f"-- dropped by the safe read")
				elif got != want:
					problems.append(f"{stream.name} #{key[1]} {name}: "
									f"{want!r} ({type(want).__name__}) in memory, "
									f"{got!r} ({type(got).__name__}) on disk")

	ok = not problems
	print(Panel(f"{checked} recorded values checked against {path}\n\n"
				+ ("[green]All survived a plain yaml.safe_load."
				   if ok else "[red]" + "\n".join(problems)),
				title=f"verify :: {'PASS' if ok else 'FAIL'}"))
	exp.note(f"input() verify: {'PASS' if ok else 'FAIL'} "
			 f"({checked} values checked, {len(problems)} problems)")
	return ok


def cleanup():
	"""Save and sync. Leaves the experiment OPEN so you can keep poking at
	it -- type exp.close() when finished."""
	global exp
	exp.__save__()
	summary()
	verify()
	print(Panel("Experiment left open. Type [bold]exp.close()[/bold] to finish.",
				title="cleanup"))


if __name__ == "__main__":
	create_exp()
	print(Panel("create_exp() done.\n\n"
				"toss()        log one toss through the dialog\n"
				"record_run()  log a sequence -- type  'H','T','H'\n"
				"simulate(5)   log 5 in code, for comparison\n"
				"summary()     tally\n"
				"verify()      check the values survive a plain read",
				title="cointoss :: input() fixture"))
