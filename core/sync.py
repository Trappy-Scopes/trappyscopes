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
		#pico.sync_files("./cameras/")
		#pico.sync_files("./lights/")

		pico.sync(os.path.join(config.root, "/Trappy-Scopes/pico_firmware/"))

	def check_nfs(server="smb://TrappyCloud"):
		from smbprotocol.connection import Connection
		from smbprotocol.session import Session
		from smbprotocol.tree import Tree

		# Replace these with your SMB server details
		server_name = server
		if "TrappyCloud" in server:
			share_name = "G"
		else:
			share_name = "/"
		guest_username = "guest"
		guest_password = ""

		# Connect to the SMB server
		connection = Connection()
		connection.connect(server_name)

		# Authenticate as guest with an empty password
		session = Session(connection, server_name, guest_username, guest_password)
		session.connect()

		# Connect to the shared folder
		tree = Tree(session, share_name)

		# Now you can perform operations on the shared folder, e.g., list files
		print(f"Current composition of the nfs {server}:")
		files = tree.list_directory("/")
		for file_info in files:
		    print(file_info)

		# Don't forget to disconnect when done
		tree.disconnect()
		session.disconnect()
		connection.disconnect()

