import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config




description= \
"""
Protocol to measure resolution with several modes - 4 modes. 4 colors, 3 images per channel.

Steps:
	1. Focus and magnification - record a 2mm chamber. At fullframe.
	2. Set configuration -> open-camera --> Open a measurement stream per sensor mode --> Record through all the color channels (X3-iterations)-> Close camera.
	3. Save measurement and acqs (1 image every 5 seconds)
Camera configuration steps followed:
	close-->open-->configure-->start-->close
"""




# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Experiment(f"{scopeid}_still_res_test_usaf_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


print(__name__)
exp.scriptid = __name__

### Configure experiment
exp.attribs.update({"setup" : ["still_resolution_tests", "usaf_test_target"],
					"description" : description,
					"voltage": 2, "itr": 3,  "channels": ["r", "g", "b", "w"], 
				    "res_set":[[1332, 990], [2028, 1080], [2028,1520], [4056, 3040], [1920, 1080]],

				    "magnification": 1.0,
				    "itr" : 3,

				    "exposure_time": 50000,
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "analogue_gain": 3,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,

				    "quality" : 95,
				    "compress_level": 0

				   })


## Configure light
lightmap = {"r": [exp.attribs["voltage"], 0, 0], 
			"g": [0, exp.attribs["voltage"], 0],
			"b": [0, 0, exp.attribs["voltage"]], 
			"w": [exp.attribs["voltage"], exp.attribs["voltage"], exp.attribs["voltage"]]
		   }
print("Registering lit controller!")
if "lit" not in scope:
	lit = RPiPicoDevice.Emit("lit", pico)
	scope.add_device("lit", lit)
	scope.draw_tree()




#### Focusing and magnification recording
exp.user_prompt(None, label="Record 2mm-inhouse trap for magnification calibration at 1X.")
scope.lit.setVs(1,1,1)
sleep(2)
cam.cam.create_still_configuration({"size":exp.attribs["res_set"][3]})
cam.cam.start_and_capture_file("magnification_std.png")
magms = exp.new_measurementstream("magnification")
m = magms(acq="magnification_std.png", config_size=list(cam.cam.still_configuration.sensor["output_size"]),
		  size=cam.cam.still_configuration.size)

exp.user_prompt(None, label="Place the USAF test target and focus at 1X.")
cam.preview(tsec=30)




### Begin experiment ---------------------------------------------------------------------------------
cam.close()  ## Close camera
for res in exp.attribs["res_set"]:

	## Set measurement stream ##########
	ms = exp.new_measurementstream(tuple(res), 
		                       measurements=["usaftt_group", 
		                       			     "usaftt_element", 
		                       			     "min_res_um"]) ## Calculated afterwards	
	tab = ms.tabulate("rV", "gV", "bV", "res", "config_size")

	###################################

	## Set Camera settings:
	cam.close()
	cam.open()

	# create video configuration
	cam.cam.create_still_configuration({"size":res})
	cam.cam.still_configuration.controls.ExposureTime = exp.attribs["exposure_time"]
	cam.cam.still_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
	cam.cam.still_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
	cam.cam.still_configuration.controls.AnalogueGain = exp.attribs["analogue_gain"]
	cam.cam.still_configuration.controls.Brightness   = exp.attribs["brightness"]
	cam.cam.still_configuration.controls.Contrast     = exp.attribs["contrast"]
	cam.cam.still_configuration.controls.ColourGains  = exp.attribs["colour_gains"]
	cam.cam.still_configuration.controls.Sharpness    = exp.attribs["sharpness"]
	cam.cam.still_configuration.controls.Saturation   = exp.attribs["saturation"]
	cam.cam.still_configuration.size = (res[0], res[1])



	### Set compression and quality
	cam.cam.options["quality"] = exp.attribs["quality"]
	cam.cam.options["compress_level"] = exp.attribs["compress_level"]

	read_config =  safepicam2_config(cam.cam.still_configuration)
	print(read_config)
	
	exp.delay("Configuration checking delay", 10)

	for channel in lightmap:

		### Set-light color
		scope.lit.setVs(*lightmap[channel])

		### Capture files
		name = f"res_{res[0]}_{res[1]}_{channel}".replace(".", "pt")
		

		for i in range(exp.attribs["itr"]):
			acq=name+f"_cntr_{i}.png"
			m = ms(rV=lightmap[channel][0], gV=lightmap[channel][1], bV=lightmap[channel][2],
					res=res, magnification=exp.attribs["magnification"], config_size=list(cam.cam.still_configuration.sensor["output_size"]),
					itr_no=i, quality=cam.cam.options["quality"], compression=cam.cam.options["compress_level"], acq=acq
				  )

			exp.dealy("Delay before capture", 5)
			cam.cam.start_and_capture_file(show_preview=True)

			## Print Measurement Table
			print(tab)

		
	### Close camera
	cam.cam.stop_preview()
	cam.close()




# Close experiment
exp.close()