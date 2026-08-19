"""Peristaltic pump support, host side.

	from actuators.pumps import RemotePumpSet, KeypadLink, Dashboard
	from actuators.pumps.supervisor import LinkSupervisor
	from actuators.pumps import envelope as env
	from actuators.pumps.simulated import SimPump, SimPumpSet

Five pieces, each usable alone:

	RemotePumpSet   PumpSet-shaped facade over scope.pumpset on the Pico
	SimPump/Set     the same API, host side, for rehearsal without hardware
	KeypadLink      reading the keypad and mirroring pump state back to it
	Dashboard       the live view, the status table, the volume integrator
	LinkSupervisor  the lock, the bounded recovery, the health of the link
	envelope        pushing the speed envelope and reading it back

They were extracted from scripts/chambertests/keypad_pump_control.py and
scripts/toyexps/keypad_pump_test.py, which had grown two copies of all of it.

LinkSupervisor is the one that matters operationally: nothing else in this
package is allowed to block on serial from a render or poll loop, and it is the
only thing permitted to reconnect.
"""

from .remote import RemotePumpSet, hard_reset, link_check, relink, pump_device
from .keypadlink import KeypadLink, parse_line
from .dashboard import Dashboard, setpoint
from .supervisor import LinkSupervisor
from . import envelope

__all__ = ["RemotePumpSet", "SimPump", "SimPumpSet", "KeypadLink", "Dashboard",
			"LinkSupervisor", "envelope", "setpoint", "parse_line",
			"hard_reset", "link_check", "relink", "pump_device"]


def __getattr__(name):
	## Simulation is imported lazily: a real rig never needs it.
	if name in ("SimPump", "SimPumpSet"):
		from . import simulated
		return getattr(simulated, name)
	raise AttributeError(name)
