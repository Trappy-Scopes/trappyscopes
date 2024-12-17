#from abcs.camera import AbstractCamera
from subprocess import Popen, PIPE
from rich import print
import sys
import os
from detectors.cameras.abstractcamera import Camera as AbstractCamera

class Camera(AbstractCamera):
	def __init__(self):
		super().__init__()
		self.process = None
		self.status  = "standby"
		self.actions = {"preview": self.__preview__, 
					    "vid": self.__video__, 
					    "img": self.__image__,
					    "vid_mjpeg_prev": self.__vid_mjpeg_prev__,
					    "vid_mjpeg": self.__vid_mjpeg__,
					    "vid_mjpeg_tpts": self.__vid_mjpeg_tpts__,
					    "prev_formatted": self.__preview_formatted__}
		self.config={"kind":"camera-libcamera"}

	def __process__(self, cmd):
		self.process = Popen(cmd, stdout=sys.stdout, stderr=sys.stderr, shell=True,\
					    universal_newlines=True)
		
		pid = self.process.pid
		stdout, stderr = self.process.communicate()
		return self.process.returncode, stdout, stderr, pid

	def preview(self, tsec=10):
		return self.__preview__(tsec=tsec)


	def __preview__(self, tsec=10):
		cmd_list = f"libcamera-vid -t {tsec*1000} -f"
		return self.__process__(cmd_list)

	def __preview_formatted__(self, filename, *args, **kwargs):
		"""
		Note that the filename arguement is ignored.
		"""
		tsec = kwargs["tsec"]
		print(kwargs)
		self.config["res"] = (2028, 2028)
		self.config["fps"] = 20
		self.config["exposure_ms"] = kwargs["exposure_ms"]
		cmd_list = f"libcamera-vid -t {tsec*1000} -f --codec mjpeg --width 2028 --height 2028 --denoise off --awbgains 0,0 --analoggain 1 --framerate {kwargs['fps']} --shutter {kwargs['exposure_ms']*1000} --contrast 2 --sharpness 1 -q {kwargs['quality']}"
		return self.__process__(cmd_list)

	def __image__(self, filename, *args, **kwargs):
		print("Capturing in 5 seconds!")
		cmd_list = f"libcamera-still -t {5*1000} -f -o {filename}"
		return self.__process__(cmd_list)

	def __video__(self, filename, *args, **kwargs):
		
		tsec = kwargs["tsec"]

		cmd_list = f"libcamera-vid -t {tsec*1000} -f -o {filename}"
		return self.__process__(cmd_list)

	def __vid_mjpeg_prev__(self, filename, *args, **kwargs):
		tsec = kwargs["tsec"]
		print(kwargs)
		self.config["res"] = (2028, 2028)
		self.config["fps"] = 20
		self.config["exposure_ms"] = kwargs["exposure_ms"]
		cmd_list = f"libcamera-vid -t {tsec*1000} -f -o {filename} --codec mjpeg --width 2028 --height 2028 --denoise off --awbgains 0,0 --analoggain 1 --framerate {kwargs['fps']} --shutter {kwargs['exposure_ms']*1000} -q {kwargs['quality']}"
		return self.__process__(cmd_list)

	def __vid_mjpeg__(self, filename, *args, **kwargs):
		tsec = kwargs["tsec"]
		print(kwargs)
		self.config["res"] = (2028, 2028)
		self.config["fps"] = 20
		self.config["exposure_ms"] = kwargs["exposure_ms"]
		cmd_list = f"libcamera-vid -t {tsec*1000} -o {filename} --nopreview --codec mjpeg --width 2028 --height 2028 --denoise off --awbgains 0,0 --analoggain 1 --framerate {kwargs['fps']} --shutter {kwargs['exposure_ms']*1000} -q {kwargs['quality']}"
		return self.__process__(cmd_list)

	def __vid_mjpeg_tpts__(self, filename, *args, **kwargs):
		tsec = kwargs["tsec"]
		ptsfname = filename.replace(".mjpeg", ".tpts")
		print(kwargs)
		self.config["res"] = (2028, 2028)
		self.config["fps"] = 20
		self.config["exposure_ms"] = kwargs["exposure_ms"]
		cmd_list = f"libcamera-vid -t {tsec*1000} -o {filename} --nopreview --codec mjpeg --width 2028 --height 2028 --denoise off --awbgains 0,0 --analoggain 1 --framerate {kwargs['fps']} --shutter {kwargs['exposure_ms']*1000} -q {kwargs['quality']} --save-pts {ptsfname} --contrast 2 --sharpness 1"
		return self.__process__(cmd_list)








		