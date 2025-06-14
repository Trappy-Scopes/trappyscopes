from datetime import timedelta
import datetime
import time
from rich import print
import ast

from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly

def create_exp():
	global exp
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_sampled_longterm_traj", append_eid=True)

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq"])

	exp.params["sampling_period_hours"] = 1
	exp.params["sampling_hours"] = 24
	exp.params["tandh_sampling_period_minutes"] = 5
	exp.params["capture_time_sec"] = 20
	exp.params["camera_fps"] = 20
	exp.params["camera_exposure_ms"] = 18
	exp.params["compression_quality_factor"] = 95
	exp.params["camera_action"] = "vid_mjpeg_prev"
	exp.params["light"] = [2,2,2]
	exp.params["beacon_stabilization_delay_s"] = 3


 
print("Use create_exp() to open a new experiment. Use exp = findexp() to open an old one.")
print("Use start_acq() to start acquiring.")
print("Use test_fov(tsec) to test aquisition parameters")
print("Use cleanup() to close and sync experiment.")



def capture():
	"""Function that records videos"""
	scope = ScopeAssembly.current
	scope.beacon.on()
	time.sleep(exp.params["beacon_stabilization_delay_s"])

	exp = Experiment.current
	split = len(exp.mstreams["acq"].readings)
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}__split_{split}.mjpeg', abspath=False)
	acq = exp.mstreams["acq"](filename)
	scope.cam.capture(exp.params["camera_action"],
	                  filename,
	                  tsec=exp.params["capture_time_sec"],
	                  fps=exp.params["camera_fps"], 
	                  exposure_ms=exp.params["camera_exposure_ms"], 
	                  quality=exp.params["compression_quality_factor"])
	acq.panel()
	scope.beacon.blink()



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
	tandh = Experiment.current.mstreams["tandh"]
	record_sensor = lambda: tandh(scope.tandh.read())
	record_sensor()
	Experiment.current.schedule.every(exp.params["tandh_sampling_period_minutes"]).minutes.until(timedelta(hours=24)).do(record_sensor)

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

