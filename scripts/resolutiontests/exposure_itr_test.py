import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config




description= \
"""
Protocol to measure the relationship between the exposure-time and snr.

Steps:
	0. We assume that our fps in 20. Hence, maximum exposure time is 50,000 .
	1. Set configuration -> open-camera --> Open a measurement stream per measurement type --> Record through all the color channels (X3-iterations)-> Close camera.
	2. Save measurement and acqs (1 image every 5 seconds)
Camera configuration steps followed:
	close-->open-->configure-->start-->close
"""




# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Experiment(f"{scopeid}_exposure_time_test_usaf_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


print(__name__)
exp.scriptid = __name__

max_exposure_time = 50000
### Configure experiment
exp.attribs.update({"setup" : ["still_resolution_tests", "usaf_test_target", "exposure_time_tests"],
					"description" : description,
					"voltage": 2, "itr": 3,  "channels": ["r", "g", "b", "w"], 
				    "res_set":[[4056, 3040]], ## Only do fullframe

				    "magnification": 2.0,
				    "itr" : 3,
				    "channels" : "rgbw",
				    "exposure_time": max_exposure_time,
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "analogue_gain": 1,
				    "digital_gain":1,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,

				    "quality" : 95,
				    "compress_level": 0,
				    "exposure_time_set" : [int(max_exposure_time*0.1), int(max_exposure_time*0.3), 
				    					   int(max_exposure_time*0.5), int(max_exposure_time*0.7), 
				    					   int(max_exposure_time*0.9), int(max_exposure_time*1.0)]
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





### Begin experiment ---------------------------------------------------------------------------------
cam.close()  ## Close camera
res = exp.attribs["res_set"][0]
for exposure in exp.attribs["exposure_time_set"]:

	## Set measurement stream ##########
	ms = exp.new_measurementstream(tuple(res), 
		                       measurements=["usaftt_group", 
		                       			     "usaftt_element", 
		                       			     "min_res_um"],
		                       	monitors=["rV", "gV", "bV", "res", "exposure_time_us"]) ## Calculated afterwards
	print(ms)
	tab = ms.tabulate("measureidx", "rV", "gV", "bV", "res", "exposure_time_us")

	###################################

	## Set Camera settings:
	cam.close()
	cam.open()

	# create video configuration
	cam.cam.create_still_configuration({"size":res})
	cam.cam.still_configuration.controls.ExposureTime = exposure
	cam.cam.still_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
	cam.cam.still_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
	cam.cam.still_configuration.controls.AnalogueGain = exp.attribs["analogue_gain"]
	cam.cam.still_configuration.controls.DigitalGain = exp.attribs["digital_gain"]
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

	for channel in exp.attribs["channels"]:

		### Set-light color
		scope.lit.setVs(*lightmap[channel])

		### Capture files
		name = f"res_{res[0]}_{res[1]}_{channel}_exposure_{exposure}".replace(".", "pt")
		

		for i in range(exp.attribs["itr"]):
			acq=name+f"_cntr_{i}.png"
			m = ms(rV=lightmap[channel][0], gV=lightmap[channel][1], bV=lightmap[channel][2],
					res=res, magnification=exp.attribs["magnification"], 
					#config_size=list(cam.cam.still_configuration.sensor["output_size"]),
					itr_no=i, quality=cam.cam.options["quality"], compression=cam.cam.options["compress_level"], acq=acq,
					exposure_time_us=exposure 
				  )

			exp.delay("Delay before capture", 5)
			cam.cam.start_and_capture_file(acq, show_preview=True)

			## Print Measurement Table
			print(tab)

		
	### Close camera
	cam.cam.stop_preview()
	cam.close()




# Close experiment
##exp.close()