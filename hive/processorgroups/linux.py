from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup
import logging as log
import multiprocessing
import re
import shutil
import subprocess
from subprocess import Popen

class ProcessorGroup(AbstractProcessorGroup):

	def __init__(self, name, processors=None):
		super().__init__(name)
		self.processes = []
		self.no_cores = 1
		if not processors:
			self.no_cores = multiprocessing.cpu_count()
	
	def shell(self, command):
		"""
		Launch the command on the shell.
		"""
		self.processes.append(Popen([command]))

	def __call__(self, command):
		self.shell(command)

	def set_time(self):
		"""Check that NTP keeps this machine's clock right. Changes nothing: the
		clock belongs to chrony (or systemd-timesyncd), so this only reports.

		Returns {"synchronized", "max_error_s", "reference"}:
		- synchronized: timedatectl's NTPSynchronized; None where there is no
		  timedatectl (macOS).
		- max_error_s: chrony's bound on the clock's error against UTC,
		  |offset| + root dispersion + root delay / 2; None without chrony.
		- reference: chrony's time source, e.g. "C0A80101 (192.168.1.1)".
		A clock that is not synchronized is logged as a warning.

		AI Generated (Claude, Anthropic), 2026-11-16.
		"""
		synchronized = max_error_s = reference = None
		if shutil.which("timedatectl"):
			out = _read(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
			if out in ("yes", "no"):
				synchronized = out == "yes"
		if shutil.which("chronyc"):
			kv = {}
			for line in _read(["chronyc", "-n", "tracking"]).splitlines():
				key, _, value = line.partition(":")
				kv[key.strip()] = value.strip()
			reference = kv.get("Reference ID")
			parts = [_first_number(kv.get(k, "")) for k in
					 ("System time", "Root dispersion", "Root delay")]
			if None not in parts:
				max_error_s = abs(parts[0]) + parts[1] + parts[2] / 2
		result = {"synchronized": synchronized, "max_error_s": max_error_s,
				  "reference": reference}
		if synchronized:
			log.info(f"{self.name}: clock NTP-synchronized {result}")
		else:
			log.warning(f"{self.name}: clock not known to be NTP-synchronized {result}")
		return result


def _read(cmd):
	"""stdout of cmd, stripped; "" if it fails or takes over 10 s."""
	try:
		return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
	except Exception as e:
		log.debug(f"{' '.join(cmd)}: {e}")
		return ""


def _first_number(text):
	"""The first number in text ("0.000006523 seconds slow of NTP time"), or None."""
	m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
	return float(m.group()) if m else None
