import time
import config.common
import os
import subprocess
import sys

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
			output = subprocess.check_output(["git", "pull"])
			output = output.decode()
			if not "Already up to date." in output:
				print("Restarting script after syncing updates.")
				os.execv(sys.argv[0], sys.argv)

	def fsync(deviceid):
		if deviceid["file_server"]:
			print("Attempting file server sync.")
			datadir = config.common.DATA_DIR
			if not datadir.endswith("/"):
				datadir += "/"
			os.system(["rsync", "-ar", datadir, \
					   deviceid["file_server"]])

	def pico_fsync(pico):
		
		print("Attempting pico device sync.")
		pico.sync_files("./cameras/")
		pico.sync_files("./lights/")

		pico.sync(os.path.join(config.root, "/Trappy-Scopes/pico_firmware/"))
