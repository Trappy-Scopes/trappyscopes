from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from experiment import Calibration



## Create a calibration context
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
exp = Calibration(f"{scopeid}_{dt}_{time_str}_tandh_calibration", append_eid=True)
tandh = exp.new_measurementstream("tandh", measurements=["temp", "humidity"])

## Define a light condition
exp.attribs["light"] = (2,0,0)
exp.attribs["sample_period_s"] = 60
exp.attribs["total_time_hours"] = 24
scope.beacon.blink()

def start():

	global exp, scope, capture
	scope.beacon.on()


	## Read tandh
	tandh = exp.mstreams["tandh"]
	scope.lit.setVs(*exp.attribs["light"])
	def record_sensor():
		try:
			value = scope.tandh.read()
		except:
			print("[red]TandH reading failed![default]")
			value =  {"temp": None, "humidity":None}
		r = tandh(**value)
		r.panel()	
	
	record_sensor()
	exp.schedule.every(exp.attribs["sample_period_s"]).seconds.until(timedelta(hours=exp.attribs["total_time_hours"])).do(record_sensor)
	print(f'Tandh sensors set to record every {exp.attribs["sample_period_s"]} seconds for the next {exp.attribs["total_time_hours"]} hours, starting now.')
	exp.logs.update(scope.get_config())
	exp.__save__()

def stop():
	global exp, scope, capture
	scope.beacon.blink()
	exp.sync_dir()
	exp.close()

	
