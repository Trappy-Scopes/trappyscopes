import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config




description= \
"""
Test to check the capacity of encoders w.r.t. to maximum framerate and resolution.

We r=test for the following conditions:
1. fps: 20, 30
2. resolution (size parameter): [2028,1520], [1520,1520]
3. Camera/library : picamera2, libcamera.
4. Encoders: h264 (hardware accelerated), yuv420 (close to raw)


Perturbation steps:
	|
	|- Camera/Type
       |- Encoder
       	   |- Resolution
       	   		|- FPS



Steps:
	
	close-->open-->configure-->start-->close
"""




# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Test(f"{scopeid}_picamera2_and_libcamera_encoder_tests_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


exp.scriptid = "picamera2_and_libcamera_encoder_tests"


### Configure experiment
exp.attribs.update({"setup" : ["encoder_tests", "h264encoder", "yuv420encoder"],
					"description" : description,
					"voltage": 1.0, "itr": 3,  "channels": ["w"], 
				    "magnification": 1.0,
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "analogue_gain": 2,
				    "digital_gain":1,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,
				    "exposure_time_us" : 50000,
				    "queue"      : False,


				    "quality" : 95,
				    "compress_level": 0,

				    "camera_set" : ["picamera2", "libcamera"],
					"encoder_set": ["h264", "yuv420"], 
					"res_set":[[2028,1520], [1520,1520]],
					"fps" : [20, 30]
				   })


def configure_picamera(res, exposure, again):
	## Set Camera settings:
	cam.close()
	cam.open()

	# create video configuration
	cam.cam.create_video_configuration({"size":res})
	cam.cam.video_configuration.controls.ExposureTime = exp.attribs["exposure_time_us"]
	cam.cam.video_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
	cam.cam.video_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
	cam.cam.video_configuration.controls.AnalogueGain = exp.attribs["analogue_gain"]
	#cam.cam.still_configuration.controls.DigitalGain = exp.attribs["digital_gain"]
	cam.cam.video_configuration.controls.Brightness   = exp.attribs["brightness"]
	cam.cam.video_configuration.controls.Contrast     = exp.attribs["contrast"]
	cam.cam.video_configuration.controls.ColourGains  = exp.attribs["colour_gains"]
	cam.cam.video_configuration.controls.Sharpness    = exp.attribs["sharpness"]
	cam.cam.video_configuration.controls.Saturation   = exp.attribs["saturation"]

	cam.cam.video_configuration.size  = (res[0], res[1])
	cam.cam.video_configuration.queue  = exp.attribs["queue"]
	cam.cam.video_configuration.buffer_count  = 6


	### Set compression and quality
	cam.cam.options["quality"] = exp.attribs["quality"]
	cam.cam.options["compress_level"] = exp.attribs["compress_level"]


	## Print -> set configuration
	read_config =  safepicam2_config(cam.cam.still_configuration)
	print(read_config)





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


### Picamera

for encoders in h264encoder
yuv420encoder



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
	#cam.cam.still_configuration.controls.DigitalGain = exp.attribs["digital_gain"]
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