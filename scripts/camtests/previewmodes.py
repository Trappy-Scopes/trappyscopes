import datetime
from experiment import Test
import numpy as np
import time
from picamera2 import Preview
# Start experiment
dt = str(datetime.date.today()).replace("-", "_")
exp = Test(f"{scopeid}_test_previewmodes_{dt}")
test = exp

#cam.config_cammode2()
lit.setVs(0,0.5,0)

no_trials = 10
## Test opening and closing of camera
for i in range(no_trials):

	#sleeping_t = np.round(np.rand() * 10, 2)
	sleeping_t = 5

	## Try QTGL
	cam.preview_type = Preview.QTGL
	print("Trying QTGL mode")
	#test.check(cam.open)
	test.check(cam.is_open)
	test.check(cam.preview)

	
	## Wait
	print(f"{i:2}. {time.perf_counter()} : Sleeping for: {sleeping_t:2} s.")
	sleep(sleeping_t)

	## Try QT
	cam.preview_type = Preview.QT
	print("Trying QT mode")
	#test.check(cam.open)
	test.check(cam.is_open)
	test.check(cam.preview)

	## Wait
	print(f"{i:2}. {time.perf_counter()} : Sleeping for: {sleeping_t:2} s.")
	sleep(sleeping_t)

	## Try QT
	cam.preview_type = Preview.DRM
	print("Trying DRM mode")
	#test.check(cam.open)
	test.check(cam.is_open)
	test.check(cam.preview)



# Close experiment
test.conclude()
test.close()
cam.close()