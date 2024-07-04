import datetime
from experiment import Test
import numpy as np
import time


from cleaners import safepicam2_config

from rich.markdown import Markdown
from rich.panel import Panel


description= \
"""

## Test Description

Test the efficacy of the MJPEG encoder (hardware) by perturbing the quality open in picamera2 at [2028, 1520], fps=20 resolution.

Steps:
	
>>	close-->open-->configure-->start-->close
"""
print(Panel(Markdown(description), title="description"))



# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Test(f"{scopeid}_mjpeg_encoder_tests_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
test = exp


exp.scriptid = "mjpeg_encoder_tests"


### Configure experiment
exp.attribs.update({"setup" : ["encoder_tests", "mjpegencoder", "uhd_resolution", "video"],
					"description" : description,
					"voltage": 1.0, "itr": 1,  "channels": ["w"], 
				    "magnification": 2,
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
					"res_set":[[2028,1520]],
					"fps_set" : [20],
					"quality_set" : [0, 5, 10, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90, 95]
				   })

expa = exp.attribs
def configure_picamera(res, fps, quality):
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
	cam.cam.options["quality"] = quality
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

lit = scope.picoprox.lit





### Begin experiment ---------------------------------------------------------------------------------
cam.close()  ## Close camera
lit.setVs(expa["voltage"],expa["voltage"],expa["voltage"])


from picamera2.encoders import Encoder, H264Encoder, JpegEncoder, MJPEGEncoder
encoder_map = {"mjpegencoder": MJPEGEncoder}
extension_map = {"mjpegencoder": "mjpeg"}

ms = exp.new_measurementstream("default", monitors=["encoder", "res", "fps", "duration_s", "acq", "quality"], measurements=["filesize_mb"])
tab = ms.tabulate("measureidx", "acq", "quality", "filesize_mb")
for encoder in encoder_map:
	print(encoder)
	for res in exp.attribs["res_set"]:
		for fps in exp.attribs["fps_set"]:
			
			for quality in exp.attribs["quality_set"]:
				configure_picamera(res, fps, quality)

				for i in range(exp.attribs["itr"]):
					name = f"quality_{quality}_res_{res[0]}_{res[1]}_fps_{fps}_{encoder}_itr_{i}".replace(".", "pt")
					acq=f'{name}.{extension_map[encoder]}'
					try:
						cam.cam.start_recording(encoder_map[encoder](), acq)
					except Exception as e:
						print("Failed!")
						print(e)
						cam.close()
					exp.delay("Recording delay", 30)
					cam.cam.stop_recording()
					#test = exp.testfn(test)
					
					measurement = ms(quality=quality, encoder=encoder, res=res, fps=fps, duration_s=30, acq=acq, 
									 success=None, filesize_mb=round(os.path.getsize(acq)/(pow(1024,2)), 2))
					#measurement.update()
					print(tab)

					exp.delay("Iteration delay", 5)
exp.conclude()
cam.close()
exp.close()



