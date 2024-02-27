import datetime
from time import sleep
import time
from experiment import Calibration
import pprint
from colorama import Style, Back
from picodevice import NullRPiPicoDevice, RPiPicoDevice

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())

exp = Calibration(f"{scopeid}_chamber_perfusion_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)


## Incase of additional pico board
#motor_pico = RPiPicoDevice(connect=False)
motor_pico = NullRPiPicoDevice(connect=False)
motor_pico.auto_connect()
#motor_pico.connect("/dev/ttyACM0")
motor_pico.exec_main()
print(motor_pico)
#print("Waiting")
#sleep(5)

## Go through different speeds


## extensive
min_delay_sec = 30
relax_delay_sec = 10
freq = 10
#speedset = [0.00, 0.01, 0.02, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.15, \
#			0.2, 0.25, 0.3]
speedset = [0.032, 0.035, 0.037, 0.04, 0.042, 0.045, 0.047, 0.05, 0.052, 0.055, 0.057, 0.06]


lit_state = (0.5, 0.5, 0.5)
pico(f"l1.setVs{str(lit_state)}")
exp.logs["pwm_freq"] = freq
exp.logs["speedset"] = speedset
exp.logs["lit"] = list(lit_state)
exp.logs["min_delay_sec"] = min_delay_sec
exp.logs["relax_delay_sec"] = relax_delay_sec
exp.logs["results"] = []
## Set Frequency
motor_pico(f"motor.fwdpin.freq({freq})")
motor_pico(f"motor.revpin.freq({freq})")
print(f"Fwd pin freq: {motor_pico('print(motor.fwdpin.freq())')}")

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} speeds!")
###


### Optional - load pipe
print("Load pipe ??????????  -- type ``load-pipe`` ")
if exp.user_prompt(None, label="load-pipe") == "load-pipe":
	exp.log_event("load-pipe-triggered")
	motor_pico("motor.speed(0.5)")
	sleep(7)
	motor_pico("motor.hold()")
	exp.log_event("load-pipe-completed")
####




####  User prompt to start the experiment
print("Ensure that the chamber is loaded - loading acquisition")
exp.user_prompt(None, label="loading-acquisition")
capture(vidmp4, "loading_procedure.mp4", tsec=60*5)     ## Capture chamber without the flow
exp.user_prompt("start-exp")
motor_pico(f"motor.speed({speedset[0]})")
exp.log_event(f"motor-started-speed-{speedset[0]}")
sleep(30)
exp.log_event(f"init-stabilization-{30}s")
####


for i, speed in enumerate(speedset):
	

	### set speed
	print(f"Motor speed: {speed}")
	exp.user_prompt("start")
	motor_pico(f"motor.speed({speed})")
	print("Speed updated.")
	

	## Start and stabilize
	start = time.perf_counter()
	print(f"Stabilization delay of {min_delay_sec} sec.")
	sleep(min_delay_sec)
	

	

	### Capture video
	name = f"peristat_speed_{str(speed).replace('.', '_')}.mp4"
	capture(vidmp4, name, tsec=30)
	### -----


	## Relaxation
	print(f"Relaxation delay of {relax_delay_sec} sec.")
	sleep(relax_delay_sec)
	stop = time.perf_counter()


	## Record measurements
	dur = stop-start
	result = {"duty":(motor_pico("print(motor.duty)").rstrip("\r\n")), 
			  "speed": speed, "freq":freq,  "duration":dur,
			  "setup": "3mm_inhouse_chambers_syringe_to_syringe", "overflow": 0, "success": None,
		      "experiment_type": "chamber_perfusion_threshold", 
		      "acq": name, "lit_state":list(lit_state)}
	pprint.pprint(result)
	exp.logs["results"].append(result)

	## It's done!
	print(f"{Back.RED}{' '*150}{Style.RESET_ALL}")
	print("Measurement done!!!")

## Stop motor and end experiment.
motor_pico("motor.hold()")
exp.close()