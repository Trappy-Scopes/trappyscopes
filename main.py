#!/usr/bin/python
# -*- coding: <encoding name> -*-

import logging
import pprint
import os
import sys
sys.path.append(os.path.abspath("./abcs"))
import abcs


import yaml
from yaml.loader import SafeLoader
from colorama import Fore

# Hardware
from cameras.selector import CameraSelector
from lights.selector import LightSelector
from picodevice import RPiPicoDevice
from picolight import PicoLight

# Other Resources
from experiment import Experiment
from utilities.fluff import pageheader, intro


#sys.path.append(["./cameras/", "./lights/", "./abcs/"])



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
print(pageheader())



## 4. Set hardware resources

picomode = "null" * (device_metadata["hardware"]["pico"][0] == "nullpico") + \
           "normal" * (device_metadata["hardware"]["pico"][0] == "pico")

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

cam = CameraSelector(device_metadata["hardware"]["camera"])
#cam.open() # Camera should be already open upon creation.
if not cam.is_open():
	log.error("Could not get a camera device - exiting.")
	exit(1)
cam.configure()
log.info(cam)


# Defining variables for common modes
video = "video"
image = "image"
unique_check = True   # Only asserted during experiment mode.
def capture(action, name, *args, **kwargs):
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


def close_exp():
	"""
	Close experiment and reset the current directory to the original.
	"""
	exp.close()
	print("--- Exiting experiment --\n")

# Overloaded Exit function
def exit():
	if exp and exp.active:
		exp.close()
	sys.exit()



## 4. Set Experiment
print("All current experiments on the Microscope:")
print(Experiment.list_all())
print("\nCall intro() to get an introduction.")
print("\n\n")
print("Press Ctrl+Z to exit or enter to ignore.")
exp_name = input("Input the session/experiment name -> ")
exp_name.strip()

exp = None
if exp_name:
	exp = Experiment(exp_name)

## Test
pico("l1.setVs(2,0,0)")

#print(sys.path)






