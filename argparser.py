"""
This module processes the command line arguments passed to the trappy scopes CLI.

Options: <script1> <script2> <script3> : Positional, run in sequence.
         <script1> <script1> <script1> : Positional, run three times.
         -itr 3 <script1>              : Itterate three times.
         
         --login <user>                : Login to the terminal
         --experiment <exp-name>       :  Load experiment
"""

import argparse
from scriptengine import ScriptEngine
from sharing import Share
from user import User
from utilities.fluff import intro
from rich import print

parser = argparse.ArgumentParser(description='Trappy-Scopes Control Layer', 
                                 prog="Trappy-Scopes scope-cli")


### --- script parsing ----------------
parser.add_argument('scriptlist_', metavar='<script>', type=str,
                    action="append", nargs='?', 
                    help='List of scripts to execute in sequence')

parser.add_argument('-itr', '--iterate', metavar=('N', '<script>'), dest='scriptlist_', 
                    action='append', nargs=2, 
                    help='Specify the number of iterations to perform for a given script.')
### ------------------------------------

### --- login --------------------------
parser.add_argument('-su', '--setuser', dest='user', default="ghost", action='store',
                    nargs=1, help='Login/Set user for the microscope.', 
                    metavar='<user-initials>')
parser.add_argument('--login', dest='user', default="ghost", action='store',
                    nargs=1, help='Login/Set user for the microscope.',
                    metavar='<user-initials>')
### ------------------------------------

### --- experiment ---------------------
parser.add_argument('-exp', '--experiment', dest='expname', default=None, action='store',
                    nargs=1, help='Set the experiment.', metavar='<exp-name>')
### ------------------------------------

## ---- enter-experiment prompt --------
parser.add_argument('-noep', '--noep', dest='noep', default=False, action='store_true',
                    help='Skip prompt to select experiment')
### ------------------------------------

### --- supres-fluff -------------------
parser.add_argument('-noff', '--nofluff', dest='nofluff', default=False, action='store_true',
                    help='Supress all the fluff during startup.')

### ------------------------------------

### --- intro --------------------------
parser.add_argument('--intro', dest='intro', default=False, action='store_true',
                    help='Print the scope CLI introduction document.')
### ------------------------------------
### ------------------------------------


### Parse !!!!!!!!!!!!!!!
args = parser.parse_args()


### ---- Process Scriptlist -----------------
scriptlist = []
for script in args.scriptlist_:
    if not isinstance(script, list):
        scriptlist.append(script)
    else:
        scriptlist += [script[1]]*int(script[0])
ScriptEngine.execlist = scriptlist
####### --------------------------------------

User.login(args.user)
Share.argparse["expname"] = args.expname
Share.argparse["noep"] = (args.noep and (len(scriptlist) > 0))
Share.argparse["nofluff"] = args.nofluff

if args.intro:
    intro()
