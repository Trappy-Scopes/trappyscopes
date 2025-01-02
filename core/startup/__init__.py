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
exec(open("argparser.py", "r").read())


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

from rich import pretty ## Default pretty printing
pretty.install()        ## Install pretty traceback handling
from rich.traceback import install as tracebackinstall 
tracebackinstall(show_locals=False)

import os
import logging
from core.permaconfig import logsettings ## Why is this required ?
# Get the root logger
import yaml
from yaml.loader import SafeLoader
from core.bookkeeping.yamlprotocol import YamlProtocol
with open(os.path.join(os.path.expanduser("~"), "trappyconfig.yaml")) as deviceid:
    device_metadata = yaml.load(deviceid, Loader=SafeLoader)
logger = logging.getLogger()
logger.setLevel(device_metadata["config"]["log_level"])  # or any level you need
logger.addHandler(logsettings.error_collector)


from experiment import Experiment
from expframework.protocol import Protocol


from utilities.fluff import pageheader, intro
from expframework.plotter import Plotter as plt
from core.permaconfig.sharing import Share
from loadscripts import ScriptEngine


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
Common.scopeid = scopeid

from rich.pretty import Pretty
from rich.panel import Panel
devicepanel = Panel(Pretty(device_metadata), title="Device")
print(devicepanel)

from hive.processorgroups.micropython import SerialMPDevice
SerialMPDevice.print_all_ports()

##3. Print Header
from rich.align import Align
from rich.rule import Rule
print("\n\n", Rule(characters='═', style="cyan"))
print(Align.center(pageheader()))
print(Rule(characters='═', style="cyan"), "\n\n")




from hive.assembly import ScopeAssembly
scope = ScopeAssembly(scopeid)
scope.open(device_metadata, abstraction="microscope")
scope.draw_tree()


## 4. Set Experiment
print("\n\n")

import rich.box as box
from rich.table import Table
exppanel = Table("#.", "EID", "Experiment", box=False, show_lines=True, title_style="blink2")
expmap = Experiment.list_all_eids()
for i, key in enumerate(expmap):
	exppanel.add_row(str(i), key, expmap[key])
#exppanel = Panel(exppanel)

print(Panel(exppanel, title="All current experiments on the Microscope", style="white"))
print("\nCall intro() to get an introduction.")

# Output the summary of errors
from rich.rule import Rule
print(Rule(title="Summary of errors", style="red"))

print("Summary of errors:")
print(logsettings.error_collector.summarize_errors())
print(Rule(style="red"))


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

### Run all scripts
if not Share.argparse["noep"]:
	exp = findexp()
scope.add_device("exp", Experiment.current)

from core.installer.installer import Installer



#from _hive.network.transmit.hivemqtt import HiveMQTT
#HiveMQTT.send(f"{scopeid}/init", {"state": "init", "session": Session.current.name, "id":1, "idf":123.4})

#from expframework.report import Report
#report = Report()


ScriptEngine.run_all(globals())
Share.updateps1()