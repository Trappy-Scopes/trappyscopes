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
for i, speed in enumerate([0.1, 0.2, 0.5, 0.8, 0.95]):
	
	print(f"Motor speed: {speed}")
	exp.user_prompt("start")
	start = time.perf_counter()
	
	pico(f"motor.speed({speed})")
	print("Speed updated.")
	
	exp.user_prompt(None, label="stop")  ## Press enter to stop
	pico("motor.hold()")
	stop = time.perf_counter()

	dur = stop-start
	result = {"speed": speed, "freq":10,  "duration":dur, "mL":50}
	pprint.pprint(result)

	exp.logs["speed_test"][i] = result

pico("motor.hold()")
exp.close()