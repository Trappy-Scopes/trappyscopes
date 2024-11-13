from datetime import timedelta
import datetime
import time
from rich import print
import ast

def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_sampled_longterm_traj", append_eid=True)

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use start_acq() to start acquiring.")



capture = lambda: scope.cam.capture("vid_mjpeg_prev", f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}',  tsec=30, fps=30, exposure_ms=(1/30)*1000*0.5)
def start_acq():

	global exp, scope, capture
	

	## Read tandh
	tandh = exp.streams["tandh"]
	record_sensor = lambda: tandh(**ast.literal_eval(pico("tandh.read()").strip("\r\n")))
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(hours=24)).do(record_sensor)
	exp.note("Tandh sensors set to record every 5 mins for the next 24 hours, starting now.")


	## Set lights and capture

	scope.lit.setVs(3,3,3)
	capture()
	exp.schedule.every(1).hours.until(timedelta(hours=24)).do(capture)
	exp.note("Set to capture 30 seconds, every 1 hour for the next 24 hours, starting now.")
	


