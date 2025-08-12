import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config

from rich.markdown import Markdown
from rich.panel import Panel


description= \
"""
Test to check if the camera can dump raw videos at various resolutions.

Steps:
	
	close-->open-->configure-->start-->close
"""
print(Panel(Markdown(description), title="description"))



# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Test(f"{scopeid}_all_encoder_tests_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


exp.scriptid = "all_encoder_tests"


### Configure experiment
exp.attribs.update({"setup" : ["encoder_tests", "rawencoder", "nullencoder"],
					"description" : description,
					"voltage": 1.0, "itr": 1,  "channels": ["w"], 
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

				    #"camera_set" : ["picamera2", "libcamera"],
					#"encoder_set": ["h264", "yuv420"], 
					"res_set":[[2028,1520], [1520,1520]],
					"fps_set" : [20, 30]
				   })


def configure_picamera(res, fps):
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
	

	cam.cam.video_configuration.controls.FrameRate = fps

	cam.cam.video_configuration.size  = (res[0], res[1])
	cam.cam.video_configuration.queue  = exp.attribs["queue"]
	cam.cam.video_configuration.buffer_count  = 6


	### Set compression and quality
	cam.cam.options["quality"] = exp.attribs["quality"]
	cam.cam.options["compress_level"] = exp.attribs["compress_level"]


	## Print -> set configuration
	read_config =  safepicam2_config(cam.cam.video_configuration)
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
scope.lit.setVs(1,1,1)


from picamera2.encoders import Encoder, H264Encoder, JpegEncoder, MJPEGEncoder
encoder_map = {"raw_encoder" : Encoder, "jpegencoder": JpegEncoder, "mjpegencoder": MJPEGEncoder, "h264encoder": H264Encoder}
extension_map = {"h264encoder": "h264", "jpegencoder": "mjpeg", "mjpegencoder": "mjpeg", "raw_encoder" : "yuv420"}

ms = exp.new_measurementstream("default", monitors=["encoder", "res", "fps", "duration_s", "acq"])
for encoder in encoder_map:
	for res in exp.attribs["res_set"]:
		for fps in exp.attribs["fps_set"]:
			
			configure_picamera(res, fps)

			for i in range(exp.attribs["itr"]):
				name = f"res_{res[0]}_{res[1]}_fps_{fps}_{encoder}_itr_{i}".replace(".", "pt")
				
				try:
					cam.cam.start_recording(encoder_map[encoder](), f'{name}.{extension_map[encoder]}')
				except Exception as e:
					print("Failed!")
					print(e)
					cam.close()
				exp.delay("Recording delay", 30)
				cam.cam.stop_recording()
				#test = exp.testfn(test)
				#measurement = ms(encoder=encoder, res=res, fps=fps, duration_s=5, acq=name, success=test)

				exp.delay("Iteration delay", 5)
exp.conclude()
cam.close()
exp.close()



