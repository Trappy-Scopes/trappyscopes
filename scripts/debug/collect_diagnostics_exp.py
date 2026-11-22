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

collect_diagnostics.py, run as an experiment.

collect_diagnostics.py is for a bare-bones machine: no framework, maybe no
network, the bundle carried off on an SSD. When the framework and the network
are working -- at the end of a long run, say -- this runs the same collector
into an experiment folder instead. The bundle is then offloaded by
exp.sync_dir() like any other run, and its findings are logged in the
experiment, where the explorer can read them.

    create_exp()                     # or create_exp("~/data/M1__YB__...")
    start()                          # runs the collector, a few minutes
    cleanup()                        # save and sync
    exp.close()

create_exp(target) takes an optional experiment directory to inspect, such as
the run you want to check. Its listing, sizes, sync ledger and rclone log are
added to the bundle. Everything else (journals, kernel log, throttling,
storage, network) is system-wide and collected either way.

Output, inside the experiment folder:

    diag_<scopeid>__<stamp>/         the collector's bundle, unchanged:
        REPORT.md, index.json, raw/, config/
    collector.log                    the collector's console output

The collector is not copied or changed: this shells out to
scripts/debug/collect_diagnostics.py, which imports nothing from the
framework. Its findings (CRITICAL, WARN, UNKNOWN, OK) go to the `findings`
measurement stream, one row each, and their counts to a `diagnostics` event.

The bundle holds the scope's configs unredacted -- the NetworkManager keyfiles
carry the file-server password and the Wi-Fi PSK -- and sync puts it on the
file server. Set exp.attribs["redact"] = True before start() for a bundle
that has to leave the lab.
"""

import glob
import json
import os
import subprocess
import sys
import threading
import time

from rich import print
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment

LEVELS = ("CRITICAL", "WARN", "UNKNOWN", "OK")


def _collector():
	"""Path to collect_diagnostics.py. Not via __file__: scripts are exec'd
	into the shell's namespace, where it is undefined. The framework's own
	modules know where the checkout is."""
	repo = os.path.dirname(os.path.dirname(os.path.abspath(
		sys.modules[Experiment.__module__].__file__)))
	return os.path.join(repo, "scripts", "debug", "collect_diagnostics.py")


def create_exp(target=None):
	"""Open the diagnostics experiment. target: an experiment directory to
	inspect as well (optional)."""
	global exp
	exp = Experiment.Construct(["diagnostics"])
	exp.attribs["target_exp"] = (os.path.abspath(os.path.expanduser(target))
								 if target else None)
	exp.attribs["redact"] = False        # True for a bundle leaving the lab
	exp.attribs["no_server"] = False     # True to skip the network tests
	exp.attribs["timeout_s"] = 30        # per command
	exp.attribs["max_minutes"] = 45      # the whole collection
	exp.new_measurementstream("findings", monitors=["level", "raw"],
							  measurements=["title", "detail"])
	if target and not os.path.isdir(exp.attribs["target_exp"]):
		print(Panel(f"[red]{exp.attribs['target_exp']} is not a directory. The "
					f"bundle will say so; everything else is still collected.",
					title="target"))
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))


def _run_logged(cmd, path, limit_s):
	"""Run cmd, echoing its output to the console and to path. Killed after
	limit_s. Returns the exit code, or None if it was killed or interrupted."""
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
						 text=True, bufsize=1)
	timer = threading.Timer(limit_s, p.kill)
	timer.start()
	try:
		with open(path, "w") as f:
			for line in p.stdout:
				sys.stdout.write(line)       # not rich: the output has [brackets]
				f.write(line)
		rc = p.wait()
		return None if rc < 0 else rc
	except KeyboardInterrupt:
		p.kill()
		p.wait()
		return None
	finally:
		timer.cancel()


def start():
	"""Run the collector into this experiment and log what it found."""
	global exp
	exp = Experiment.current
	a = exp.attribs
	cmd = [sys.executable, _collector(), "--out", os.getcwd(), "--no-tar",
		   "--timeout", str(a["timeout_s"])]
	if a["target_exp"]:
		cmd += ["--exp-dir", a["target_exp"]]
	if a["no_server"]:
		cmd.append("--no-server")
	if a["redact"]:
		cmd.append("--redact")

	exp.log_event("diagnostics_start", attribs={"cmd": " ".join(cmd)})
	t0 = time.time()
	rc = _run_logged(cmd, "collector.log", a["max_minutes"] * 60)
	seconds = round(time.time() - t0, 1)

	## The collector names its bundle diag_<scopeid or host>__<stamp>.
	bundles = [d for d in glob.glob("diag_*__*") if os.path.isdir(d)
			   and os.path.getmtime(d) >= t0 - 1]
	bundle = max(bundles, key=os.path.getmtime) if bundles else None
	index = os.path.join(bundle, "index.json") if bundle else None
	if not index or not os.path.exists(index):
		exp.log_event("diagnostics", attribs={"bundle": bundle, "rc": rc,
											  "seconds": seconds, "complete": False})
		exp.__save__()
		print(Panel(f"[red]The collector did not finish (exit code {rc}). "
					f"What it wrote is in {bundle or 'no bundle'}, and "
					f"collector.log has its output. cleanup() still syncs it.",
					title="diagnostics"))
		return

	with open(index) as f:
		findings = json.load(f)["findings"]
	for x in findings:
		exp.mstreams["findings"](level=x["level"], raw=f"{bundle}/{x['raw']}",
								 title=x["title"], detail=x["detail"])
	counts = {lvl.lower(): sum(x["level"] == lvl for x in findings) for lvl in LEVELS}
	exp.log_event("diagnostics", attribs={"bundle": bundle, "rc": rc,
										  "seconds": seconds, "complete": True,
										  **counts})
	exp.__save__()

	worst = [f"{x['level']:8s} {escape(x['title'])}" for x in findings
			 if x["level"] in ("CRITICAL", "WARN")]
	print(Panel(f"{bundle}/REPORT.md\n\n"
				+ "  ".join(f"{k}: {v}" for k, v in counts.items()) + "\n\n"
				+ ("\n".join(worst) or "No critical or warning findings.")
				+ "\n\n[yellow]cleanup() to save and sync.",
				title="diagnostics"))


def cleanup():
	"""Save and sync. Does NOT close the experiment -- type exp.close()
	afterwards, as for the other scripts."""
	global exp
	exp = Experiment.current
	exp.schedule.clear()
	exp.schedule.end_thread = True
	exp.note("Diagnostics collected and offloaded.")
	exp.__save__()
	exp.sync_dir()
	print(Panel("[yellow]Saved and offloaded. The experiment is still OPEN -- "
				"type [bold]exp.close()[/bold] to finish it.", title="cleanup"))


if __name__ == "__main__":
	print(Panel('create_exp()   or   create_exp("~/data/<run to inspect>")\n'
				"start()\n"
				"cleanup() then exp.close()\n\n"
				"Runs collect_diagnostics.py into an experiment, so the bundle "
				"syncs like any other run.",
				title="collect_diagnostics_exp"))
