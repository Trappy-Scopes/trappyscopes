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


## Incase of additional pico board
#motor_pico = RPiPicoDevice()
#motor_pico.auto_connect()

#print("Waiting")
#sleep(5)

## Go through different speeds
exp.logs["speed_test"] = {}
#speedset = [0.05, 0.10, 0.15, 0.2, 0.25, 0.3, 0.5, 0.75, 0.8, 0.95]
#speedset = [0.99, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09]

## extensive
fill_mL = 20
freq = 10
speedset = [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.15, \
			0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 0.8, 0.95, 0.99]


## Set Frequency
pico(f"motor.fwdpin.freq({freq})")
pico(f"motor.revpin.freq({freq})")
print(f"Fwd pin freq: {pico('print(motor.fwdpin.freq())')}")

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} sppeds!")


## Plotting
plotdata = {"speed": [], "duration": []}

for i, speed in enumerate(speedset):
	
	print(f"Motor speed: {speed}")
	exp.user_prompt("start")
	start = time.perf_counter()
	
	pico(f"motor.speed({speed})")
	print("Speed updated.")
	
	inp = exp.user_prompt(None, label="stop")  ## Press enter to stop
	pico("motor.hold()")
	stop = time.perf_counter()

	dur = stop-start
	result = {"duty":(pico("print(motor.duty)").rstrip("\r\n")), 
				  "speed": speed, "freq":freq,  "duration":dur, "mL":fill_mL,
				  "setup": "ibidi_0pt2mm_syringe_to_syringe", "overflow": 0, "success": (str(inp).strip() != "fail"),
				  "experiment_type": "pwm_freq_perturbation"}
	pprint.pprint(result)

	exp.logs["speed_test"][i] = result

	plotdata["speed"].append(speed)
	plotdata["duration"].append(dur)


	## Plot duration vs speed
	plt.clf()
	plt.xlabel(f"duration for filling {fill_mL}mL (seconds)")
	plt.ylabel("normalised speed")

	plt.plot(plotdata["duration"], plotdata["speed"], label=f"{freq}Hz")
	plt.show()
pico("motor.hold()")
exp.close()