from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_longterm_traj", append_eid=True)

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	exp.attribs["chunk_size_sec"] = 10*60
	exp.attribs["fps"] = 20
	exp.attribs["exposure_ms"] = 18
	exp.attribs["quality"] = 70
	exp.attribs["no_chunks"] = 20*6
	exp.attribs["light"] = (2,0,0)
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use start_acq() to start acquiring.")
print("Use stop_cam() to kill the capture thread.")
scope.beacon.blink()




global process
process = None

def stop_cam():
	global process
	process.kill()

def capture():
	for i in range(exp.attribs["no_chunks"]):
		#filename = exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.avi', abspath=False)
		filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.mjpeg', abspath=False)
		scope.cam.read("vid_mjpeg_tpts", filename, tsec=exp.attribs["chunk_size_sec"], fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])
		#scope.cam.read("video", filename, tsec=10)
		exp.sync_file_bg(filename, remove_source=True)
	
	## Experiment is finishing - therefore sync the whole directory
	exp.sync_dir()
	exp.logs.update(scope.get_config())
	exp.__save__()
	scope.beacon.blink()
	exp.close()

def start_acq():

	global exp, scope, capture
	

	scope.beacon.on()


	## Read tandh
	tandh = exp.mstreams["tandh"]
	def record_sensor():
		try:
			value = scope.tandh.read()
		except:
			print("[red]TandH reading failed![default]")
			value =  {"temp": 0, "humidity":0}
		r = tandh(**value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(hours=24)).do(record_sensor)
	exp.note("Tandh sensors set to record every 5 mins for the next 24 hours, starting now.")
	exp.logs.update(scope.get_config())
	exp.__save__()

	## Set lights and capture

	scope.lit.setVs(*exp.attribs["light"])
	

	from multiprocessing import Process
	global process
	process = Process(target=capture)
	process.start()
	#capture()

def test_fov():
	scope.cam.read("prev_formatted", None, tsec=30, fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])

