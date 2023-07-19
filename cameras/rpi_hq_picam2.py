from abcs.camera import AbstractCamera


from pprint import pprint
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
	def configure(self, fps=30, res=[1920, 1080],  config=None):
		"""
		Configure the base settings of the camera.
		The rest are set based on the capture mode.
		"""

		# Ignoring config_file option for now.

		self.cam.set_controls({
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

			})

		time.sleep(0.2) # Sync Delay

	# 5
	def capture(self, action, filename, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=0, **kwargs):
		action = action.lower().strip()
		if action == "preview":
			self.modes[action](tsec=tsec, **kwargs)
		else:
			self.modes[action](filename, tsec=tsec, **kwargs)

	# 6
	def preview(self, tsec=30, preview=Preview.QT):

		self.cam.configure(self.cam.create_preview_configuration())

		self.cam.title_fields = ["ExposureTime", "FrameDuration"]
		self.cam.start_preview(Preview.QT)
		time.sleep(tsec)
		self.cam.stop_preview()

	# 7
	def state(self):
		return self.cam.camera_properties

	# 8
	def help(self):
		"""
		Prints docstrings for all capture modes.
		"""

		helpdict = {}
		for mode in self.modes:
			helpdict[mode] = self.mode[mode].__doc__.strip("\n")
		print("PiCamera2 Capture Modes:")
		pprint(helpdict)


	# 9
	def __repr__(self):
		time_now = time.perf_counter()
		return f"<PiCamera2 - {time_now - self.opentime_ns:3d}s>" + \
			   pprint.format(self.status())

	# --- Implementation Specific functions ---

	# 10
	def optimize(self):
		self.config = self.cam.align_configuration(self.config)
		log.info(f"Camera config: {self.config}")

	# 11
	def autofocus(self):
		"""
		Trigger Autofocus cycle. Returns the success status.
		"""
		return self.cam.autofocus_cycle()

	# 12
	def timestamp(self, mode, *args, **kwargs):
		pass

	def frame_metadata(self):
		"""
		Returns the Metadata from the last frame.
		"""
		md = self.frame_metadata()
		return md

	def lux_state(self):
		"""
		Returns the Lux state ("Avg Lux and ColorTemp of the last frame.")
		"""
		md = self.frame_metadata()
		return {"lux": md["Lux"], "color_temp": md["ColorGains"]}


	
	### Capture mode implementations

	# 
	def __image__(self, filename, *args, **kwargs):
		"""
		Capture a png image.
		tsec is ignored.
		"""
		self.cam.configure(self.cam.create_still_configuration())
		self.cam.start_and_capture_file(filename)

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

	# 
	def __videomp4__(self, filename, *args, **kwargs):
		"""
		Record an MP4 file using Ffmpeg.
		Timestamps are not passed to Ffmpeg. Hence they are estimated.
		"""

		self.cam.configure(self.cam.create_video_configuration())
		tsec = kwargs["tsec"]
		output = FfmpegOutput(filename) # Opens a new file object
		
		self.cam.start_and_record_video(output, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()

	# 
	def __video_raw__(self, filename, *args, **kwargs):
		"""
		Captures in raw binary unncoded format. NOT IMPLEMENTED.
		"""
		pass

	# 
	def __ndarray__(self, filename, *args, **kwargs):
		"""
		Capture to ndarray object. NOT IMPLEMENTED
		If filename is passed. The ndarray is packed to a .npy binary file.
		tsec: Capture time in seconds. Number of frames captured is tsec*framerrate.
		Shape of the captured array: frame X Width(px) X Height(px).
		"""
		
		# Check validity of the resolution
		valid_res = [mode["size"] for mode in self.cam.sensor_modes]
		if self.config["size"] not in any(valid_res):

			log.error("Invalid resolution for raw capture. Capture cancelled.")
			log.debug(f"Use the following resolutions instead: {valid_res}")
			return

		# Pre-allocate array
		array_shape = [int(tsec*fps), int(res[0]), int(res[1]), 3]
		self.array = np.ndarray(*array_shape)
		print(self.array.shape)

	# 
	def __stream__(self, stream):
		"""
		Capture to a stream like object. NOT IMPLEMENTED.
		"""
		pass

		
