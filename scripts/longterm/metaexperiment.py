from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment

def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"Metaexperiment_{dt}_{time_str}_cell_trapping", append_eid=True)

	### Experiment streams
	exp.new_measurementstream("tandh", measurements=["temp"], monitors=["ch"])
	exp.new_measurementstream("cell_fates", monitors=["last_split", "active_periods", "max_cells", "eid"])
	exp.new_measurementstream("damaged_devices", monitors=["id"])

	exp.new_measurementstream("cell_counts", measurements=["counts"], monitors=["df", "density", "label"])

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use link_objects() to link measuement streams.")
print("Use new_count() to register cell_counts.")

global tandh, cell_fates, damaged, counts
tandh = None; cell_fates = None; damaged = None; counts = None
def link_objects():
	global tandh, cell_fates, damaged, counts
	tandh = exp.mstreams["tandh"]
	cell_fates = exp.mstreams["cell_fates"]
	damaged = exp.mstreams["damaged_devices"]
	counts = exp.mstreams["cell_counts"]


def new_count(label, *args, df=2):
	import numpy as np
	c = Experiment.current.mstreams["cell_counts"](counts=args, label=label, df=df,
									density=np.mean(args)*10000*df)
	c.panel()
	print(Panel(f"Culture density is: {c['density']:.2e}"))