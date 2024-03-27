#!/usr/bin/python
# -*- coding: utf-8 -*-

### Parse args -----------------
import argparser
## -----------------------------



### Printing and logging -------
from rich import pretty
pretty.install()
import logging
# ------------------------------

import pprint
from pprint import pprint as ppprint
from rich import print
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
from sharing import Share
#from scriptengine import LoadScript
#sys.path.append(["./cameras/", "./lights/", "./abcs/"])
from user import User
from config.common import Common

from rich.markdown import Markdown

from useractions import *

#### ---------- Library Level processing ----------------------



## Set Logging

## Import DeviceMetadata

from user import User
User.login(Share.argparse["user"])


print("\n\n")
## 0. Setlogging and device state
og_directory = os.getcwd()
log = logging.Logger("main")
log.setLevel(0)
global exp
exp = None      # For crash safety
User.exp_hook = exp

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
#print("-"*100)
#print("\nDevice: ")
#print("-------")
from rich.pretty import Pretty
from rich.panel import Panel
devicepanel = Panel(Pretty(device_metadata), title="Device")
print(devicepanel)
#from rich.layout import Layout
#devicelayout = Layout(name="Device", size=15)
#devicelayout.update(str(device_metadata))
#print(device_metadata)
#log.critical(pprint.pformat(device_metadata))
global scopeid, scope_user
scopeid = device_metadata["name"]
Share.scopeid = scopeid
Common.scopeid = scopeid


RPiPicoDevice.print_all_ports()

##3. Print Header
#from colorama import init
#init()
print(pageheader())



## 4. Set hardware resources

## TODO concise
print(Markdown("# LIGHTS"))
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

print("\n\n")
print(Markdown("# CAMERA"))
cam = CameraSelector(device_metadata["hardware"]["camera"])
#cam.open() # Camera should be already open upon creation.
if not cam.is_open():
	log.error("Could not get a camera device - exiting.")
	exit(1)
#cam.configure()
log.info(cam)

#----
print(Markdown("# SCOPE READY"))
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
			cam.preview(tsec=tsec)


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

def LoadScript(scriptfile):
		print(f"{Fore.YELLOW}{'='*10} Executing: {Fore.WHITE}{scriptfile} {Fore.YELLOW} {'='*10}{Fore.RESET}")
		with open(scriptfile) as f:
			exec(f.read(), globals())


## 4. Set Experiment
print("\n\n")
print(Markdown("# ACTION"))

#exppanel = Panel(Pretty(Experiment.list_all()), title="Experiments so far")
#print(exppanel)

from rich.table import Table
exppanel = Table("#.", "EID", "Experiment", box=None, show_lines=True)
for i, exp_ in enumerate(Experiment.list_all()):
	exppanel.add_row(str(i), "xx", os.path.basename(exp_))
#exppanel = Panel(exppanel)

print(Panel(exppanel, title="All current experiments on the Microscope"))


exp_name = None
print("\nCall intro() to get an introduction.")
if not Share.argparse["noep"]:
	
	print("\n\n")
	
	print("Press Ctrl+Z to exit or enter to ignore.")
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter

	expcompleter = WordCompleter([os.path.basename(exp_) for exp_ in Experiment.list_all()])
	exp_name = prompt('Input the session/experiment name -> ', completer=expcompleter)
	#autocompleter.directory("/Users/byatharth/experiments")
	#exp_name = input("Input the session/experiment name -> ")
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


from measurement import Measurement
m = Measurement(q=2, qq=123, m=234, o=1.123)
Share.updateps1()
