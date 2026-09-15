from datetime import timedelta
import datetime
import os
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty
from rich.prompt import Confirm

from expframework.experiment import Experiment
from expframework.expsync import ExpSync  # AI Generated
from expframework.script import Script  # AI Generated
from core.gitutil import commit_and_push  # AI Generated

# Cell counts repo + export directory on the current machine (MDev). This updates the global database.
CELL_COUNTS_REPO_DIR = "/Users/byatharth/code/Trappy-Scopes/others/cell-counts"
CELL_COUNTS_EXPORT_DIR = os.path.join(CELL_COUNTS_REPO_DIR, "data", "metaexperiments")

Script.describe("Metaexperiment: day-level log of cell trapping across scopes "
				 "(temp/humidity, cell fates, damaged devices, cell counts).")  # AI Generated

@Script.setup
def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"Metaexperiment_{dt}_{time_str}_cell_trapping", append_eid=True)

	populate_exp()


print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use link_objects() to link measuement streams.")
print("Use new_count() to register cell_counts.")



def populate_exp():
	global exp
	### Experiment streams
	exp.new_measurementstream("tandh", measurements=["temp"], monitors=["ch"])
	#exp.new_measurementstream("cell_fates", monitors=["last_split", "active_periods", "max_cells", "eid"])
	exp.new_measurementstream("damaged_devices", monitors=["id"])

	exp.new_measurementstream("cell_counts", measurements=["counts"], monitors=["df", "density", "label", "sep", "sample_media_ratio", "scaled_density"])


global tandh, cell_fates, damaged, counts
tandh = None; cell_fates = None; damaged = None; counts = None
def link_objects():
	global tandh, cell_fates, damaged, counts
	tandh = exp.mstreams["tandh"]
	#cell_fates = exp.mstreams["cell_fates"]
	damaged = exp.mstreams["damaged_devices"]
	counts = exp.mstreams["cell_counts"]


def new_count(label, *args, df=2, sep=None, sample_media_ratio=(1.5, 18.5)):
	import numpy as np
	c = Experiment.current.mstreams["cell_counts"](counts=args, label=label, df=df, sep=sep,
									density=float(np.mean(args)*10000*df))

	if sep is True:
		sample, media = sample_media_ratio
		c["scaled_density"] = c["density"] * (sample + media) / sample
	else:
		c["scaled_density"] = c["density"]

	c.panel()
	print(Panel(f"Culture density is: {c['density']:.2e}"))


@Script.cleanup
def cleanup():
	"""
	Export counts and sync experiment to file server.
	"""
	exp = Experiment.current
	os.makedirs(CELL_COUNTS_EXPORT_DIR, exist_ok=True)
	csv_path = os.path.join(CELL_COUNTS_EXPORT_DIR, f"{exp.name}_cell_counts.csv")
	exp.mstreams["cell_counts"].df.to_csv(csv_path, index=False)
	print(Panel(f"Exported cell_counts to {csv_path}", style="green"))

	if ExpSync.active:
		exp.sync_dir()
		print(Panel("Experiment directory synced to file server.", style="green"))
	else:
		print(Panel("File server not connected -- skipping experiment directory sync.", style="yellow"))

	## AI Generated -- commit+push is a shared, hard-to-reverse action (a
	## GitHub repo other scripts/people also touch), so it's confirmed
	## here rather than done silently at the end of an unattended run.
	if Confirm.ask(f"Push cell-counts repo ({csv_path.split('/')[-1]})?", default=True):
		try:
			pushed = commit_and_push(CELL_COUNTS_REPO_DIR, [csv_path], f"Export cell_counts: {exp.name}")
			if pushed:
				print(Panel("cell-counts repo pushed.", style="green"))
			else:
				print(Panel("Nothing new to commit in cell-counts repo.", style="dim"))
		except Exception as e:
			print(Panel(f"cell-counts push failed: {e}", style="red"))