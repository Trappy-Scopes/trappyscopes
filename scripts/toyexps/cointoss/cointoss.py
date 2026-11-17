"""
Coin toss v1 -- the simplest thing that runs.

Mounts a coin on the ScopeAssembly and flips it five times, one flip a
second, under a real Experiment. Nothing is measured and nothing is
recorded into a measurement stream: the outcome lives on the coin itself,
as an attribute of the physical object, and the only trace in
experiment.yaml is the script_run event ScriptEngine writes.

This is a deliberately UNSTRUCTURED script -- flat functions, no
setup/start/cleanup contract (see expframework/script.py). It is what you
write when you just want to try something. cointoss_input.py is the same
experiment written structurally, and is where the recording starts.

author: Yatharth Bhasin
date: 30-July-2025
licence: MIT Licence

Copyright (c) 2025 Yatharth Bhasin

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

## Common imports. Everything a function needs only once is imported inside
## that function, to keep the session namespace clean -- ScriptEngine execs
## this file straight into the interactive namespace.
import random
from datetime import timedelta

from rich import print
from rich.panel import Panel

from expframework.experiment import Experiment
from expframework.script import Script
from hive.assembly import ScopeAssembly


## The description ScriptEngine prints and logs into the script_run event.
## Script.describe() rather than a bare `__description__` string: it is a real
## call, so a misspelling is an immediate error instead of a silently ignored
## variable (two of the longterm scripts carry `__decription__` to this day).
Script.describe("""
Coin toss v1. Mounts a `coin` PhysicalObject on the ScopeAssembly and flips
it five times, one a second, through the experiment scheduler. The outcome
is written onto the coin, not into a measurement stream -- recording is what
cointoss_input.py adds.
""")


## The vocabulary every cointoss script shares:
##   device  `coin`      a PhysicalObject on the assembly
##   field   `outcome`   what came up
##   values  "H" / "T"
FACES = ("H", "T")


def create_exp():
	"""Construct the experiment this session's tosses belong to."""
	global exp
	exp = Experiment.Construct(["test", "scripted_run", "coin_toss"],
								username=True, eid=True, date=True, time=True,
								scopeid=True)
	return exp


def add_coin(name="coin", description="5 cents Euro coin"):
	"""Mount a coin on the current ScopeAssembly.

	A coin is a physical object with no electronics, which is exactly what
	hive.physical.PhysicalObject is for -- it carries metadata (which coin,
	what its faces are, what came up last) and nothing else. Declaring it
	here is the imperative equivalent of the ScopeAssembly block in
	docs/notes/advanced_config.md; either way `scope.coin` is the result.
	"""
	from hive.physical import PhysicalObject
	global scope, coin

	scope = ScopeAssembly.current
	print("[yellow]Assembly before the coin:")
	print(scope.draw_tree())

	coin = scope.add_device(name, PhysicalObject(name, faces=list(FACES),
												 outcome=None,
												 description=description))
	print("[green]Assembly with the coin:")
	print(scope.draw_tree())
	return coin


def toss():
	"""Flip the coin once and write the outcome onto it.

	Nothing is recorded anywhere else. `coin["outcome"]` is overwritten
	every call, so only the last flip survives -- which is the whole
	limitation cointoss_input.py exists to fix.
	"""
	coin["outcome"] = random.choice(FACES)
	print(f"coin -> [bold]{coin['outcome']}[/bold]")
	return coin["outcome"]


def toss_five(every_s=1):
	"""Schedule five tosses, one every `every_s` seconds, then stop.

	Driven by exp.schedule (expframework's wrapper around `schedule`), so
	the flips happen on the experiment's own background thread while the
	prompt stays usable -- the point being that even the simplest script
	does not have to block to do something over time.
	"""
	exp.schedule.every(every_s).second.do(toss).until(
		timedelta(seconds=5 * every_s))
	print(f"[cyan]Five tosses scheduled, one every {every_s}s.")


print("cointoss v1 -- create_exp(), add_coin(), then toss() or toss_five().")


if __name__ == "__main__":
	create_exp()
	add_coin()
	toss_five()
	print(Panel("Five tosses are running on the scheduler.\n\n"
				"toss()        flip once, now\n"
				"scope.coin    the coin itself\n"
				"coin.show()   every field on it\n\n"
				"Nothing is being recorded -- see cointoss_input.py.",
				title="cointoss :: v1 (unstructured)"))
