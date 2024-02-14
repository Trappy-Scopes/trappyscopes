import datetime
from time import sleep
import time
from experiment import Calibration
import pprint

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())



fill_mL = 20
exp = Calibration(f"{scopeid}_motor_slowspeed_vs_freq_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
sleep(0)


## Incase of additional pico board
#motor_pico = RPiPicoDevice()
#motor_pico.auto_connect()

#print("Waiting")
#sleep(5)

## Go through different speeds
exp.logs["speed_test"] = []

## extensive
speedset = [0.01, 0.02, 0.03, 0.04, 0.05]
freqset =  [50, int(10**2), int(10**3), int(10**4), int(10**5)]
freqset.reverse()

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} sppeds!")

print(f"Freqs: {freqset}")
print(f"Will test {len(freqset)} frequencies!")


### RT Plot
freqwise = {}


for freq in freqset:
	freqwise[freq] = {"duration": [], "speed":[]}
	print("Iterating over: ", freq, "Hz")

	pico(f"motor.fwdpin.freq = {freq}")
	pico(f"motor.rev.freq = {freq}")
	print(f"Fwd pin freq: {pico('print(motor.fwdpin.freq)')}")

	for i, speed in enumerate(speedset):
		
		print(f"Motor speed: {speed}")
		exp.user_prompt("start")
		start = time.perf_counter()
		
		pico(f"motor.speed({speed})")
		print("Speed updated.")
		
		inp = exp.user_prompt(None, label="stop")  ## Press enter to stop
		print(f"\n\n{inp}\n\n")
		pico("motor.hold()")
		stop = time.perf_counter()

		dur = stop-start
		

		
		result = {"duty":(pico("print(motor.duty)").rstrip("\r\n")), 
				  "speed": speed, "freq":freq,  "duration":dur, "mL":fill_mL,
				  "setup": "open_cylinder", "overflow": 0, "success": (str(inp).strip() != "fail")}
		pprint.pprint(result)
		exp.logs["speed_test"].append(result)


		## RT Terminal plotting
		if result["success"]:
			freqwise[freq]["duration"].append(dur)
			freqwise[freq]["speed"].append(speed)
		else:
			print("Skipping point in RT plotting!")
		plt.clf()
		plt.xlabel(f"duration for filling {fill_mL}mL (seconds)")
		plt.ylabel("normalised speed")
		for freq in freqwise:
			if freqwise[freq]["duration"]:
				plt.plot(freqwise[freq]["duration"], freqwise[freq]["speed"], label=f"{freq}Hz")
		plt.show()

		

pico("motor.hold()")
exp.close()