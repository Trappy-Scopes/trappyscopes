from abcs.camera import AbstractCamera

from pprint import pprint, pformat
from copy import deepcopy
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

	default_controls = {
			#"ExposureTime": 1000,
			
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


	# 1
	def __init__(self):
		
		self.cam = Picamera2()
		self.opentime_ns = time.perf_counter()
		log.info("PiCamera2 Camera was opened.") # Constructor opens the cam.


		# Preview Window Settings
		self.preview_type = Preview.QT
		self.win_title_fields = []
		self.cam.title_fields = ["ExposureTime", "FrameDuration"]



		# Capture Modes for this implementation
		self.modes = {
					  "preview"      : self.preview,
					  "img"          : self.__image__,
					  "img_trig"     : self.__image_trig__,
					  "timelapse"	 : self.__timelapse__,
					  "vid"	         : self.__video__,
					  "vidmp4"       : self.__videomp4__,
					  "vid_noprev"   : self.__video_noprev__,
					  "vid_raw"      : self.__video_raw__,
					  "ndarray"		 : self.__ndarray__,
					  "stream"		 : self.__stream__
					 }


		# Video Encoders and image quality parameters
		self.encoderh264 = H264Encoder()
		self.cam.options["quality"] = 95
		self.cam.options["compress_level"] = 0


		# Specific config and controls that deviate from the PiCamera defaults.
		self.config = {}
		self.controls = Camera.default_controls

		# Configurations
		self.config_map = {}
		self.config_map["preview"] = self.cam.create_preview_configuration()
		self.config_map["still"] = self.cam.create_still_configuration()
		self.config_map["video"] = self.cam.create_video_configuration()

		#self.config_map["still"]["lores"] = {}
		#self.config_map["still"]["display"] = "lores" # Turn on preview
		
		self.config_map["preview"]["controls"] = self.controls
		self.config_map["still"]["controls"] = self.controls
		self.config_map["video"]["controls"] = self.controls

		# Configuration Setting Functions
		self.config_default =  lambda : self.configure(res=(1980, 1080), fps=30)
		self.config_default2 = lambda : self.configure(res=(2028, 1080), fps=30)
		self.config_largeres = lambda : self.configure(res=(4056, 3040), fps=10)
		self.config_largefps = lambda : self.configure(res=(1332, 990), fps=120)

		# Set initial conditions
		self.mode_ = "video" 	# Current Mode - ["preview", "still", "video"]
		#self.config_default() 	# Configure default resoltion and fps
		self.cam.configure(self.config_map["video"])
		time.sleep(0.2)

	# 2
	def open(self):
		self.close()
		self.cam.start()
		#self.encoderh264 = H264Encoder()
		self.opentime_ns = time.perf_counter()
		log.info("PiCamera2 Camera was opened.")

	# 3
	def is_open(self):
		return self.cam.is_open

	# 3
	def close(self):
		self.cam.close()
		#self.encoderh264.close()
		log.info("PiCamera2 Camera was closed.")

	# 4
	def configure(self, fps=None, res=None, config=None):
		"""
		Configure the base settings of the camera. Both the [stream] configurations and controls.
		The rest are set based on the capture mode.
		Ignoring config_file option for now.
		"""

		# CONTROLS
		self.cam.set_controls(self.controls)


		# CONFIGURATIONS
		if res != None and fps != None:
			print(f"Setting fps:{fps} and resolution:{res}")
			frameduration = int((1/fps)*1**6)
			framedurationlim = (frameduration, frameduration)

			for mode_ in self.config_map:
				self.config_map[mode_]["size"] = tuple(res)
				self.config_map[mode_]["controls"]["FrameDurationLimits"] = \
															 framedurationlim
		time.sleep(0.2) # Sync Delay

	# 5
	def capture(self, action, filename, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0, **kwargs):
		"""
		init_delay does not include camara mode changes applied at 
		the beginning which might be of the order of 100s of ms.
		"""	

		action = action.lower().strip()
		if iterations == 1:
			if action == "preview":
				self.modes[action](tsec=tsec, **kwargs)
			else:
				self.modes[action](filename, tsec=tsec, **kwargs)
		else:
			if action == "preview":
				self.modes[action](tsec=tsec, **kwargs)
			else:
				filename_stubs = filename.split(".")
				filenames_ = [f"{filename_stubs[0]}_{i}.{filename_stubs[1]}" \
				for i in range(iterations)]
				print(filenames_)
				time.sleep(init_delay_s)
				for i in range(iterations):
					filename_ = filenames_[i]
					print(f"{i}: {time.time.ns()}. Capturing file: {filename_} :")
					self.modes[action](filename_, tsec=tsec, **kwargs)
					print(f"{i}:  {time.time.ns()}. Sleeping for {itr_delay_s}s.")
					time.sleep(itr_delay_s)

	# 6
	def preview(self, tsec=30, preview=Preview.QT):
		"""
		Start a preview. Defaults for 30seconds. 
		Infinite preview or pre-emptive termination is not supported. 
		"""
		self.set_mode_config("preview")

		self.cam.start_preview(self.preview_type)
		time.sleep(tsec)
		self.cam.stop_preview()

	# 7 TODo Rethink
	def state(self):
		"""
		Returns a dictionary of the parameter settings of the camera.
		"""
		state_ = {}
		state_["config"] = self.config
		state_["controls"] = self.controls
		state_.update(self.cam.camera_properties)
		return state_

	# 8
	def help(self):
		"""
		Prints docstrings for all capture modes.
		"""
		helpdict = {}
		for mode in self.modes:
			print(self.modes[mode])
			helpdict[mode] = self.modes[mode].__doc__.strip("\n").strip("\t")
		print("PiCamera2 Capture Modes:")
		for z in zip(self.modes.keys(), helpdict):
			pprint(z)


	# 9
	def __repr__(self):
		time_now = time.perf_counter()
		return f"<PiCamera2 - op for {(time_now - self.opentime_ns):.2f}s>"

	# --- Implementation Specific functions ---

	# 10
	def optimize(self):
		# TODO Redo for all three configurations
		self.config = self.cam.align_configuration(self.config)
		log.info(f"Camera config optimized to: {self.config}")
		self.cam.configure(self.config)

	# 12
	def timestamp(self, mode, *args, **kwargs):
		tsec = kwargs["tsec"]
		for i in range(tsec*self.get_fps()):
			f_md = self.frame_metadata()
			print(f"{i}. {self.time.time_ns()}")


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


	def set_mode_config(self, mode):
		"""
		Sets the camera configuration for the three main modes: ["preview",
		"still", "video"].
		"""
		if self.mode_ != mode:
			self.mode_ = mode
			self.cam.configure(self.config_map[mode])
			self.close()	   # Close Camera
			time.sleep(0.5)
			self.open()		  # Open Camera
			time.sleep(0.2)


	def autoadjust(self, wb=True, exposure=True):
		"""
		Autoadjust "ExposureTime", "AnalogueGain", and "ColourGains".
		wb [optonal] : Adjusts the white balance (Red - Blue Ratio).
		exposure [optional] : Adjusts the exposure time of the camera.
		"""
		control_struct = {}
		if wb:
			control_struct.update({"AwbEnable": 1})
		if exposure:
			control_struct.update({"AeEnable": 1})

		self.cam.start_preview(self.preview_type)

		self.cam.stop()
		self.cam.configure(self.cam.create_video_configuration()) #Instead of this only upodate specific fields
		self.cam.start()

		time.sleep(1) # Wait for autoadjustments

		self.cam.set_controls({"AwbEnable": 0, "AeEnable": 0})
		time.sleep(5) # For checking the results.
		
		
		self.cam.stop_preview()
		self.cam.title_fields = self.win_title_fields

		# Push the updates to the controls structure and update the camera.
		ExposureTime = self.cam.video_configuration.ExposureTime
		ColorGains =  self.cam.video_configuration.ColorGains
		
		print(f"Autoadjusted -> ExposureTime: {ExposureTime} and ColorGains: {ColorGains}")
		print("Pushing the values to Camera Controls.")
		
		self.controls["ExposureTime"] = ExposureTime
		self.controls["ColorGains"] = ColorGains
		for mode in self.config_map:
			self.config_map[mode]["controls"] = self.controls
		self.configure()
		self.set_mode_config(self.mode_)

	def get_fps(self):
		"""
		Uses the Video Configuration as the default configuraation.
		"""
		return self.cam.video_configuration.controls.FrameRate

	def get_res(self):
		"""
		Uses the Video Configuration as the default configuraation.
		"""
		return self.cam.video_configuration.size

	
	### Capture mode implementations

	# OK
	def __image__(self, filename, *args, **kwargs):
		"""
		Capture a png image.
		tsec is ignored.
		"""
		self.set_mode_config("still")
		self.cam.start_and_capture_file(filename)
		self.cam.stop_preview()

	# NOK
	def __image_trig__(self, filename, *args, **kwargs):
		"""
		Capture PNG image when the `Enter` key is pressed.
		"""
		self.set_mode_config("still")
		
		self.cam.start_preview(Preview.QT)
		_ = input("Waiting for image trigger: Enter key...")
		self.cam.capture_file(filename, format='png')
		print("Capture completed.")

		self.cam.stop_preview()

	# NOk
	def __timelapse__(self, filename, *args, **kwargs):
		"""
		Captures a timelapse sequence in jpeg format.
		filenames: is preceeded by the capture sequence number.
		frames: number of frames that must be captured.
		delay_s (optional) : Delay between images in seconds.
		"""
		if not all(["frames", "delay_s"]) in kwargs:
			raise KeyError("Either arguments missing: frames and/or delay_s")

		self.set_mode_config("still")

		filenames_ = "{:03d}" + filename
		self.cam.start_and_capture_files( \
			name=filenames_, init_delay=0, \
			num_files = kwargs["frames"], delay = kwargs["delay_s"], \
			show_preview = True)
		self.cam.stop_preview()

	
	# OK
	def __video__(self, filename, *args, **kwargs):
		"""
		Record an h264 video.
		RPi Hardware supports processing upto 1080p30.
		"""

		#self.cam.configure(self.cam.create_video_configuration())
		self.set_mode_config("video")

		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()
		# quality=Quality.HIGH

	# OK
	def __video_noprev__(self, filename, *args, **kwargs):
		"""
		Record a video without preview in h264 format.
		Recommended for high fps recordings.
		"""
		self.set_mode_config("video")

		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=False, \
								 duration=tsec)
		#quality=Quality.HIGH, 

	# Ok
	def __videomp4__(self, filename, *args, **kwargs):
		"""
		Record an MP4 file using Ffmpeg.
		Timestamps are not passed to Ffmpeg. Hence they are estimated.
		"""
		self.set_mode_config("video")

		tsec = kwargs["tsec"]
		output = FfmpegOutput(filename) # Opens a new encoder file object
		
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()

	# 
	def __video_raw__(self, filename, *args, **kwargs):
		"""
		Captures in raw binary unncoded format. NOT IMPLEMENTED.
		"""
		self.set_mode_config("video") #Probably not necessary
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

		
