#!/usr/bin/python
# -*- coding: <encoding name> -*-

import logging
import pprint

import os
import yaml
from yaml.loader import SafeLoader

# Hardware
from cameras.selector import CameraSelector
from lights.selector import LightSelector
from picodevice import RPiPicoDevice
from picolight import PicoLight

# Other Resources
from experiment import Experiment
from utilities import fluff

import sys
sys.path.append(["./cameras/", "./lights/", "./abcs/"])



## 1. Setlogging and device state
og_directory = os.getcwd()
log = logging.Logger("main")
log.setLevel(0)
print("-"*100)


## 2. Load device ID an metadata
with open("config/deviceid.yaml") as deviceid:
	device_metadata = yaml.load(deviceid, Loader=SafeLoader)
print("\nDevice: ")
print("-------")
log.critical(pprint.pformat(device_metadata))


##3. Print Header
print(fluff.header())


## 4. Set Experiment
print("All current experiments on the Microscope:")
print(Experiment.list_all())
print("\n\n")
print("Press Ctrl+Z to exit.")
exp_name = input("Input the session/experiment name -> ")
exp_name.strip()

exp = None
if exp_name:
	exp = Experiment(exp_name)


## 5. Set hardware resources
pico = RPiPicoDevice(name=device_metadata["hardware"]["pico"][0], \
					 port='/dev/cu.usbmodem10')
if not pico.connected:
	log.error("Could not get a pico device - exiting.")
	exit(1)
pico.exec_main()
log.info(pico)

#lit = LightSelector(device_metadata["hardware"]["illumination"])
lit = PicoLight(pico, "l1")
log.info(lit)

cam = CameraSelector(device_metadata["hardware"]["camera"])
if not cam.connected:
	log.error("Could not get a camera device – exiting.")
	exit(1)
cam.configure()
log.info(cam)

unique_check = False
def capture(name, *args, **kwargs):
	"""
	Default capture 
	"""

	if mode == None:
		mode = "video"
	
	# File  uniqueness check
	if unique_check:
		if name in os.listdir():
			print("File already exists – ignoring the call.")
			return
	
	# Capture call
	cam.capture(name,  *args, **kwargs)

	# Reprint Experiment Header
	if exp_name:
		exp.log()
		print(exp.header(), end="")



def close_exp():
	"""
	Close experiment and reset the current directory to the original.
	"""
	exp_name = None
	sys.ps1 = '>>> '
	os.chdir(og_directory)
	print("---\n\n")









