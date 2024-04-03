import datetime
from experiment import Test
import numpy as np
import time

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Experiment(f"{scopeid}_test_cameraclosure_{dt}")
test = exp

#cam.config_cammode2()
set_green = lambda : pico("l1.setVs(0,0.5,0)")
set_red = lambda : pico("l1.setVs(0.5,0,0)")
set_blue = lambda : pico("l1.setVs(0,0,0.5)")
set_white = lambda : pico("l1.setVs(0.5,0.5,0.5)")


cam.close()  ## Close camera



## Test opening and closing of camera
for res in res_set:

	## Set Camera settings:
	cam.close()
	cam.configure()


	for channel in [set_red, set_green, set_blue, set_white]:


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