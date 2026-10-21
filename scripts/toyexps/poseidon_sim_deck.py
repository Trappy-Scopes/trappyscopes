"""
The real Poseidon control deck, driving a simulated board.

AI Generated -- written by Claude (Anthropic), 2026-10. Unlike
poseidon_deck_dummy.py (a layout mock-up), this runs the actual
poseidon_pumps.arduino.PoseidonController; only the Arduino is simulated, by
poseidon_pumps.sim, a Python port of the unchanged upstream sketch. Positions,
limits and the busy / stop / pause rules behave as they will on the hardware.

Needs the poseidon_pumps repository; set POSEIDON_PUMPS_ROOT if it is not at
~/code/Trappy-Scopes/poseidon_pumps.

	exec(open("scripts/toyexps/poseidon_sim_deck.py").read())
	poseidon_sim.deck()          # reopen later; poseidon_sim.state() for the numbers

Positions persist under ~/trappyverse/state/poseidon-sim-deck-demo-p*.

author: Yatharth Bhasin
date: 13-October-2026
licence: MIT Licence
"""

import os
import sys

POSEIDON_ROOT = os.environ.get("POSEIDON_PUMPS_ROOT",
							   os.path.expanduser("~/code/Trappy-Scopes/poseidon_pumps"))
if POSEIDON_ROOT not in sys.path:
	sys.path.insert(0, POSEIDON_ROOT)

from poseidon_pumps.arduino import PoseidonController

poseidon_sim = PoseidonController(
	name="deck-demo", simulate=True, microsteps=32,
	pumps={1: {"syringe": "BD 10 mL", "rate": 900.0, "unit": "µL/hr", "accel": 50.0},
		   2: {"syringe": "BD 1 mL", "rate": 0.1, "unit": "mm/s", "accel": 5.0},
		   3: {"syringe": "BD 3 mL", "rate": 0.1, "unit": "mm/s", "accel": 5.0}})

poseidon_sim.deck()
print(poseidon_sim.state())
