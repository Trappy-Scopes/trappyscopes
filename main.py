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
import os
print(os.getcwd())
exec(open("argparser.py", "r").read())
from config.common import Common
from sharing import Share


## ------------------------------––-------------------------------  Goal 2 ----------------------------------------------------------------------

### Pretty printing
import readline
#xec(open("utilities/autocompleter.py", "r").read())
from rich.markdown import Markdown
from rich import print

from rich import pretty ## Default pretty printing
pretty.install()        ## Install pretty traceback handling
from rich.traceback import install as tracebackinstall 
tracebackinstall(show_locals=False)




## Set Logging
from core.permaconfig import logsettings ## Why is this required ?
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

#--------------------------------------------------------------
# from utilities import autocompleter ## TODO - sets completer upon 



#-------------------------------------------------------------

## Define exp object - for Crash safety
global exp
exp = Share.ScopeVars.exp


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
#from cameras.selector import CameraSelector
#from lights.selector import LightSelector ##Obsolete
#from picodevice import RPiPicoDevice



# Trappy-Scopes  Resources
#	import abcs
from experiment import Experiment
from expframework.protocol import Protocol


from utilities.fluff import pageheader, intro
#from sync import SyncEngine
from devicetree import ScopeAssembly
from terminalplot import *
from sharing import Share
from loadscripts import ScriptEngine





## ------------------------------––-------------------------------  Goal 3 ----------------------------------------------------------------------
## Gitupdate repositories
import socket

## transfered
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
os.system(f"pcmanfm --wallpaper-mode=fit --set-wallpaper {def_wallpaper_path}")

## -------- Synchronize ------------
#SyncEngine.git_sync(device_metadata)
## ---------------------------------


from rich.pretty import Pretty
from rich.panel import Panel
devicepanel = Panel(Pretty(device_metadata), title="Device")
print(devicepanel)


global scopeid, scope_user
scopeid = device_metadata["name"]
Share.scopeid = scopeid
Common.scopeid = scopeid

from optics import Optics
Optics.populate(device_metadata["optics"])
#optics = Optics()

#from scopeframe import ScopeFrame
#ScopeFrame.populate(device_metadata)

from hive.processorgroups.micropython import SerialMPDevice
SerialMPDevice.print_all_ports()

##3. Print Header
print(pageheader())





from hive.assembly import ScopeAssembly
scope = ScopeAssembly(scopeid)
scope.open(device_metadata, abstraction="microscope")
scope.draw_tree()


## 4. Set Experiment
print("\n\n")
print(Markdown("# ACTION"))


from rich.table import Table
exppanel = Table("#.", "EID", "Experiment", box=None, show_lines=True)
expmap = Experiment.list_all_eids()
for i, key in enumerate(expmap):
	exppanel.add_row(str(i), key, expmap[key])
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


from expframework.expsync import ExpSync
ExpSync.configure(device_metadata)


from useractions import *
if not Share.argparse["noep"]:
	exp = findexp()


from core.installer.installer import Installer



#from _hive.network.transmit.hivemqtt import HiveMQTT
#HiveMQTT.send(f"{scopeid}/init", {"state": "init", "session": Session.current.name, "id":1, "idf":123.4})

#from expframework.report import Report
#report = Report()



### Run all scripts
ScriptEngine.run_all(globals())


Share.updateps1()




