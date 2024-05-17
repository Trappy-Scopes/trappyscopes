import datetime
from time import sleep
import time
from experiment import Calibration
from rich import print
from rich.markdown import Markdown

print(trap)

# Start experiment
unique_check = True
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())


## Create experiment
exp = Experiment(f"{scopeid}_long_term_perfusion_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
exp.delay("Start delay", 3)



global counter, mstream
counter = 0
mstream = exp.new_measurementstream("captures", measurements=["acq"],
								 	monitors=["tandh"])
def acq_protocol():
	now = datetime.datetime.now()
	capname = f"duration_{Experiment.current.timer_elapsed()/3600:.0f}h.h264"

	m = Experiment.current.streams["captures"]() ## Generate measurement

	## Capture
	cam.capture(vid, capname, tsec=30)
	m["acq"] = capname
	m["fps"] = 30
	m["res"] = [1920, 1080]
	m["fluidics"] = trap.name
	m["fluidics_type"] = trap.attribs["type"]
	m["pump_id"] = pumpid ## Need to be defined beforehand

	try:
		m["tandh"] = scope.pico.tandh.read()
	except:
		pass

## Schedule acquisitions
exp.schedule.every().hour.do(acq_protocol)
exp.schedule.post_register("hourly_capture")



