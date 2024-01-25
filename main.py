#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import pprint
from pprint import pprint as ppprint
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
from sync import SyncEngine

#sys.path.append(["./cameras/", "./lights/", "./abcs/"])


print("\n\n")
## 0. Setlogging and device state
og_directory = os.getcwd()
log = logging.Logger("main")
log.setLevel(0)
exp = None      # For crash safety

## 1. Check script files
scriptfiles = None
if len(sys.argv) > 1:
	scriptfiles = [os.path.abspath(file) for file in sys.argv[1:]]
	scriptfiles = [file for file in scriptfiles if ".py" in file]

print("Scripts that will be loaded: ")
print(scriptfiles)


## 2. Load device ID an metadata
with open("config/deviceid.yaml") as deviceid:
	device_metadata = yaml.load(deviceid, Loader=SafeLoader)

## -------- Synchronize ------------
SyncEngine.git_sync(device_metadata)
## ---------------------------------
print("-"*100)
print("\nDevice: ")
print("-------")
log.critical(pprint.pformat(device_metadata))
scopeid = device_metadata["name"]

##3. Print Header
print(str(pageheader()).encode("utf-8"))



## 4. Set hardware resources

## TODO concise
print("----- LIGHTS -----")
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

print("\n\n----- CAMERA -----")
cam = CameraSelector(device_metadata["hardware"]["camera"])
#cam.open() # Camera should be already open upon creation.
if not cam.is_open():
	log.error("Could not get a camera device - exiting.")
	exit(1)
#cam.configure()
log.info(cam)


# Defining variables for common modes
vid = "vid"
img = "img"
vidmp4 = "vidmp4"
preview = "preview"
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
	if device_metadata["auto_fsync"]:
		SyncEngine.fsync(device_metadata)
	sys.exit()



## 4. Set Experiment
print("All current experiments on the Microscope:")
pprint.pprint(Experiment.list_all())
exp_name = None
print("\nCall intro() to get an introduction.")
print("----- ACTION -----")
if not scriptfiles:
	
	print("\n\n")
	
	print("Press Ctrl+Z to exit or enter to ignore.")
	exp_name = input("Input the session/experiment name -> ")
	exp_name.strip()

exp = None
if exp_name:
	exp = Experiment(exp_name)



## Run Scriot file
if len(sys.argv) > 1:
	#Experiment.run(sys.argv[1])
	#__import__(sys.argv[1], globals(), locals())
	for exefile in scriptfiles:
		with open(exefile) as f:
			exec(f.read(), globals())
##------


## Test
#pico("l1.setVs(2,2,0)")
#print(sys.path)






