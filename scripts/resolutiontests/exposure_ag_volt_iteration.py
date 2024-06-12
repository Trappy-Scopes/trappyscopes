import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config




description= \
"""
Protocol to measure the relationship between exposure time, analogue gain, and forward voltage of the led vs the snr of the image and the calculated lux.

Steps:
	0. Set configuration -> open-camera --> Open a measurement stream per measurement type --> Record through all the color channels (X3-iterations)-> Close camera.
	1. For each Analogue Gain -> Iterate through each volt and color --> For each of these --> Iterate through each exposure value.
	2. Save measurement and acqs (1 image every 3 seconds) and metadata values.

Camera configuration steps followed:
	close-->open-->configure-->start-->close
"""




# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Experiment(f"{scopeid}_exposuretime_ag_fwdvolt_test_usaf_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


exp.scriptid = "exposuretime_ag_fwdvolt_test_usaf"



### Configure experiment
exp.attribs.update({"setup" : ["still_resolution_tests", "usaf_test_target", "exposure_time_tests", "analogue_gain_tests", "fwd_volt_tests", "lux_tests"],
					"description" : description,
					"limits" : {"voltage": 3.0, "exposure_time_us": 50000, "analogue_gain": 5},
					"itr": 1,  
					"channels": ["r", "g", "b", "w"], 
				    "res_set":[[2028,1520]], ## Only do fullframe

				    "magnification": 1.0,

				    
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "digital_gain":1,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,
				    "queue"      : False,

				    "quality" : 95,
				    "compress_level": 0,
				   })


exp.attribs.update({"exposure_time_set" : [int(exp.attribs["limits"]["exposure_time_us"]*0.1), int(exp.attribs["limits"]["exposure_time_us"]*0.3), 
				    					   int(exp.attribs["limits"]["exposure_time_us"]*0.5), int(exp.attribs["limits"]["exposure_time_us"]*0.7), 
				    					   int(exp.attribs["limits"]["exposure_time_us"]*0.9), int(exp.attribs["limits"]["exposure_time_us"]*1.0)],
				    "voltage_set" : [1.0, 1.5, 2.0, 2.5, 3.0],
				    "analogue_gain_set": [1,2,3,4,5]
				   })


## Configure light ->
def get_lightconditions(ch, volt):
	lightmap = {"r": [volt, 0, 0], 
				"g": [0, volt, 0],
				"b": [0, 0, volt], 
				"w": [volt, volt, volt]}
	return lightmap[ch]


def configure_camera(res, exposure, again):
	## Set Camera settings:
	cam.close()
	cam.open()

	# create video configuration
	cam.cam.create_still_configuration({"size":res})
	cam.cam.still_configuration.controls.ExposureTime = exposure
	cam.cam.still_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
	cam.cam.still_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
	cam.cam.still_configuration.controls.AnalogueGain = again
	#cam.cam.still_configuration.controls.DigitalGain = exp.attribs["digital_gain"]
	cam.cam.still_configuration.controls.Brightness   = exp.attribs["brightness"]
	cam.cam.still_configuration.controls.Contrast     = exp.attribs["contrast"]
	cam.cam.still_configuration.controls.ColourGains  = exp.attribs["colour_gains"]
	cam.cam.still_configuration.controls.Sharpness    = exp.attribs["sharpness"]
	cam.cam.still_configuration.controls.Saturation   = exp.attribs["saturation"]

	cam.cam.still_configuration.size  = (res[0], res[1])
	cam.cam.still_configuration.queue  = exp.attribs["queue"]

	### Set compression and quality
	cam.cam.options["quality"] = exp.attribs["quality"]
	cam.cam.options["compress_level"] = exp.attribs["compress_level"]


	## Print -> set configuration
	read_config =  safepicam2_config(cam.cam.still_configuration)
	print(read_config)


print("Registering lit controller!")
if "lit" not in scope:
	lit = RPiPicoDevice.Emit("lit", pico)
	scope.add_device("lit", lit)
	scope.draw_tree()





### Begin experiment ---------------------------------------------------------------------------------
cam.close()  ## Close camera




## Begin iterations
for res in exp.attribs["res_set"]:                                  ## 0
	for ch in exp.attribs["channels"]:                              ## 1
		ms = exp.new_measurementstream(ch,                          ## 1 
			 measurements=["usaftt_group", "usaftt_element",        ## 1
			               "min_res_um", "Lux"],                    ## 1
			 monitors=["channel", "volt",                           ## 1
			           "again",  "exposure_time_us"])               ## 1 
		tab = ms.tabulate("measureidx", "channel",                  ## 1
						  "volt", "again", "Lux",                   ## 1
						  "exposure_time_us", title=ch)             ## 1
		print(tab)													## 1
		## -------------------------------------------------------  ## 1
		for volt in exp.attribs["voltage_set"]:                     ## 2
			### Set-light color                                     ## 2
			scope.lit.setVs(*get_lightconditions(ch, volt))         ## 2
			### --------------------------------------------------- ## 2		
			for again in exp.attribs["analogue_gain_set"]:          ## 3
				for exposure in exp.attribs["exposure_time_set"]:   ## 4
						## Configure camera
						configure_camera(res, exposure, again)
						exp.delay("Configuration checking delay", 5)
						

						### Acquire image & metadata
						name = f"res_{res[0]}_{res[1]}_{ch}_exposure_{volt}V_exposureus_{exposure}_again_{again}".replace(".", "pt")

						### --------------------------------------  ## 5
						for i in range(exp.attribs["itr"]):
							
							## Capture image
							acq=name+f"_cntr_{i}.png"
							cam.cam.start_and_capture_file(acq, show_preview=True)
							cam.cam.stop_preview()
							cam.cam.stop()
							

							## Capture metadata
							cam.cam.start()
							frame_metadata = cam.frame_metadata()

							lightmap = get_lightconditions(ch, volt)
							measurement = ms(channel=ch, voltage=volt, again=again, exposure_time_us=exposure,
											 rV=lightmap[0], gV=lightmap[1], bV=lightmap[2],
											 res=res, magnification=exp.attribs["magnification"], itr_no=i, 
											 acq=acq, acq_fullpath=os.path.join(exp.exp_dir, acq), *frame_metadata)
							
							## Print Measurement Table
							print(tab)


							## Delay during iteration
							if exp.attribs["itr"] > 1:
								exp.delay("Delay between captures", 3)
		

						

		
	### Close camera
	cam.cam.stop_preview()
	cam.close()




# Close experiment
##exp.close()