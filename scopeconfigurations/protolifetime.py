import time
import datetime
from rich import print
import gc

from experiment import Experiment
from dataclasses import dataclass, field, asdict


global exp
if Experiment.current == None:
	## Create an experiment
	global exp
	unique_check = False
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	exp = Experiment(f"{scopeid}_{dt}_{t.tm_hour}_{t.tm_min}_lifetime_machine", append_eid=True)

print(exp)
## -----------------------------
@dataclass
class LifetimeMachine:
	hours : float         = 24 
	chunk_hours : float   = 0.5
	res: tuple[int]       = (1080, 1080)
	fps: float            = 20
	state: int            = 0

lifetimemach = LifetimeMachine()
print("Lifetime Machine created: ", lifetimemach)
print("[red] Change configuration if necessary.[default]")
exp.log("lifetime_machine", attribs=asdict(lifetimemach))
## -------------------------------

ms = exp.new_measurementstream("main", measurements=["acq"])
def start_acq():
	"""
	Start acqusition for n-number of hours
	"""

	# --- Configure camera -> only size and resolution.

	exp.log("start_acq")


	ltm = lifetimemach
	for i in range(int(ltm.hours/ltm.chunk_hours)):
		cam.close()
		cam.open()
		cam.cam.create_video_configuration(main={"size": tuple(ltm.res)}, encode="main")
		cam.cam.video_configuration.size  = tuple(ltm.res)
		cam.cam.video_configuration.controls.FrameRate = ltm.fps

		capname = exp.newfile(f"{i}__{str(i*ltm.chunk_hours).replace('.', ',')}.h264")
		print("Capturing : ", capname)
		cam.capture(vid_noprev, capname, tsec=ltm.chunk_hours*3600)
		m = ms(acq=capname, trap=trap.name, **asdict(ltm))
		m.panel()
		cam.close()
		print(f"Acquired chunk: {i}. Experiment clock: {exp.timer_elapsed():.3f}s.")
		ltm.state += 1
		gc.collect()

