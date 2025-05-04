"""
Goal of this script:

-> Set up trappy-scopes control layer interface.
	|- 1. Parse arguments that enable special features (intaller, uid generation, etc).
	|_ 2. Condition machine - set up console and logging operations.
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
#exec(open("..argparser.py", "r").read())
from core.argparser import *

### --------------  Load metadata --------------------------
from core.permaconfig.config import TrappyConfig
device_metadata = TrappyConfig()
device_metadata = device_metadata.get()
## --------------------------------------------------


## Login
from core.bookkeeping.user import User
User.login(Share.argparse["user"])

## Create Session 
from core.bookkeeping.session import Session
session = Session()

## Define exp object - for Crash safety
global exp

## ------------------------------––-------------------------------  Goal 2 ----------------------------------------------------------------------

### Pretty printing
import readline
#xec(open("utilities/autocompleter.py", "r").read())
from rich.markdown import Markdown
from rich import print




import os
import logging
from core.permaconfig import loggersettings ## Why is this required ?
# Get the root logger
import yaml
from yaml.loader import SafeLoader
from core.bookkeeping.yamlprotocol import YamlProtocol



from expframework.experiment import Experiment
from expframework.protocol import Protocol


from utilities.fluff import pageheader, intro
from expframework.plotter import Plotter as plt
from core.permaconfig.sharing import Share


## ------------------------------––-------------------------------  Goal 3 ----------------------------------------------------------------------

print("\n\n")
## 0. Setlogging and device state
og_directory = os.getcwd()
from core.bookkeeping.user import User
User.exp_hook = exp




## 2. Load device ID an metadata

### Depreciate
if device_metadata["config"]["set_wallpaper"]:
	from utilities.wallpaper import generate_wallpaper, def_wallpaper_path
	generate_wallpaper(device_metadata)
	os.system(f"pcmanfm --wallpaper-mode=fit --set-wallpaper {def_wallpaper_path}")

global scopeid, scope_user
scopeid = device_metadata["name"]
Share.scopeid = scopeid


from rich.pretty import Pretty
from rich.panel import Panel
#device_metadata.panel()

from hive.processorgroups.micropython import SerialMPDevice
SerialMPDevice.print_all_ports()

##3. Print Header
from rich.align import Align
from rich.rule import Rule


## Draw Page header
for i in range(1, 5):
	print(Rule(characters='═', style=f"rgb(0,{51*i},{51*i})"),  end='')
print("\n")
#print("\n\n", Rule(characters='═', style="cyan"))
print(Align.center(pageheader()))
for i in range(1, 6):
	print(Rule(characters='═', style=f"rgb(0,{int(255/i)},{int(255/i)})"),  end='')


## Draw ScopeAssembly
from hive.assembly import ScopeAssembly
from hive.rpycserver import RpycServer
scope = ScopeAssembly(scopeid)
server = RpycServer()
RpycServer.roll["scope"] = scope
scope.open(device_metadata, abstraction="microscope")
for i in range(1, 5):
	print(Rule(characters='═', style=f"rgb({51*i},{51*i},0)"),  end='')
scope.draw_tree()
for i in range(1, 5):
	print(Rule(characters='═', style=f"rgb({int(255/i)},{int(255/i)},0)"),  end='')


## Set Experiment
import rich.box as box
from rich.table import Table
exppanel = Table("#.", "EID", "Experiment", box=False, show_lines=True, title_style="blink2")
expmap = Experiment.list_all_eids()
for i, key in enumerate(expmap):
	exppanel.add_row(str(i), key, expmap[key])
#exppanel = Panel(exppanel)
for i in range(1, 5):
	print(Rule(characters='═', style=f"rgb({51*i},{51*i},{51*i})"),  end='')
print(Panel(exppanel, title="All current experiments on the Microscope", style="white"))
for i in range(1, 6):
	print(Rule(characters='═', style=f"rgb({int(255/i)},{int(255/i)},{int(255/i)})"),  end='')


# Output the summary of errors
from rich.rule import Rule
for i in range(1, 4):
	print(Rule(characters='═', style=f"rgb({int(51*i)},0,0)"),  end='')
print(Rule(title="Summary of errors", characters='═', style=f"rgb({int(51*5)},0,0)"),  end='')
print(loggersettings.error_collector.summarize_errors())
print(Rule(characters='═', style=f"rgb({int(51*5)},0,0)"),  end='')
for i in range(1, 5):
	print(Rule(characters='═', style=f"rgb({int(255/i)},0,0)"),  end='')
print("\n")

print("\nCall intro() to get an introduction.")


from expframework.expsync import ExpSync
ExpSync.configure(device_metadata)


#from .useractions import *
#import useractions
try:
	exec(open("core/startup/useractions.py").read())
except:
	exec(open("useractions.py").read())
finally:
	pass

print("Use `exp = findexp()` to search for an old experiment.")
print("Use `exp = Experiment('new_name')` to create a new experiment.")

### Run all scripts
#if not Share.argparse["noep"]:
#	exp = findexp()
#scope.add_device("exp", Experiment.current)

from core.installer.installer import Installer

from core.bookkeeping.registry import Reg
if scopeid == "MDev":
	Reg.load()


from hive.laboratory import Lab
lab = Lab()

#from _hive.network.transmit.hivemqtt import HiveMQTT
#HiveMQTT.send(f"{scopeid}/init", {"state": "init", "session": Session.current.name, "id":1, "idf":123.4})

#from expframework.report import Report
#report = Report()

#from loadscripts import ScriptEngine
from expframework.scriptengine import ScriptEngine
if "startup_scripts" in device_metadata["config"]:
	if device_metadata["config"]["startup_scripts"]:
		ScriptEngine.execlist += device_metadata["config"]["startup_scripts"]
ScriptEngine.run_all(globals())
Share.updateps1()