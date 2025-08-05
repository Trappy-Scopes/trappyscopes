from datetime import timedelta



from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from hive.assembly import ScopeAssembly
from expframework.experiment import Experiment 

__description__ = \
"""
Test stability of light source at a set Voltages for long hours (O(days)). Correspondingly also
monitor temperature to correlate its effects.
"""

def create_exp():
	global exp, scope
	exp = Experiment.Construct(["light", "longterm", "stability"])
	tandh = exp.new_measurementstream("lux_sensor_count", measurements=["light", "counts", "temp"])

	## Define a light condition
	exp.attribs["light"] = (2,0,0)
	exp.attribs["sample_period_s"] = 60
	exp.attribs["total_time_hours"] = 24
	exp.attribs["beacon_state"] = True

	scope.beacon.blink()

def start():
	global exp, scope
	
	if exp.attribs["beacon_state"]:
		scope.beacon.on()
	else:
		scope.beacon.off()


	## Read tandh
	photon_counts = exp.mstreams["lux_sensor_count"]
	scope.lit.setVs(*exp.attribs["light"])
	def record_sensor():
		global exp, scope
		try:
			value = scope.sensor.read()
		except:
			print("[red]:Light sensor reading failed![default]")
			value =  {"counts":None, "success":False}
		r = photon_counts(light=exp.attribs["light"], temp=scope.tandh.read()["temp"], **value)
		r.panel()	
	
	## 0th measurement
	record_sensor()
	
	exp.schedule.every(exp.attribs["sample_period_s"]).seconds.until(timedelta(hours=exp.attribs["total_time_hours"])).do(record_sensor)
	print(f'Light sensor value set to record every {exp.attribs["sample_period_s"]} seconds for the next {exp.attribs["total_time_hours"]} hours, starting now.')
	exp.logs.update(scope.get_config())


def stop():
	global exp, scope
	scope.beacon.blink()
	exp.sync_dir()
	exp.close()

