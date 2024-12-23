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
	exp = Experiment(f"{scopeid}_{dt}_{time_str}_ecosystem_sampled_12hday_12hnight", append_eid=True)

	exp.new_measurementstream("tandh", measurements=["temp", "humidity"])
	exp.new_measurementstream("acq", monitors=["acq", "phase"])

	
	exp.attribs["fps"] = 20
	exp.attribs["quality"] = 70
	exp.attribs["chunk_size_sec"] = 10*60
	exp.attribs["no_chunks"] = 24*6*5 ## Programmed to run 5-days

	exp.attribs["exposure_ms_day"] = 15
	exp.attribs["exposure_ms_night"] = 50
	## Current camera exposure
	exp.attribs["exposure_ms"] = exp.attribs["exposure_ms_day"] 
	

	

	
	exp.attribs["day_light"] = (2,3,2)
	exp.attribs["night_light"] = (0.5, 0, 0)
	exp.attribs["light"] = exp.attribs["day_light"] ## Current camera light
	
	exp.attribs["phase"] = "day"

	exp.attribs["group"] = "ecosystem"
	exp.attribs["description"] = "The script records for a certain duration every hour for 5 days.\n \
								  During the night it records in low-intensity red light. An arbitrary amount of smaple is loaded."
	print(Panel(Pretty(exp.attribs), title="Experiment Attributes"))

print("Use create_exp() to open a new experiment. Use findexp() to open an old one.")
print("Use start_acq() to start acquiring.")
print("Use stop_cam() to kill the capture thread.")
scope.beacon.blink()

def test_fov(tsec):
	"""Test the fov for edges and focus."""
	scope.cam.read("prev_formatted", None, tsec=tsec, fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])

global bomdia
def bomdia():
	"""Bring daylight."""
	global exp, scope
	exp.attribs["phase"] = "day"
	exp.attribs["exposure_ms"] = exp.attribs["exposure_ms_day"]
	exp.attribs["light"] = exp.attribs["day_light"]
	scope.lit.setVs(*exp.attribs["light"])
	print(Panel(Pretty(exp.attribs), title="Bom dia!"))

global bonnoite
def bonnoite():
	"""Bring darkness (not really)!"""
	global exp, scope
	exp.attribs["phase"] = "night"
	exp.attribs["exposure_ms"] = exp.attribs["exposure_ms_night"]
	exp.attribs["light"] = exp.attribs["night_light"]
	scope.lit.setVs(*exp.attribs["light"])
	print(Panel(Pretty(exp.attribs), title="Bon noite!"))



global process
process = None
def stop_cam():
	"""Function to kill camera process if acquisition is multi-threaded."""
	global process
	process.kill()

global capture
def capture():
	"""Simple capture function"""
	filename=exp.newfile(f'{str(datetime.datetime.now()).split(".")[0].replace(" ", "__").replace(":", "_").replace("-", "_")}_phase_{exp.attribs["phase"]}__split_{i}.mjpeg', abspath=False)
	exp.mstreams["acq"](acq=filename, phase=exp.attribs["phase"])
	scope.cam.read("vid_mjpeg_tpts", filename, tsec=exp.attribs["chunk_size_sec"], fps=exp.attribs["fps"], exposure_ms=exp.attribs["exposure_ms"], quality=exp.attribs["quality"])
	#scope.cam.read("video", filename, tsec=10)
	exp.sync_file_bg(filename, remove_source=True)

global packup
def packup():
	## Experiment is finishing - therefore sync the whole directory.
	global scope, exp
	exp.sync_dir()
	exp.logs.update(scope.get_config())
	exp.__save__()
	scope.beacon.blink()
	exp.close()
	import schedule
	return schedule.CancelJob

def start_acq():

	global exp, scope, capture, bomdia, bonnoite
	scope.beacon.on() ### Indicate that we have begun.
	exp.sync_dir()
	exp.logs.update(scope.get_config())

	## Set tandh stream.
	tandh = exp.mstreams["tandh"]
	def record_sensor():
		try:
			value = scope.tandh.read()
			value.update({"success":True})
		except:
			print("[red]TandH reading failed![default]")
			value =  {"temp": 0, "humidity":0, "success":False}
		r = tandh(**value)
		r.panel()	
	record_sensor()
	exp.schedule.every(5).minutes.until(timedelta(seconds=exp.attribs["chunk_size_sec"]*exp.attribs["no_chunks"])).do(record_sensor)
	exp.note("Tandh sensors set to record every 5 mins for the next 24 hours, starting now.")
	

	### Schedule day and light changes ---------------------
	exp.schedule.every().days.at("08:00").until(timedelta(days=5)).do(bomdia)
	exp.schedule.every().days.at("20:00").until(timedelta(days=5)).do(bonnoite)
	exp.note("Set day and night circadian cycles.")
	## Assume that its day now
	bomdia()
	## ---------------------------------------------------------


	## Set acquisitions
	exp.schedule.every(1).hours.until(timedelta(days=5)).do(capture)
	exp.note("Set to capture, every 1 hour for the next 5 days, starting now.")
	capture()


	## exp.schedule a packup protocol
	exp.schedule.every(5).days.do(packup)
	exp.note("Packup protocol set to execute at the fifth day.")

	exp.note("Assumed that the motor has been set to perfuse at an appropriate rate.")
	exp.logs.update(scope.get_config())
	exp.__save__()

	exp.note("Now we hope for the best!")

	

