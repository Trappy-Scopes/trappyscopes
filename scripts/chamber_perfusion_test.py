import datetime
from time import sleep
import time
from experiment import Calibration
import pprint
from colorama import Style, Back

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())

exp = Calibration(f"{scopeid}_chamber_perfusion_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)


## Incase of additional pico board
#motor_pico = RPiPicoDevice()
#motor_pico.auto_connect()

#print("Waiting")
#sleep(5)

## Go through different speeds


## extensive

freq = 10
speedset = [0.00, 0.01, 0.02, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.15, \
			0.2, 0.25, 0.3]


## Set Frequency
pico(f"motor.fwdpin.freq({freq})")
pico(f"motor.revpin.freq({freq})")
print(f"Fwd pin freq: {pico('print(motor.fwdpin.freq())')}")

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} sppeds!")


## Plotting
#plotdata = {"speed": [], "duration": []}

for i, speed in enumerate(speedset):
	
	print(f"Motor speed: {speed}")
	exp.user_prompt("start")
	start = time.perf_counter()


	sleep(10)

	
	pico(f"motor.speed({speed})")
	print("Speed updated.")
	

	### Capture video
	name = f"peristat_speed_{str(speed).replace('.', 'pt')}.h264"
	capture(vid, name, tsec=30)
	### -----

	sleep(5)

	### 
	pico("motor.hold()")
	stop = time.perf_counter()


	dur = stop-start
	result = {"duty":(pico("print(motor.duty)").rstrip("\r\n")), 
			  "speed": speed, "freq":freq,  "duration":dur,
			  "setup": "2mm_inhouse_chambers_syringe_to_syringe", "overflow": 0, "success": None,
		      "experiment_type": "chamber_perfusion_threshold", "acq": name}
	pprint.pprint(result)

	print(f"{Back.RED}{' '*100}{Style.RESET_ALL}")
	print("Acq done!!!")

pico("motor.hold()")
exp.close()