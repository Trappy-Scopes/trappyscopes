

from validation import *
from mcu_controls import MCUControls

import yaml
"""
Prototype 1
-----------

+ Basic info output
+ capture - video & audio
+ preview
+ metadata input
+ datastorage

Prototype 2
----------
+ get_frames
+ multicapture
"""


class MicroscopeAssembly:

	def __init__(name, cam=None, lit=None, pico=None, exp=exp):
		self.pico = pico
		self.cam = cam
		self.lit = lit

		self.unique_check = True   # Only asserted during experiment mode.
		self.exp = exp

		self.node = Node()

	def init(self, deviceid):
		picomode = "null" * (deviceid["hardware"]["pico"][0] == "nullpico") + \
		           "normal" * (deviceid["hardware"]["pico"][0] == "pico")

		pico = RPiPicoDevice.Select(picomode, name=device_metadata["hardware"]["pico"][1], \
							 port=None)
		print(pico)
		if not pico.connected:
			log.error("Could not get a pico device - exiting.")
			exit(1)
		pico.exec_main()
		log.info(pico)

		#lit = LightSelector(device_metadata["hardware"]["illumination"])
		lit = PicoLight(pico, "l1")
		log.info(lit)

		cam = CameraSelector(deviceid["hardware"]["camera"])
		#cam.open() # Camera should be already open upon creation.
		print(cam)
		if not cam.is_open():
			log.error("Could not get a camera device - exiting.")
			exit(1)
		#cam.configure()
		log.info(cam)


		
	def capture(self, action, name, *args, **kwargs):
		"""
		Default capture 
		"""
		print(f"cwd: {os.getcwd()}")
		if action == None:
			action = "video"
		
		# File  uniqueness check
		if unique_check and exp.active:
			if not exp.unique(name):
				print(f"{Fore.RED}File already exists - ignoring the call.{Fore.RESET}")
				return
			
			# Capture call
			cam.capture(action, name,  *args, **kwargs)

			# Reprint Experiment Header
			if exp or exp.active():
				exp.log_event(name)


class Microscope:

	"""
	Class that describes the `Microscope`  object.
	"""

	def status():
		"""
		Returns an introduction to the objectct.
		"""

		intro = \
		f"""
		Microscope

		-----------       {self.name}
            |||           {self.server, self.port}
		xxxxxxxxxxx       status = {self.cam_open}
		|   xxx   |
		xxxxxxxxxxx
		     V
		"""
		return intro

	def __repr__():
		return f" >|#|==+···| Microscope -> {self.name}."


	def info():
		"""
		Returns a string of information about the current state of the camera.
		"""
		info_str = \
		f"""
		Camera
		------

		Exposure speed: {self.camera.exposure_speed}
		"""


	def __init__(self, pins, config=None):
		self.name = None
		self.id = None
		self.port = None
		self.address = None

		self.session_id = None
		self.cam_open = False


		self.camera = None         # Camera object
		self.lights = None         # Lights / Illumination
		self.mcu = None            # Microcontroller Unit (MCU)
		self.pump = None           # Syrenge Pump
		self.mcu_firmware = None   # MCU Control Firmware
		self.gpio = None           # Raspberry Pi GPIO
		self.optics = None         # Hold infomration about the optical components
		self.chambers = None       # Represents the chamber(s) in the microscope


		# State Information
		self.run_state = Metadata()                       # Metadata object
		self.cam_config = yaml.load(".camconfig.yaml")  # Camera configuration
		self.state = yaml.load(".scopeconfig.yaml")       # Misc state information


		self.default_vid_ext = self.state["default_vid_ext"]
		self.default_img_ext = self.state["default_img_ext"]


		# Set Microscope Settings
		self.lights.set(self.state["color"], self.state["lux"])

		# Data
		self.frames = None
		self.sensor_data = None


	
		# Action Structure — A dictionary of 
		self.actions = { "image": self.__image__,
				    	 "video": self.__video__,
				         "preview": self.preview
				       }

	def init_cam(self):
		"""
		Initalize the camera and get it ready for capture.
		Includes a 2 second sleep for the camera to stabilize.
		"""
		self.camera.close() # For safet
		self.cam_open = True
		self.camera = picamera.Camera()
		# Stabilization delay (maye redundant for fixed A/D gains.)
		time.sleep(2)


	def deinit_cam():
		"""
		Deinitalize Camera
		"""
		self.camera.close()
		self.cam_open = False


	def set_camera(self, param=None):
		"""
		This function sets the camera settings for imaging.
		"""
		# Fix parameters for calibration
		# Preview for 10 minutes
		# AWB = Automatic White balance
		# drc 0 Dynamic Range Control
		# Annotation Settings: 16 - Shutter settings, 32 - CAF (Continuous Auto Focus), 64, Gain setting
		# Maximum Exposure time/ Shutter Speed: 33333,333333333332871
		# ev is exposure value: Range is 10 to 10; default being 0.

		# Experiment: Add --vstab flag for vertical stabilization
		
		# raspivid --annotate 112 --stats --verbose -f -t 600000 -fps 30 -h 1080 -w 
		# 1920 -awb off --brightness 50 --ev 0 --contrast 0 -drc off --exposure off 
		# -ISO 500 --saturation 0 --sharpness 0 --shutter 20000

		camera.framerate = 30
		camera.resolution(1920, 1080)
		
		camera.brightness(50)
		camera.color_effects(None)
		camera.contrast(0)

		camera.awb_mode("off")
		camera.awb_gains(1.9)

		camera.drc_strength("off")
		camera.flash_mode('off')


		camera.iso(200)
		camera.exposure_mode("off")

		# Set gain values


	def capture(action="image", tsec=3, iterations=1, delay_s=0, init_delay_s=0):
		"""
		Capture video or image using the microscope.
		"""

		# 1. Session Formation
		self.session_id = uuid.uuid4()
		self.session_time = time.time()
		

		#1.1 Generate meta-data object
		self.session_md = Metadata("session")
		self.session_md.add_que('Mode of operation (action) -> either \"image\" or \"video\" ?', label="action")
		self.session_md.add_que("Number of iterations?", label="iterations")
		self.session_md.add_que("Time delay between captures?", label="delay")
		self.session_md.collect()

		# 1.2 Append Other meta-data structures
		self.session_md = self.session_md + self.camera_config
		self.session_md = self.session_md + self.device_state


		# 1.3 Generate File Descriptor (Node)
		self.datastore.new_node(self.session_md.fd(include=[]))
		fd = metadata.file_descriptor()
		self.datastore.new_session(fd)
		

		if mode == "video":
			self.__video__()

			self.metadata.metadata_file(self.datastore.session_path())

		elif mode == "image":
			img_name = fd + ".jpeg"
			self.camera.capture(img_name)

		else:
			print("Invalid capture mode!")



	def calibrate_camera():
		"""
		Slowly increase light and measure camera counts.
		"""
		return
		# Fix resolution and framerate
		cmap = {'r':0, 'g':1, 'b':2}
		COLOR_CALIBRATION_RESOLUTION = 0.05
		color_calib_curve = {}
		color_calib_curve_std = {}
		total_pixels = camera.resolution[0]*camera.resolution[1]
		
		for color in ['r', 'g', 'b']:	
			self.lights.set_color(color)
			color_calib_curve[color] = {}
			color_calib_curve_std[color] = {}
			time.sleep(2)
			if self.mcu.completed(timeout_sec=2): #How would this work?
				for lux in range(0.0, 1.0, COLOR_CALIB_RESOLUTION):
					
					self.lights.set_lux(lux)
					if self.mcu.completed(timeout_sec=2):
						time.sleep(2) # Sleep fot 2 seconds
						
						frames = self.get_frames()
						# frames[frame_no][row][column][color]
						r_ch = []
						g_ch = []
						b_ch = []
						for f in frames.shape[0]:
							# TODO summation needs to happen over entire array: here axis is not specified. Fix
							r_ch.append(np.sum(frames[f, :, :, 0], dtype=np.float64)/total_pixels)
							g_ch.append(np.sum(frames[f, :, :, 1], dtype=np.float64)/total_pixels)
							b_ch.append(np.sum(frames[f, :, :, 2], dtype=np.float64)/total_pixels)

						# Sum over all channels
						color_calib_curve[color][lux] = [np.mean(r_ch), np.mean(g_ch), np.mean(b_ch)]
						color_calib_curve_std[color][lux] = [np.std(r_ch), np.std(g_ch), np.std(b_ch)]

		print(color_calib_curve)
		print(color_calib_curve_std)


	def align():
		"""
		Start an alignment sequence.
		"""
		pass


	def preview(self, tsec=30):
		"""
		Starts a preview window for the camera.
		"""
		if self.status == "on":
			self.camera.annotate_text("Preview")
			self.camera.start_preview()
			sleep(tsec)
			self.camera.stop_preview()
		else:
			print("Camera not open for operation!")

	def toggle_flash_mode():
		return
		camera.flash_mode('off')
		camera.flash_mode('auto')
		camera.flash_mode('on')
		camera.flash_mode('redeye')
		camera.flash_mode('fillin')
		camera.flash_mode('torch')


	def get_frames(no_frames=100):
		"""
		Returns some fixed number of frames as a `numpy ndarray` in RGB format. 
		"""
		print("Capturning {no_frames} frames!")
		output = np.empty((*self.camera.resolution, no_frames), dtype=np.uint16)

    	i = 0
    	start_time = time.perf_counter()
    	for _ in camera.capture_continuous():
    		camera.capture(output[i], 'rgb')
    		i = i + 1
    		if i >= 100:
    			break
    	end_time = time.perf_counter()
    	return output



    def multicapture(tsec=30, resolutions=[]):
    	"""
		
		Only captures the first 3 resolution values, it ignores the rest.


		From picamera docs:
		------------------
		There are 4 splitter ports in total that can be used 
		(numbered 0, 1, 2, and 3). The video recording methods
		default to using splitter port 1, while the image capture
		methods default to splitter port 0 (when the use_video_port
		parameter is also True).
    	"""
    	if resolutions > 0:

	    	dt = datetime.datetime.now()
	    	node = self.datastore.new_node(f"multicapture-{str(dt)}")
	    	
	    	captures = {}
	    	for res in resolutions[:3]:
	    		if is_valid_res_type(res):
	    			captures.extend(res, self.datastore.new(f"{res[0]}X{res[1]}"), node=node)


	    	camera.resolution = (*resolutions[0])
	    	camera.start_recording(f'{captures[resolutions[0]]}.{self.default_video_ext}')
	    	for port in range(2,3)
	    		camera.start_recording(captures[port-1], splitter_port=port, resize=*resolutions[port-1])
	    		

	    	camera.wait_recording(tsec)
	    	camera.stop_recording()
	    	for port in range(2,3)
	    		camera.stop_recording(splitter_port=port)
	    	

	    def __image__(preview=False):
	    	

	    def __video__(preview=True):
	    	# With preview

	    	#video_name = self.datastore.new() + ".h264"
	    	video_name = f"{time.time_ns()}" + self.default_vid_ext
	    	self.camera.start_recording(video_name, format="h264")          
	    	self.camera.wait_recording(tsec)
	    	self.camera.stop_recording()





if __name__ == "__main__":
	m1 = Microscope(lights="pwm")