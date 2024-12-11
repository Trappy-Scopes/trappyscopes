import os
from rich import print

print("Trappy-Scopes startup protocol executed...")

from core.bookkeeping.yamlprotocol import YamlProtocol
scopeconfig = YamlProtocol.load(os.path.join(os.path.expanduser("~"), "trappyconfig.yaml"))



## --- Git synchronisation ----------------------
if scopeconfig["config"]["git_sync"]:
	print("Updating git repositories...")
	os.system("git pull")

	for remote, repo_dir in scopeconfig["config"]["git_dependencies"].items():
		
		print(f"Syncing {repo_dir} with remote {remote}")
		os.system(f"git -C {repo_dir} pull")


## ------- Set execution mode --------------------
#os.environ.putenv("TRAPPY_UI", "interactive")
import sys
print("Setting UI mode...")
print(f"ui_mode={scopeconfig["config"]["ui_mode"]}")