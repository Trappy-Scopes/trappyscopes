import datetime
from experiment import Test
import numpy as np
import time

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Test(f"{scopeid}_test_cameraclosure_{dt}")
test = exp

#cam.config_cammode2()
lit.setVs(0,0.5,0)
cam.close()

## Test opening and closing of camera
for i in range(15):
	test.check(cam.open)
	test.check(cam.is_open)

	#sleeping_t = np.round(np.rand() * 10, 2)
	sleeping_t = 5
	print(f"{i:2}. {time.perf_counter()} : Sleeping for: {sleeping_t:2} s.")
	sleep(sleeping_t)
	
	test.check(cam.close)
	print(f"{i:2}. {time.perf_counter()} : Sleeping for: {sleeping_t:2} s.")
	sleep(sleeping_t)


test.conclude()
# Close experiment
test.close()