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

exp = Calibration(f"{scopeid}_inhouse_chambers_cellflow_test_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)


## Incase of additional pico board
#motor_pico = RPiPicoDevice(connect=False)
#motor_pico = NullRPiPicoDevice(connect=False)
#motor_pico.auto_connect()
#motor_pico.connect("/dev/ttyACM0")
#motor_pico.exec_main()
motor_pico = pico
print(motor_pico)
cam.close()




## extensive
min_delay_sec = 60*10
relax_delay_sec = 30
freq = 10
#speedset = [0.00, 0.01, 0.02, +0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.15, \
#			0.2, 0.25, 0.3]
speedset = [0.030, 0.030, 0.030, \
			0.032, 0.032, 0.032, \
			0.033, 0.033, 0.033, \
			0.034, 0.034, 0.034, \
			0.035, 0.035, 0.035, \
			0.036, 0.036, 0.036]
#speedset.reverse()


exp.logs["pwm_freq"] = freq
exp.logs["speedset"] = speedset
exp.logs["lit"] = "arbitrary"
exp.logs["min_delay_sec"] = min_delay_sec
exp.logs["relax_delay_sec"] = relax_delay_sec
exp.logs["results"] = []
exp.logs["magnification"] = 4


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
##
os.system(f"libcamera-vid -t {60*3*1000} -f -o {'loading_procedure.h264'}")
#capture(vidmp4, "loading_procedure.mp4", tsec=60*3)     ## Capture chamber without the flow

# - Another optional loading run --- have infinite of these
print("Another loading run - type ``more-load`` ")
if exp.user_prompt(None, label="more-load") == "more-load":
	os.system(f"libcamera-vid -t {60*3*1000} -f -o {'loading_procedure2.h264'}")


### Start Experiment
exp.user_prompt("start-exp")
motor_pico(f"motor.speed({speedset[0]})")
exp.log_event(f"motor-started-speed-{speedset[0]}")
sleep(30)
exp.log_event(f"init-stabilization-{30}s")
####


for i, speed in enumerate(speedset):
	

	### set speed
	print(f"Motor speed: {speed}")
	motor_pico(f"motor.speed({speed})")
	print("Speed updated.")
	

	## Start and stabilize
	start = time.perf_counter()
	print(f"Stabilization delay of {min_delay_sec} sec.")
	sleep(min_delay_sec)
	

	

	### Capture video
	name = f"peristat_speed_{i}_{str(speed).replace('.', '_')}.h264"
	os.system(f"libcamera-vid -t {60*3*1000} -f -o {name}")
	### -----


	## Relaxation
	print(f"Relaxation delay of {relax_delay_sec} sec.")
	sleep(relax_delay_sec)
	stop = time.perf_counter()


	## Record measurements
	dur = stop-start
	result = {"duty":(motor_pico("print(motor.duty)").rstrip("\r\n")), 
			  "speed": speed, "freq":freq,  "duration":dur,
			  "setup": "in_house_syringe_to_syringe", "overflow": 0, "success": None,
		      "experiment_type": "flow_threshold_with_cells", 
		      "acq": name, "lit_state":"arbitrary", "flow":False}
	pprint.pprint(result)
	exp.logs["results"].append(result)

	## It's done!
	print(f"{Back.RED}{' '*150}{Style.RESET_ALL}")
	print("Measurement done!!!")

## Stop motor and end experiment.
motor_pico("motor.hold()")
exp.close()




	### maintain perfusion - maybe?
	## motor_pico("motor.hold()")
