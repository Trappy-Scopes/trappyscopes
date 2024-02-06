import datetime
from time import sleep
import time
from experiment import Calibration
import pprint

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())

exp = Calibration(f"{scopeid}_motor_speedcontrol_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)

#motor_pico = RPiPicoDevice()
#motor_pico.auto_connect()

#print("Waiting")
#sleep(5)

## Go through different speeds
exp.logs["speed_test"] = {}
#speedset = [0.05, 0.10, 0.15, 0.2, 0.25, 0.3, 0.5, 0.75, 0.8, 0.95]
speedset = [1.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, .0]
print(f"Speeds: {speedset}")

for i, speed in enumerate(speedset):
	
	print(f"Motor speed: {speed}")
	exp.user_prompt("start")
	start = time.perf_counter()
	
	pico(f"motor.speed({speed})")
	print("Speed updated.")
	
	exp.user_prompt(None, label="stop")  ## Press enter to stop
	pico("motor.hold()")
	stop = time.perf_counter()

	dur = stop-start
	result = {"duty":pico("motor.duty"), "speed": speed, "freq":10,  "duration":dur, "mL":50, "setup": "open_cylindrical_tubes", "overflow": None}
	pprint.pprint(result)

	exp.logs["speed_test"][i] = result

pico("motor.hold()")
exp.close()