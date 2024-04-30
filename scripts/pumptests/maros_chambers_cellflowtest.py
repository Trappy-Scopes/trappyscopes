import datetime
import time
from experiment import Calibration
import pprint
from colorama import Style, Back
from picodevice import NullRPiPicoDevice, RPiPicoDevice

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())



mdevice_type = "maros"
flow_type = "pull"


exp = Calibration(f"{scopeid}_{mdevice_type}_cellflow_test_{flow_type}_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}", append_eid=True)
exp.delay("Init stabilization", 5)


## Incase of additional pico board
#motor_pico = RPiPicoDevice(connect=False)
#motor_pico = NullRPiPicoDevice(connect=False)
#motor_pico.auto_connect()
#motor_pico.connect("/dev/ttyACM0")
#motor_pico.exec_main()
motor_pico = pico
print(motor_pico)
motor_id = "motor2"
motor = scope[motor_id]
print(motor)
cam.close()


from fluidicsdevice import FluidicsDevice
#trap = FluidicsDevice("2mm-inhouse", dia_mm=2, id_="37b8b8c592")
trap = FluidicsDevice("maros_traps", dia_mm=5, id_="2d255a89b2")
exp.logs["fluidicsdevice"] = trap

## extensive
min_delay_sec = 60*10
relax_delay_sec = 30
freq = 10


speedset = []
"""
speedset = [0.027, 0.027, 0.027,
			0.028, 0.028, 0.028,
			0.029, 0.029, 0.029,
			0.030, 0.030, 0.030, \
			0.032, 0.032, 0.032, \
			0.033, 0.033, 0.033, \
			0.034, 0.034, 0.034, \
			0.035, 0.035, 0.035, \
			0.036, 0.036, 0.036,
			0.037, 0.037, 0.037,
			0.038, 0.038, 0.038]
"""
speedovelaps = [0.037, 0.037, 0.037,
				0.038, 0.038, 0.038]
speedset_fast = [0.040, 0.040, 0.040,
				 0.050, 0.050, 0.050,
				 0.070, 0.070, 0.070,
				 0.090, 0.090, 0.090,
				 0.100, 0.100, 0.100,
				 0.120, 0.120, 0.120,
				 0.150, 0.150, 0.150,
				 0.170, 0.170, 0.170,
				 0.190, 0.190, 0.190,
				 0.210, 0.210, 0.210,
				 0.250, 0.250, 0.250]
speedset.extend(speedovelaps)
speedset.extend(speedset_fast)



#speedset.reverse()


exp.logs["pwm_freq"] = freq
exp.logs["speedset"] = speedset
exp.logs["lit"] = "arbitrary"
exp.logs["min_delay_sec"] = min_delay_sec
exp.logs["relax_delay_sec"] = relax_delay_sec
exp.logs["results"] = []
exp.logs["magnification"] = 4
exp.logs["motor_id"] = motor_id


## Set Frequency
motor.fwdpin.freq(freq)
motor.revpin.freq(freq)


print(f"Fwd pin freq: {motor_pico(f'print({motor_id}.fwdpin.freq())')}")

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} speeds!")
###


### Optional - load pipe
print("Load pipe ??????????  -- type ``load-pipe`` ")
if exp.user_prompt(None, label="load-pipe") == "load-pipe":
	exp.log_event("load-pipe-triggered")
	motor.speed(0.5)
	exp.delay("Pump working", 7)
	motor.hold()
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
motor.speed(speedset[0])
exp.log_event(f"motor-started-speed-{speedset[0]}")
exp.delay("Experiment start delay", 30)
exp.log_event(f"init-stabilization-{30}s")
####


for i, speed in enumerate(speedset):
	

	### set speed
	print(f"Motor speed: {speed}")
	motor.speed(speed)
	print("Speed updated.")
	

	## Start and stabilize
	start = time.perf_counter()
	print(f"Stabilization delay of {min_delay_sec} sec.")
	exp.delay("Speed stabilization", min_delay_sec)
	

	

	### Capture video
	name = f"peristat_speed_{i}_{str(speed).replace('.', '_')}.h264"
	os.system(f"libcamera-vid -t {60*3*1000} -f -o {name}")
	### -----


	## Relaxation
	print(f"Relaxation delay of {relax_delay_sec} sec.")
	exp.delay("Buffer delay", relax_delay_sec)
	stop = time.perf_counter()


	## Record measurements
	dur = stop-start
	result = {"duty":(motor_pico(f"print({motor_id}.duty)").rstrip("\r\n")), 
			  "speed": speed, "freq":freq,  "duration":dur,
			  "mdevice": mdevice_type, "flow_type": flow_type,
			  "setup": "syringe_to_syringe", "overflow": 0, "success": None,
		      "experiment_type": "flow_threshold_with_cells", 
		      "acq": name, "lit_state":"arbitrary", "flow":False, "fluidics": trap.__getstate__()}
	pprint.pprint(result)
	exp.logs["results"].append(result)

	## It's done!
	print(f"{Back.RED}{' '*150}{Style.RESET_ALL}")
	print("Measurement done!!!")

## Stop motor and end experiment.
motor.hold()
exp.close()




	### maintain perfusion - maybe?
	## motor_pico("motor.hold()")
