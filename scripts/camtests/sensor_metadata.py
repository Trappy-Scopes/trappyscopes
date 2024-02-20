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
iteations = 5
frames = 10
exp.logs["iterations"] = iteations
exp.logs["frames"] = frames
exp.logs["color_ch_levels"] = 20

## Start color mixing
mixer = ColorIterator(levels=20, ch=["r", "g", "b", "w"])


cam.cam.start()
litstate = True
index = 0
while litstate:
	## Set colour
	litstate = next(mixer, None)
	pico(f"l1.setVs({litstate[0]}, {litstate[1]}, {litstate[2]})")

	for it in range(iteations):
		sleep(10)  ## Do one every minute
		for i in range(frames):
			print(f"<< {index} : {litstate}>>")
			index = index + 1
			md = cam.frame_metadata()
			md["time"] = time.perf_counter()
			md["frame_no"] = i
			md["index"] = index
			md["lit"] = litstate


			result.append(md)
			pprint.pprint(result)
			exp.logs["results"].append(result)
cam.close()
exp.close()