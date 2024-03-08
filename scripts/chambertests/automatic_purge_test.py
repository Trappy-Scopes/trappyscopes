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

exp = Experiment(f"{scopeid}_automatic_chamber_purge_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)


## Incase of additional pico board
#motor_pico = RPiPicoDevice(connect=False)
#motor_pico = NullRPiPicoDevice(connect=False)
#motor_pico.auto_connect()
#motor_pico.connect("/dev/ttyACM0")
#motor_pico.exec_main()
#print(motor_pico)


## OR
motor_pico = pico


### Lights
lit_state = (0.5, 0.5, 0.3)
pico(f"l1.setVs{str(lit_state)}")


#### Configuration
condset = [{"pulses":1, "rev_pulses":1, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034},
		   {"pulses":2, "rev_pulses":1, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":3, "rev_pulses":1, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":4, "rev_pulses":1, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":5, "rev_pulses":1, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":1, "rev_pulses":2, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":1, "rev_pulses":3, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":1, "rev_pulses":4, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		   {"pulses":1, "rev_pulses":5, "halfperiod_s":0.5, "high_speed":0.06, "decline_step":0.001, "decline_dealy_s":0.1, "low_speed":0.034}
		  ]
### ---------------
exp.logs["results"] = []
counter = 0

#### Purge function
def motor_purge(motor_pico, pulses = 5, rev_pulses = 1, halfperiod_s = 0.5, 
				high_speed = 0.06, decline_step = 0.01, decline_dealy_s = 1,
				low_speed = 0.35):
	### Initial push
	motor_pico(f"motor.fwd({0.4})")
	sleep(10)


	### Forwarrd Pulses
	for i in range(pulses):
		## Large oscillations
		motor_pico(f"motor.fwd({high_speed})")
		sleep(halfperiod_s)
		motor_pico("motor.hold()")
		sleep(halfperiod_s)
		## ------------------

	## Reverse pulses lock
	for i in range(rev_pulses):
		motor_pico(f"motor.rev({high_speed})")
		sleep(halfperiod_s)
		motor_pico("motor.hold()")
		sleep(halfperiod_s)

	## Relax
	for i in range(int((high_speed-low_speed)/decline_step)):
		motor_pico(f"motor.speed({high_speed-(i*decline_step)})")
		sleep(1)

	### maintain perfusion - maybe?
	motor_pico("motor.hold()")
####


## Explore some conditions
for condition in condset:

	## Assert that there are some bubbles in the setup
	counter = counter + 1
	start = time.perf_counter() # ------------------------------- Measurement point begins here

	condition_str = str(condition).replace("[", "").replace("]", "").replace(" ", "").replace(",", "_")
	
	print("Assert that there are bubbles in here!")
	while(exp.user_prompt("go") != "go"):
		cam.preview(10)
	capture(img, f"{condition_str}_bubbles.png")

	cam.start_capture(vid, f"{condition_str}_purge_process.h264")
	sleep(1)
	motor_purge(motor_pico, **condition)
	sleep(5)
	cam.stop_capture()

	capture(img, f"{condition_str}_post_purge.png")


	end = time.perf_counter() # -------------------------------- Measurement point ends here


	ur = stop-start
	result = {"index": counter, "duration":dur,
			  "setup": "2mm_inhouse_chambers_syringe_to_syringe", "overflow": 0, "success": None,
		      "experiment_type": "automatic_purge", 
		      "acq": condition_str, "lit_state":list(lit_state), 
		      "traps_closed": False, "flow_observed": True, "pressure_waves": True, 
		      "beads_seen": False, "bubbles": True, "bubbles_reduced": False}
	result.extend(condition)
	pprint.pprint(result)
	exp.logs["results"].append(result)

## Stop motor and end experiment.
motor_pico("motor.hold()")
exp.close()


