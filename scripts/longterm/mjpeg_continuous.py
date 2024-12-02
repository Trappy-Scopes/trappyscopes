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
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_longterm_traj", append_eid=True)

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use start_acq() to start acquiring.")



capture = lambda: scope.cam.capture("vid_mjpeg_prev", f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}.mjpeg',  tsec=30, fps=30, exposure_ms=(1/30)*1000*0.5, quality=70)
def start_acq():

	global exp, scope, capture
	

	## Read tandh
	tandh = exp.mstreams["tandh"]
	record_sensor = lambda: tandh(temp=scope.pico("print(tandh.read())"))
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(hours=24)).do(record_sensor)
	exp.note("Tandh sensors set to record every 5 mins for the next 24 hours, starting now.")


	## Set lights and capture

	scope.lit.setVs(3,3,3)
	
	for i in range(24*2):
		filename = exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.mjpeg')
		scope.cam.capture("vid_mjpeg_prev", filename,tsec=30*60, fps=20, exposure_ms=(1/20)*1000*0.5, quality=70)
		exp.sync_file(filename)


	## Experiment is finishing - therefore sync the whole directory
	exp.sync_dir()
	exp.close()