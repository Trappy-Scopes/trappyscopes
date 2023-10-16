import time
import config.common
import os
import subprocess
import sys
import colorama

class SyncEngine:

	def sync_all(deviceid):
		"""
		Does not call pico sync
		"""
		SyncEngine.git_sync(deviceid)
		SyncEngine.fsync(deviceid)


	def git_sync(deviceid):
		if deviceid["git_sync"]:
			print("Attempting git sync.")
			output = subprocess.check_output(["git", "pull", "--recurse-submodules"])
			output = output.decode()
			print(f"{colorama.Fore.YELLOW}output{colorama.Fore.RESET}")
			if not "Already up to date." in output:
				print(f"{colorama.Fore.RED}Please restart script. Updates were pulled.{colorama.Fore.RESET}")
				sys.exit()
		else:
			print("Skipping git sync...")

	def fsync(deviceid, remote=False):
		"""
		a : recursively sync while preserving timestamps, etc
		v : verbose
		h : human readable numbers
		P : progress report
		"""
		
		if deviceid["file_server"]:
			datadir = config.common.DATA_DIR
			print(colorama.Fore.BLUE)
			print("Attempting file server sync.")
			print(f"From: {datadir}\nTo: {deviceid['file_server']}")
			if not datadir.endswith("/"):
				datadir += "/"
			if not remote:
				subprocess.run(["rsync", "-avhi", "--stats", datadir, deviceid['file_server']])
			else:
				print("Implementation missing!")
			print(colorama.Fore.RESET)
	

	def pico_fsync(pico):
		
		print("Attempting pico device sync.")
		pico.sync_files("./utilities/pico_firmware/")
		pico.sync_files("./cameras/")
		pico.sync_files("./lights/")

		pico.sync(os.path.join(config.root, "/Trappy-Scopes/pico_firmware/"))
