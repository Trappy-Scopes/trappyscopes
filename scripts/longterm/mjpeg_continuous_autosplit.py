from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly

def create_exp():
	global exp, scopeid, scope
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment.Construct(["longterm_traj"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	exp.attribs["chunk_size_sec"] = 10*60
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 18
	exp.attribs["quality"] = 100
	exp.attribs["no_chunks"] = 92
	exp.attribs["light"] = (0.4,0,0)
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts_multi"
	exp.attribs["group"] = "red_light"
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use start_acq() to start acquiring.")
print("Use stop_cam() to kill the capture thread.")





global process
process = None

def stop_cam():
	global process, scope
	print(f"Killing: {process}")
	process.kill()
	print(f"Killed: {process}")
	scope.beacon.blink()

global capturefilelist, syncidx
capturefilelistcapturefilelist = 0
capturefilelist = []
def filename_fn(split_no):
	global exp
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__{time.time_ns()}__split_{split_no}.mjpeg', abspath=False)
	capturefilelist.append(filename)
	return filename


def sync_file():
	global exp, capturefilelist, syncidx
	if len(capturefilelist) > 1:
		exp.sync_file_bg(capturefilelist[syncidx], remove_source=True)
		syncidx = syncidx + 1


def capture():
	global exp, scope
		
	# Pending -> File record mechaanism
	#c = exp.mstreams["acq"](filename=filename)
	#c.panel()
	exp = Experiment.current
	scope = ScopeAssembly.current
	scope.cam.read(exp.attribs["camera_mode"], filename_fn, no_iterations=exp.attribs["no_chunks"], tsec=exp.attribs["chunk_size_sec"], 
					show_preview=False, quality=exp.attribs["quality"])

	## Experiment is finishing - therefore sync the whole directory
	exp.logs.update(scope.get_config())
	exp.__save__()
	exp.sync_dir()
	scope.beacon.blink()
	exp.close()

def start_acq():

	global exp, scope, capture
	
	scope = ScopeAssembly.current
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
def start_acq_blocking():

	global exp, scope, capture
	
	scope = ScopeAssembly.current
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
	

	#from multiprocessing import Process
	#global process
	#process = Process(target=capture)
	#process.start()
	capture()

def test_fov(tsec):
	global scope
	print("[red]This function is obselete!")
	scope.cam.read("prev_formatted", None, tsec=tsec, fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])


if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	scope.lit.setVs(0.4,0,0)
	print("Lights ready...")
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.blink()
