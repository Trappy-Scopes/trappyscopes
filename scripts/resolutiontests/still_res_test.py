import datetime
from experiment import Test
import numpy as np
import time

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Experiment(f"{scopeid}_still_res_test_usaf_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
test = exp

#cam.config_cammode2()
set_green = lambda : pico("l1.setVs(0,0.5,0)")
set_red = lambda : pico("l1.setVs(0.5,0,0)")
set_blue = lambda : pico("l1.setVs(0,0,0.5)")
set_white = lambda : pico("l1.setVs(0.5,0.5,0.5)")


cam.close()  ## Close camera


res_set = [[1332, 990], [2028, 1080], [2028,1520], [4056, 3040], [1920, 1080]]
exp.logs["results"] = []
exp.logs["res_set"] = res_set


## Test opening and closing of camera
for res in res_set:

	## Set Camera settings:
	cam.close()
	cam.open()
	#cam.configure(res=res)

	fps=20.
	framelimit=int(1000000/fps)
	res_x = 1920
	res_y = 1080
	exposure_time=50000
	awb_enable = False
	ae_enable = False
	brightness = 0.3
	analogue_gain=3
	contrast = 2.5
	colour_gains = (0.,0.)
	sharpness = 1.
	saturation = .5
	

	#define a dictionary with the controls to save in file
	controls={"FrameRate":fps,
	"ExposureTime":exposure_time,
	"AwbEnable":awb_enable,
	"AeEnable":ae_enable,
	"AnalogueGain":analogue_gain,
	"Brightness":brightness,
	"Contrast":contrast,
	"ColourGains":colour_gains,
	"Sharpness":sharpness,
	"Saturation":saturation}

	# create video configuration
	cam.cam.create_still_configuration({"size":res}, controls=controls)

	#the video configuration controls need to be 
	#set again - set only the ones in 'controls'
	cam.cam.still_configuration.controls.FrameRate = fps
	cam.cam.still_configuration.controls.ExposureTime = exposure_time
	cam.cam.still_configuration.controls.AwbEnable = awb_enable
	cam.cam.still_configuration.controls.AeEnable = ae_enable
	cam.cam.still_configuration.controls.AnalogueGain = analogue_gain
	cam.cam.still_configuration.controls.Brightness = brightness
	cam.cam.still_configuration.controls.Contrast = contrast
	cam.cam.still_configuration.controls.ColourGains = colour_gains
	cam.cam.still_configuration.controls.Sharpness = sharpness
	cam.cam.still_configuration.controls.Saturation = saturation
	#cam.still_configuration.controls.ExposureValue = exposure_value
	cam.cam.still_configuration.size = (res_x,res_y)


	lightmap = {"r": set_red, "g":set_green, "b": set_blue, "w":set_white}
	for channel in lightmap:

		### Set-light color
		lightmap[channel]()

		name = f"res_{res[0]}_{res[1]}_{channel}0pt5_"
		cam.cam.start_and_capture_files(name+"{:d}.png", initial_delay=2, delay=5,
										num_files=3)


		result = {"V": 0.5, "channel":channel, "res":res, "magnification": 1, 
				  "name":name, "exp_type":"still_resolution_test_usaf", 
				  "target":"USAF", "group1":None, "group2":None, "min_res_um":None,
				  "res": list(cam.cam.still_configuration.size), 
				  "raw_res": list(cam.cam.still_configuration.sensor["output_size"])
				  "replicate":0}
		from copy import deepcopy
		for i in range(3):
			r = deepcopy(result)
			r["replicate"] = i+1
			exp.logs["results"].append(r)

		#sleeping_t = np.round(np.rand() * 10, 2)
		sleeping_t = 5
		print(f"{i:2}. {time.perf_counter()} : Sleeping for: {sleeping_t:2} s.")
		sleep(sleeping_t)
		
	cam.cam.stop_preview()
	cam.close()




# Close experiment
exp.close()