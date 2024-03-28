"""
This module processes the command line arguments passed to the trappy scopes CLI.

Options: <script1> <script2> <script3> : Positional, run in sequence.
         <script1> <script1> <script1> : Positional, run three times.
         -itr 3 <script1>              : Itterate three times.
         
         --login <user>                : Login to the terminal
         --experiment <exp-name>       :  Load experiment
"""

import argparse
#from rich import print

from loadscripts import ScriptEngine
from sharing import Share
import os

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
                    nargs=1, help='Login/Set user for the microscope.',  type=str,
                    metavar='<user-initials>') 
parser.add_argument('--login', dest='user', default="ghost", action='store', type=str,
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


### --- MP4 converter ------------------
parser.add_argument('-mp4', '--mp4', metavar=('<exp-name>'), dest='tomp4_exp', 
                    action='store', nargs=1, type=str, 
                    help='Convert all the .h264 videos in the experiment folder to .mp4 videos.')

parser.add_argument('-fps', '--fps', metavar='<fps>', dest='fps', 
                    action='store', nargs=1, type=int, default=30, 
                    help='Specify the fps for conversion to mp4.')
### ------------------------------------


### --- Trappy-Scopes installation -----
parser.add_argument('-install', '--install', dest='install', 
                    action='store_true',
                    help='Do installation of all required python and Unix libraries required for trappyscopes.')
### ------------------------------------



### --- Count lines of code in the project -----
parser.add_argument('-loc', '--loc', dest='loc', 
                    action='store_true',
                    help='Count lines of code for this project.')
### -------------------------------------------



### --- Generate a unique identifier ----------
parser.add_argument('-uid', '--uid', dest='uid', 
                    action='store_true',
                    help='Generate a trappy-scopes (systems) unique identifier.')
### -------------------------------------------


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


Share.argparse["user"] = args.user[0]
Share.argparse["expname"] = args.expname
Share.argparse["noep"] = (args.noep and (len(scriptlist) > 0))
Share.argparse["nofluff"] = args.nofluff

if args.intro:
    from utilities.fluff import intro
    intro()
    exit(0)

if args.tomp4_exp:
    from utilities.mp4box import MP4Box
    args.tomp4_exp = args.tomp4_exp[0]
    args.tomp4_exp = os.path.join(Share.expdir, args.tomp4_exp)
    if os.path.exists(args.tomp4_exp):
        print(f"Appending all converted files to {args.tomp4_exp + '/processed'} .\nFPS set at: {args.fps}")
        MP4Box.convert_all(args.tomp4_exp, fps=args.fps, prompt=False)
    else:
        print(f"[red]Given experiment doesn't exist:[default] {args.tomp4_exp}")
    exit()

if args.install:
    from utilities.installer import Installer
    Installer.do_all()
    exit(0)

if args.loc:
    os.system("git ls-files | xargs wc -l ")
    exit(0)

if args.uid:
    from uid import uid
    from rich import print
    print(f"Unique identifier: {uid()}")
    exit()

