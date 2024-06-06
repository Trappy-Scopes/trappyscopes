#!/usr/bin/python
# -*- coding: utf-8 -*-



"""
Goal of this script:

-> Set up trappy-scopes control layer interface.
	|- 1. Parse arguments that enable special features (intaller, uid generation, etc).
	|_ 2. Condition machone - set up console and logging operations.
	|- 2. Update and maintain a prescription of repositories that are required for lab function.
	|- 3. Set-up a ScopeAssembly object on the machine - the virtual microscope object.
	|- 4. Expose standard object name for user convenience (exp, cam, lit, pico, etc).
	|- 5. Run the user-defined experimental script in the Experiment-Orchastration-Engine. 
	|- 6. Expose higher order functions for user conveneience (capture(), delexp(), findexp(), etc).
	*
"""


## ------------------------------––------------------------------- Goal 1 -----------------------------------------------------------------------
## Configurations
from config.common import Common
from sharing import Share
import argparser


## ------------------------------––-------------------------------  Goal 2 ----------------------------------------------------------------------

### Pretty printing
import readline
from rich import pretty
from rich import print
from rich.markdown import Markdown
pretty.install()



## Set Logging
import logsettings ## Why is this required ?
import logging
log = logging.getLogger("main")
import logging

class ErrorCollectingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.errors = []

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.errors.append(self.format(record))

    def summarize_errors(self):
        if not self.errors:
            return "No errors logged."
        return "\n".join(self.errors)

# Setup the custom handler
error_collector = ErrorCollectingHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
error_collector.setFormatter(formatter)

# Get the root logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # or any level you need
logger.addHandler(error_collector)




## Define exp object - for Crash safety
global exp
exp = None    # For crash safety - so far only standard python packages are invoked (except argparser).

## Login
from user import User
User.login(Share.argparse["user"])

## Create Session 
from bookeeping.session import Session
session = Session()

## Depreciate
import pprint
from pprint import pprint as ppprint
from colorama import Fore

import os
import sys
from time import sleep


import yaml
from yaml.loader import SafeLoader
from yamlprotocol import YamlProtocol


# Hardware - Depreciate
from cameras.selector import CameraSelector
from lights.selector import LightSelector
from picodevice import RPiPicoDevice



# Trappy-Scopes  Resources
from utilities import autocompleter ## TODO - sets completer upon 
import abcs
from experiment import Experiment
from utilities.fluff import pageheader, intro
from sync import SyncEngine
from devicetree import ScopeAssembly
from terminalplot import *
from sharing import Share
from loadscripts import ScriptEngine





## ------------------------------––-------------------------------  Goal 3 ----------------------------------------------------------------------
## Gitupdate repositories
import socket

def is_internet_available():
    try:
        # Attempt to resolve Google's DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

# Check if internet is available
if is_internet_available():
    print("Internet access available.")
else:
    print("No internet access.")

## 

#### ---------- Library Level processing ----------------------

print("\n\n")
## 0. Setlogging and device state
og_directory = os.getcwd()
User.exp_hook = exp




## 2. Load device ID an metadata
with open("config/deviceid.yaml") as deviceid:
	device_metadata = yaml.load(deviceid, Loader=SafeLoader)

from utilities.wallpaper import generate_wallpaper, def_wallpaper_path
generate_wallpaper(device_metadata)
os.system(f"pcmanfm --set-wallpaper {def_wallpaper_path}")

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

from optics import Optics
Optics.populate(device_metadata["optics"])

from scopeframe import ScopeFrame
ScopeFrame.populate(device_metadata)

from fluidicsdevice import FluidicsDevice
trap = FluidicsDevice("unknown microfluidics device", type="unknown")



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
	log.error("Could not get a pico device!")
else:
	pico.exec_main()
	log.info(pico)

print("[red]Light object l1 is no longer recognised.[default]")
#lit = RPiPicoDevice.Emit("l1", pico)
print("\n\n")

print(Markdown("# CAMERA"))
cam = CameraSelector(device_metadata["hardware"]["camera"])
#cam.open() # Camera should be already open upon creation.

if not cam.is_open():
	log.error("Could not get a camera device!")
else:
	#cam.configure()
	log.info(cam)

#----
print(Markdown("# SCOPE READY"))
scope = ScopeAssembly()
scope.add_device("cam", cam, description="Main camera.")
if pico.connected:
	scope.add_device("pico", pico, description="Main microcontroller on Serial.")
	scope.add_device("picoprox", RPiPicoDevice.Emit("", pico))
	try:
		all_pico_devs = pico.exec_cleanup("print(Handshake.obj_list(globals_=globals()))")
		for d in all_pico_devs:
			scope.add_device(d, RPiPicoDevice.Emit(d, pico), description="Pico peripheral.")
	except:
		print("pico: handshake failed!")			
scope.draw_tree()

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

# Output the summary of errors
from rich.rule import Rule
print(Rule(title="Summary of errors", style="red"))

print("Summary of errors:")
print(error_collector.summarize_errors())
print(Rule(style="red"))

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
#if len(sys.argv) > 1:
	#Experiment.run(sys.argv[1])
	#__import__(sys.argv[1], globals(), locals())
#	for exefile in scriptfiles:
#		LoadScript(exefile)
##------


## Test
#pico("l1.setVs(2,2,0)")
#print(sys.path)

from useractions import *

def exit():
	"""
	Custom overloaded exit function.
	"""
	if exp != None:
		if exp.active:
			exp.close()
	#if device_metadata["auto_fsync"]:
	#	SyncEngine.fsync(device_metadata)
	
	if cam:
		if cam.is_open():
			cam.close()
	sys.exit()

from transmit.hivemqtt import HiveMQTT
HiveMQTT.send(f"{scopeid}/init", {"state": "init", "session": Session.current.name, "id":1, "idf":123.4})




### Run all scripts
ScriptEngine.run_all(globals())



Share.updateps1()




