from abcs.camera import AbstractCamera

from pprint import pprint, pformat
import logging as log
import numpy as np
import time

from picamera2 import Picamera2, Preview
from picamera2.outputs import FfmpegOutput, FileOutput
from picamera2.encoders import H264Encoder, Quality

class Camera(AbstractCamera):
	"""
	Camera object framework specialised for Raspberry Pi HQ Camera.
	Implementation used Picamera v2 python library.

	config parameter can be used to pass a configuration dict.
	"""
	# 1
	def __init__(self, config={}):
		self.cam = Picamera2()
		self.opentime_ns = time.perf_counter()
		log.info("PiCamera2 Camera was opened.") # Constructor opens the cam.

		# Capture Modes for this implementation
		self.modes = {
					  "preview"      : self.preview,
					  "image"        : self.__image__,
					  "image_trig"   : self.__image_trig__,
					  "timelapse"	 : self.__timelapse__,
					  "video"	     : self.__video__,
					  "videomp4"     : self.__videomp4__,
					  "video_noprev" : self.__video_noprev__,
					  "video_raw"    : self.__video_raw__,
					  "ndarray"		 : self.__ndarray__,
					  "stream"		 : self.__stream__
					 }


		# Video Encoders and image quality parameters
		self.encoderh264 = H264Encoder()
		self.cam.options["quality"] = 95
		self.cam.options["compress_level"] = 0

		self.config = config

		# Configurations
		self.still_config = self.cam.create_video_configuration()
		self.video_config = self.cam.create_video_configuration()
		self.preview_config = self.create_still_configuration()


		# Configuration Setting Functions
		self.config_default =  lambda : self.configure(res=(1980, 1080), fps=30)
		self.config_default2 = lambda : self.configure(res=(2028, 1080), fps=30)
		self.config_largeres = lambda : self.configure(res=(4056, 3040), fps=10)
		self.config_largefps = lambda : self.configure(res=(1332, 990), fps=120)


	# 2
	def open(self):
		self.cam.close()
		self.cam.start()
		log.info("PiCamera2 Camera was opened.")

	def is_open(self):
		return self.cam.is_open

	# 3
	def close(self):
		self.cam.close()
		log.info("PiCamera2 Camera was closed.")

	# 4
	def configure(self, fps=30, res=[1920, 1080],  config=None, mode=None):
		"""
		Configure the base settings of the camera.
		The rest are set based on the capture mode.
		"""

		# Ignoring config_file option for now.
		self.config["controls"] = {
			"ExposureTime": 1000,
			
			"AnalogueGain": 1,
			"AeEnable"    : False,
			"AwbEnable"   : False,
			#"ColorGains"  : (1,1), # AWB[0.0, 32.0]. Setting disables Auto AWB
			#"Afmode": controls.AfModeEnums.Manual,

			"Sharpness"   : 0, # [0.0, 16.0]
			"Saturation"  : 1.0, # Set 0 for grayscale. [0.0, 32.0]
			#"NoiseReductionMode" : draft.NoiseReductionModeEnum.Off, # Or use Fast
			"Contrast"    : 1.0, # [0.0, 32.0]
			"Brightness"  : 0.0, # [-1.0, 1-0]

			}
		self.cam.set_controls(self.config["controls"])

		print(f"Setting fps:{fps} and resolution:{res}")
		frameduration = int((1/fps)*1**6)
		framedurationlim = (frameduration, frameduration)
		
		self.still_config["size"] = tuple(res)
		self.still_config["controls"]["FrameDurationLimits": framedurationlim]
		self.video_config["size"] = tuple(res)
		self.video_config["controls"]["FrameDurationLimits": framedurationlim]
		self.preview_config["size"] = tuple(res)
		self.preview_config["controls"]["FrameDurationLimits": framedurationlim]

		time.sleep(0.2) # Sync Delay

	# 5
	def capture(self, action, filename, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0, **kwargs):
		# Iterations	

		action = action.lower().strip()
		if action == "preview":
			self.modes[action](tsec=tsec, **kwargs)
		else:
			self.modes[action](filename, tsec=tsec, **kwargs)

	# 6
	def preview(self, tsec=30, preview=Preview.QT):
		# Doesnt work
		self.cam.configure(self.cam.create_preview_configuration())

		self.cam.title_fields = ["ExposureTime", "FrameDuration"]
		self.cam.start_preview(Preview.QT)
		time.sleep(tsec)
		self.cam.stop_preview()

	# 7 TODo Rethink
	def state(self):
		state_ = {}
		state_.update(self.config)
		state_.update(self.cam.camera_properties)
		return state_

	# 8 #TODO
	def help(self):
		"""
		Prints docstrings for all capture modes.
		"""

		helpdict = {}
		for mode in self.modes:
			print(self.modes[mode])
			helpdict[mode] = self.modes[mode].__doc__.strip("\n")
		print("PiCamera2 Capture Modes:")
		pprint(helpdict)


	# 9
	def __repr__(self):
		time_now = time.perf_counter()
		return f"<PiCamera2 - op for{(time_now - self.opentime_ns):.3f}s>"

	# --- Implementation Specific functions ---

	# 10
	def optimize(self):
		self.config = self.cam.align_configuration(self.config)
		log.info(f"Camera config: {self.config}")

	# 11 - Not implemented by PiCamera2 for RPi HQ Camera
	#def autofocus(self):
		"""
		Trigger Autofocus cycle. Returns the success status.
		"""
	#	return self.cam.autofocus_cycle()

	# 12
	def timestamp(self, mode, *args, **kwargs):
		pass

	def frame_metadata(self):
		"""
		Returns the Metadata from the last frame.
		"""
		md = self.cam.capture_metadata()
		return md

	def lux_state(self):
		"""
		Returns the Lux state ("Avg Lux and ColorTemp of the last frame.")
		"""
		md = self.frame_metadata()
		return {"lux": md["Lux"], "color_temp": md["ColorGains"]}


	
	### Capture mode implementations

	# OK
	def __image__(self, filename, *args, **kwargs):
		"""
		Capture a png image.
		tsec is ignored.
		"""
		self.cam.configure(self.cam.create_still_configuration())
		self.cam.start_and_capture_file(filename)
		self.cam.stop_preview()

	# 
	def __image_trig__(self, filename, *args, **kwargs):
		"""
		Capture PNG image when the `Enter` key is pressed.
		"""

		# Maybe set trigger prompt in the title bar of the window.
		self.cam.title_fields = ["ExposureTime", "FrameDuration"]
		self.cam.configure(self.cam.create_still_configuration())
		
		self.cam.start_preview(Preview.QTGL)
		
		_ = input("Waiting for image trigger: Enter key...")
		self.cam.capture_file(filename, format='png')
		print("Capture completed.")

		self.cam.stop_preview()

	# 
	def __timelapse__(self, filename, *args, **kwargs):
		"""
		Captures a timelapse sequence in jpeg format.
		filenames: is preceeded by the capture sequence number.
		frames: number of frames that must be captured.
		delay_s (optional) : Delay between images in seconds.
		"""
		filenames = args[0]

		if not all(["frames", "delay_s"]) in kwargs:
			raise KeyError("Either arguments missing: frames and/or delay_s")


		filenames_ = "{:03d}" + filenames
		self.cam.start_and_capture_files( \
			name=filenames_, init_delay=0, \
			num_files = frames, delay = delay_s, \
			show_preview = True)

	# OK
	def __video__(self, filename, *args, **kwargs):
		"""
		Record an h264 video.
		RPi Hardware supports processing upto 1080p30.
		"""

		#self.cam.configure(self.cam.create_video_configuration())
		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()
		#filename.close()
		#time.sleep(tsec)
		#self.cam.stop_recording()

		# quality=Quality.HIGH

	# OK
	def __video_noprev__(self, filename, *args, **kwargs):
		"""
		Record a video without preview in h264 format.
		Recommended for high fps recordings.
		"""

		#self.cam.configure(self.cam.create_video_configuration())
		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=False, \
								 duration=tsec)
		#time.sleep(tsec)
		#self.cam.stop_recording()

		#quality=Quality.HIGH, 

	# Ok
	def __videomp4__(self, filename, *args, **kwargs):
		"""
		Record an MP4 file using Ffmpeg.
		Timestamps are not passed to Ffmpeg. Hence they are estimated.
		"""

		self.cam.configure(self.cam.create_video_configuration())
		tsec = kwargs["tsec"]
		output = FfmpegOutput(filename) # Opens a new file object
		
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()

	# 
	def __video_raw__(self, filename, *args, **kwargs):
		"""
		Captures in raw binary unncoded format. NOT IMPLEMENTED.
		"""
		self.cam.configure(self.cam.create_video_configuration())
		tsec = kwargs["tsec"]

	# 
	def __ndarray__(self, filename, *args, **kwargs):
		"""
		Capture to ndarray object. NOT IMPLEMENTED
		If filename is passed. The ndarray is packed to a .npy binary file.
		tsec: Capture time in seconds. Number of frames captured is tsec*framerrate.
		Shape of the captured array: frame X Width(px) X Height(px).
		"""

		# Need to set RGB888 format first
		
		# Check validity of the resolution
		tsec = kwargs["tsec"]
		fps = 30
		valid_res = [mode["size"] for mode in self.cam.sensor_modes]
		print(valid_res)
		res = [2028, 1080]
		#if self.config["size"] not in any(valid_res):
		#
		#	log.error("Invalid resolution for raw capture. Capture cancelled.")
		#	log.debug(f"Use the following resolutions instead: {valid_res}")
		#	return

		# Pre-allocate array
		array_shape = [int(tsec*fps), int(res[0]), int(res[1]), 4]
		self.array = np.ndarray(*array_shape)
		print(self.array.shape)

		self.cam.capture_arrays("main")

	# 
	def __stream__(self, stream):
		"""
		Capture to a stream like object. NOT IMPLEMENTED.
		"""
		pass

		
