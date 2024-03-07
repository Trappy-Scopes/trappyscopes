import datetime
from time import sleep
import time
from experiment import Calibration
import pprint
from colorama import Style, Back
from abcs.motor import AbstractMotor


# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())

exp = Calibration(f"{scopeid}_ibidi_pump_pressure_trapclosure_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)

cam.close()
## Incase of additional pico board
pump = AbstractMotor() ## NullDevice



## extensive
min_delay_sec = 30
relax_delay_sec = 10




pressureset = [100, 90, 80,70, 60, 50, 40 ,30, 20, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]



### Experimental info
exp.logs["pressureset"] = pressureset
exp.logs["min_delay_sec"] = min_delay_sec
exp.logs["relax_delay_sec"] = relax_delay_sec
exp.logs["results"] = []
exp.logs["magnification"] = 4




### Optional - load pipe
print("Purge ??????????  -- type ``purge`` And start pump at 100")
if exp.user_prompt(None, label="purge") == "purge":
	exp.log_event("purge-triggered")
	os.system(f"libcamera-vid -t {3*60*1000} -f")
####


### Start Experiment
exp.user_prompt("start-exp")
print(f"Please set the pump to {pressureset[0]} mbarr.")
sleep(30)
exp.log_event(f"init-stabilization-{30}s")
####


for i, pressure in enumerate(pressureset):
	

	### set pressure
	print(f"Pump pressure: {pressure} mbarr. Please adjust the pump settings and trigger.")
	exp.user_prompt("start")

	## Start and stabilize
	start = time.perf_counter()
	print(f"Stabilization delay of {min_delay_sec} sec.")
	sleep(min_delay_sec)
	

	

	### Capture video
	name = f"ibidipump_pressure_{str(pressure).replace('.', '_')}.h264"
	os.system(f"libcamera-vid -t {1*60*1000} -f -o {name}")
	### -----


	## Relaxation
	print(f"Relaxation delay of {relax_delay_sec} sec.")
	sleep(relax_delay_sec)
	stop = time.perf_counter()


	## Record measurements
	dur = stop-start
	
	result = {
			  "pressure": pressure,  "duration":dur,
			  "setup": "ibidi_pressure_controlled_pump", "chamber_type":"inhouse_4mm", "success": None,
		      "experiment_type": "chamber_perfusion_threshold", 
		      "acq": name, "lit_state":"arbitrary", "microscope":"vwr",
		      }
	pprint.pprint(result)
	exp.logs["results"].append(result)

	## It's done!
	print(f"{Back.RED}{' '*150}{Style.RESET_ALL}")
	print("Measurement done!!!")

## Stop motor and end experiment.

exp.close()

