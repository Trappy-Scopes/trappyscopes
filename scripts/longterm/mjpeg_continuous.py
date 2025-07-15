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
	exp.attribs["no_chunks"] = 21*6
	exp.attribs["light"] = (2,0,0)
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts"
	exp.attribs["group"] = "red_light"
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
	global exp
	for i in range(exp.attribs["no_chunks"]):
		
		#filename = exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.avi', abspath=False)
		filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{i}.mjpeg', abspath=False)
		
		c = exp.mstreams["acq"](filename=filename)
		c.panel()
		
		scope.cam.read(exp.attribs["camera_mode"], filename, tsec=exp.attribs["chunk_size_sec"], fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])
		#scope.cam.read("video", filename, tsec=10)
		
		exp.sync_file_bg(filename, remove_source=True)
	
	## Experiment is finishing - therefore sync the whole directory
	exp.logs.update(scope.get_config())
	exp.__save__()
	exp.sync_dir()
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
	exp.schedule.every(5).minutes.until(timedelta(seconds=exp.attribs["chunk_size_sec"]*exp.attribs["no_chunks"])).do(record_sensor)
	exp.logs.update(scope.get_config())
	exp.__save__()
	print("All jobs: ", exp.schedule.get_jobs())

	## Set lights and capture

	scope.lit.setVs(*exp.attribs["light"])
	

	from multiprocessing import Process
	global process
	process = Process(target=capture)
	process.start()
	#capture()

def test_fov(tsec):
	scope.cam.read("prev_formatted", None, tsec=tsec, fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])

