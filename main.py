#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import pprint
from pprint import pprint as ppprint
import os
import sys
sys.path.append(os.path.abspath("./abcs"))
import abcs
import readline

import yaml
from yaml.loader import SafeLoader
from colorama import Fore

# Hardware
from cameras.selector import CameraSelector
from lights.selector import LightSelector
from picodevice import RPiPicoDevice
from picolight import PicoLight
from utilities import autocompleter

# Other Resources
from experiment import Experiment
from utilities.fluff import pageheader, intro
from sync import SyncEngine
from time import sleep
from devicetree import ScopeAssembly
from terminalplot import *
from scriptengine import LoadScript
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
global scopeid, scope_user
scopeid = device_metadata["name"]


RPiPicoDevice.print_all_ports()

##3. Print Header
#from colorama import init
#init()
print(pageheader())



## 4. Set hardware resources

## TODO concise
print("----- LIGHTS -----")
picomode = "null" * (device_metadata["hardware"]["pico"][0] == "nullpico") + \
           "normal" * (device_metadata["hardware"]["pico"][0] == "pico")

pico = RPiPicoDevice.Select(picomode, name=device_metadata["hardware"]["pico"][1], \
	   connect=False)
pico.auto_connect()
#pico.connect("/dev/ttyACM1")
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

#----
print("\n\n----- SCOPE READY -----")
device = ScopeAssembly()
#

# Defining variables for common modes
vid = "vid"
img = "img"
vidmp4 = "vidmp4"
prev = "preview"
vid_noprev = "vid_noprev"
unique_check = True   # Only asserted during experiment mode.

def capture(action, name, *args, **kwargs):
	"""
	Default capture 
	"""
	if not cam.is_open():
		cam.open()
		sleep(1)
	print(f"acq: {name}")
	
	if not action:
		action = "video"
	
	# File  uniqueness check
	if unique_check:
		if exp.active:
			if not exp.unique(name):
				print(f"{Fore.RED}File already exists - ignoring the call.{Fore.RESET}")
				return
	
	# Capture call -------------------------------
	cam.capture(action, name,  *args, **kwargs) #|
	#### -----------------------------------------

	#cam.close()
	
	if exp or exp.active():
		exp.log_event(name)

def preview(tsec):
	if cam:
		if cam.is_open():
			cam.preview(tsec=30)


def close_exp():
	"""
	Close experiment and reset the current directory to the original.
	"""
	exp.close()
	if cam:
		if cam.is_open():
			cam.close()
	print("--- Exiting experiment --\n")

# Overloaded Exit function
def exit():
	if exp:
		if exp.active:
			exp.close()
	if device_metadata["auto_fsync"]:
		SyncEngine.fsync(device_metadata)
	
	if cam:
		if cam.is_open():
			cam.close()
	sys.exit()



## 4. Set Experiment
print("\n\n----- ACTION -----")
print("All current experiments on the Microscope:")
ppprint(Experiment.list_all())
exp_name = None
print("\nCall intro() to get an introduction.")
if not scriptfiles:
	
	print("\n\n")
	
	print("Press Ctrl+Z to exit or enter to ignore.")

	#autocompleter.directory("/Users/byatharth/experiments")
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
		LoadScript(exefile)
##------


## Test
#pico("l1.setVs(2,2,0)")
#print(sys.path)
scope_user = "ghost"
def set_user(user):
	print(f"{Fore.BLUE}trappy-scope says: {Fore.RESET}Hello! {user}.")
	scope_user = user
	if exp:
		if exp.active:
			exp.user = scope_user
			sys.ps1 = exp.header()
		else:
			sys.ps1 = f"{Fore.BLUE}user:{scope_user}{Fore.RESET} || >>> "

	elif user == "" or user == None:
		sys.ps1 = ">>> "
	else:
		sys.ps1 = f"{Fore.BLUE}user:{scope_user}{Fore.RESET} || >>> "


