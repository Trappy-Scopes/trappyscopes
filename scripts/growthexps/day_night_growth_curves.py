import datetime
import time
from rich import print

def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_growth_curves", append_eid=True)

global param, strainid, name
param = {
	
	"hours"   : 2,
	"strains" : ["CC2377", "CC125", "CC2984", "CC2377_N", "CC125_N", "CC2984_N"]
}
strainid = 0



def new_timepoint():
	global name, strainid
	name = None
	strainid = -1
new_timepoint()

def new_count():
	global param, strainid, name
	strainid = strainid + 1
	strain = param["strains"][strainid]
	print(f"[bold][red] Counting:::: {strain}!")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}{t.tm_min}__{t.tm_hour}"
	name = f"{strain}__{time_str}"
	print("Naming sequence:: ", name)

def register_counts(*args, df=2):
	"""
	Add measurements to the datastreams.
	"""
	pass

