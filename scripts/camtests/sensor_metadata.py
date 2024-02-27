import datetime
import datetime
from experiment import Calibration
import numpy as np
import time
from perturbations import ColorIterator


### Create the experiment
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Calibration(f"{scopeid}_cam_sensor_metadata_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")

## result - parameters
result = []
exp.logs["results"] = []
print(exp.logs["results"])
iteations = 5
frames = 10
wait_time_s = 10
exp.logs["iterations"] = iteations
exp.logs["frames"] = frames
exp.logs["color_ch_levels"] = 21
exp.logs["wait_time_s"] = wait_time_s
## Start color mixing
mixer = ColorIterator(levels=21, ch=["r", "g", "b", "w"])

exp.unsaved = True
if not cam.is_open():
	cam.open()
cam.cam.start()
litstate = True
index = 0
exp.logs["init_time"] = time.perf_counter()
m = 0
while litstate:
	## Set colour
	litstate = next(mixer, None)
	if litstate:
		pico(f"l1.setVs({litstate[0]}, {litstate[1]}, {litstate[2]})")

		m += 1
		for it in range(iteations):
			sleep(wait_time_s)  ## Do one every minute
			for i in range(frames):
				print(f"<< {index} : {litstate}>>")
				index = index + 1
				md = cam.frame_metadata()
				md["time"] = time.perf_counter()
				md["frame_no"] = i
				md["index"] = index
				md["lit_r"] = litstate[0]
				md["lit_g"] = litstate[1]
				md["lit_b"] = litstate[2]
				md["measurement"] = m
				md["illumination"] = device_metadata["hardware"]["illumination"]

				result.append(md)
				pprint.pprint(md)
				exp.logs["results"] = result
#print(exp.logs["results"])

cam.cam.close()
exp.close()