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
	def record_sensor():
		try:
			value = scope.tandh.read()
		except:
			print("TandH reading failed!")
			value =  {"temp": 0, "humidity":0}
		r = tandh(**value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(hours=24)).do(record_sensor)
	exp.note("Tandh sensors set to record every 5 mins for the next 24 hours, starting now.")
	exp.logs.update(scope.get_config())
	exp.__save__()

	## Set lights and capture

	scope.lit.setVs(3,3,3)
	
	for i in range(24):
	#for i in range(10):
		#filename = exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.avi', abspath=False)
		filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.mjpeg', abspath=False)
		scope.cam.read("vid_mjpeg", filename, tsec=30*60, fps=20, exposure_ms=(1/20)*1000*0.5, quality=70)
		#scope.cam.read("video", filename, tsec=60)
		exp.sync_file_bg(filename, remove_source=True)


	## Experiment is finishing - therefore sync the whole directory
	exp.sync_dir()
	exp.logs.update(scope.get_config())
	exp.__save__()
	exp.close()