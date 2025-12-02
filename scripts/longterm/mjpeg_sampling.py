from datetime import timedelta
import datetime
import time
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty
import ast

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly



def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment.Construct(["sampled_longterm_traj"])

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	exp.params["sampling_period_hours"] = 0.5
	exp.params["sampling_hours"] = 24
	exp.params["tandh_sampling_period_minutes"] = 5

	
	exp.attribs["chunk_size_sec"] = 60*5
	exp.attribs["fps"] = 25
	exp.attribs["exposure_ms"] = 3
	exp.attribs["quality"] = 100
	exp.attribs["no_splits"] = 81
	exp.attribs["light"] = (2.4,0,0)
	exp.attribs["camera_mode"] = "vid_mjpeg_tpts"
	exp.attribs["group"] = "red_light"
	exp.attribs["sync_files"] = True
	exp.attribs["beacon_stabilization_delay_s"] = 1
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))

 
print("Use create_exp() to open a new experiment. Use exp = findexp() to open an old one.")
print("Use start_acq() to start acquiring.")
print("Use cleanup() to close and sync experiment.")

## Split number
global split_no
split_no = 0

global capturefilelist, syncidx
syncidx = 0
capturefilelist = []

def sync_file():
	global exp, capturefilelist, syncidx
	if len(capturefilelist) > 1:
		exp.sync_file_bg(capturefilelist[syncidx], remove_source=True)
		syncidx = syncidx + 1

def filename_fn(split_no):
	global exp
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__{time.time_ns()}__split_{split_no}.mjpeg', abspath=False)
	capturefilelist.append(filename)
	#if split_no >= 1 and exp.params["sync_files"]:
	#	sync_file()
	return filename



def capture():
	"""Function that records videos"""
	scope = ScopeAssembly.current
	exp = Experiment.current
	scope.beacon.on()
	time.sleep(exp.params["beacon_stabilization_delay_s"])

	exp = Experiment.current
	split = len(exp.mstreams["acq"].readings)
	
	global split_no
	filename=filename_fn(split_no)
	acq = exp.mstreams["acq"](acq=filename)
	
	### Capture
	scope.cam.open()
	scope.cam.configure()
	scope.cam.read(exp.attribs["camera_mode"], 
				   filename,
				   tsec=exp.attribs["chunk_size_sec"], 
				 	show_preview=False,
					quality=exp.attribs["quality"])
	scope.cam.close()
	
	acq.panel()
	scope.beacon.blink()
	if exp.params["sync_files"]:
		exp.sync_file_bg(filename, remove_source=True)


def record_sensor():
	"""Read temperature sensor"""
	tandh = Experiment.current.mstreams["tandh"]
	try:
		value = scope.tandh.read()
	except:
		print("[red]TandH reading failed![default]")
		value =  {"temp": 0, "humidity":0}
	r = tandh(**value)
	r.panel()



def test_fov(tsec):
	print("DEPRECIATED!!!!")
	scope = ScopeAssembly.current
	scope.cam.read("prev_formatted", 
					None, 
					tsec=tsec, 
					fps=exp.params["camera_fps"], 
					exposure_ms=exp.params["camera_exposure_ms"], 
					quality=exp.params["compression_quality_factor"])


def start_acq():
	global exp, scope, capture
	scope = ScopeAssembly.current

	## Read tandh
	record_sensor()
	Experiment.current.schedule.every(exp.params["tandh_sampling_period_minutes"]).minutes.until(timedelta(hours=exp.params["sampling_hours"])).do(record_sensor)

	## Set lights and capture
	scope.lit.setVs(*exp.params["light"])
	capture()
	Experiment.current.schedule.every(exp.params["sampling_period_hours"]).hours.until(timedelta(hours=exp.params["sampling_hours"])).do(capture)
	

def cleanup():
	exp = Experiment.current
	exp.logs.update(ScopeAssembly.current.get_config())
	exp.__save__()
	exp.sync_dir()
	exp.close()

if __name__ == "__main__":
	global scope
	scope = ScopeAssembly.current
	scope.lit.setVs(2.4,0,0)
	print("Lights ready...")
	scope.cam.config["controls"]["ExposureTime"] = 3000
	scope.cam.open()
	scope.cam.configure()
	scope.beacon.blink()

