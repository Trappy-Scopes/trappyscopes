from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment 


## Create a calibration context
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
exp = Experiment(f"{scopeid}_{dt}_{time_str}_light_calibration", append_eid=True)
tandh = exp.new_measurementstream("photon_counts", measurements=["light", "photon_count"])

## Define a light condition
exp.attribs["light"] = (2,0,0)
exp.attribs["sample_period_s"] = 60
exp.attribs["total_time_hours"] = 24
scope.beacon.blink()

def start():

	global exp, scope, capture
	scope.beacon.on()


	## Read tandh
	photon_counts = exp.mstreams["photon_counts"]
	scope.lit.setVs(*exp.attribs["light"])
	def record_sensor():
		try:
			value = scope.light_sensor.read()
		except:
			print("[red]:Light sensor reading failed![default]")
			value =  {"light": None, "photon_count":None}
		r = photon_counts(light=exp.attribs["light"], **value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(exp.attribs["sample_period_s"]).seconds.until(timedelta(hours=exp.attribs["total_time_hours"])).do(record_sensor)
	print(f'Light sensor value set to record every {exp.attribs["sample_period_s"]} seconds for the next {exp.attribs["total_time_hours"]} hours, starting now.')
	exp.logs.update(scope.get_config())
	exp.__save__()

def stop():
	global exp, scope, capture
	scope.beacon.blink()
	exp.sync_dir()
	exp.close()

	
