"""Peristaltic pump support, host side.

    from actuators.pumps import RemotePumpSet, KeypadLink, Dashboard
    from actuators.pumps.simulated import SimPump, SimPumpSet

Four pieces, each usable alone:

    RemotePumpSet   PumpSet-shaped facade over scope.pumpset on the Pico
    SimPump/Set     the same API, host side, for rehearsal without hardware
    KeypadLink      reading the keypad and mirroring pump state back to it
    Dashboard       the live view, the status table, the volume integrator

They were extracted from scripts/chambertests/keypad_pump_control.py and
scripts/toyexps/keypad_pump_test.py, which had grown two copies of all of it.
"""

from .remote import RemotePumpSet, hard_reset, link_check, relink
from .keypadlink import KeypadLink, parse_line
from .dashboard import Dashboard

__all__ = ["RemotePumpSet", "SimPump", "SimPumpSet", "KeypadLink", "Dashboard",
			"parse_line", "hard_reset", "link_check", "relink"]


def __getattr__(name):
	## Simulation is imported lazily: a real rig never needs it.
	if name in ("SimPump", "SimPumpSet"):
		from . import simulated
		return getattr(simulated, name)
	raise AttributeError(name)
