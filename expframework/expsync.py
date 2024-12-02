from rich import print
import os
from sharing import Share
import logging as log
import asyncio
import subprocess
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
import time
import datetime


from uid import uid

class ExpSync:
	"""
	Synchronises experiment files with a remote server.
	"""
	active = False
	server = None
	share = None
	username = None
	password = None

	def configure(scopeconfig):
		ExpSync.active = scopeconfig["config"]["file_server"]["active"]
		ExpSync.server = scopeconfig["config"]["file_server"]["server"]
		ExpSync.share = scopeconfig["config"]["file_server"]["share"]
		ExpSync.username = scopeconfig["config"]["file_server"]["username"]
		ExpSync.password = scopeconfig["config"]["file_server"]["password"]

	def __init__(self, scopeid, experiment, max_threads=2):
		self.max_workers = max_threads
		if platform.system() == "Linux":
			log.debug("Plateform is Linux.")
			self.mount_addr = f"/mnt/{ExpSync.share}/"
			# Todo fill for linux.
		elif platform.system() == "Darwin":
			log.debug("Plateform is Darwin (MacOS).")
			self.mount_addr = f"/Volumes/{ExpSync.share}/"

		#if not os.path.exists(self.mount_addr):
		if ExpSync.active:
			self.mount(ExpSync.server, ExpSync.share, 
					   ExpSync.username, ExpSync.password)

		if ExpSync.active:
			self.mkexpdir(scopeid, experiment)

			if not os.path.exists(".sync"):
				self.set_sync_file()
		
		self.destination_dir = os.path.join(self.mount_addr, scopeid, experiment)
	
	def mkexpdir(self, scopeid, experiment):
		try:
			os.makedirs(os.path.join(self.mount_addr, scopeid, experiment), mode=0o777, exist_ok=True)
		except:
			os.system(f"sudo mkdir {os.path.join(self.mount_addr, scopeid, experiment)}")
		log.info("Created / confirmed remote Experiment directory.")

	def set_sync_file(self):
		"""
		Mark the experiment for synchronisation.
		"""
		syncid = uid()
		log.critical(f"Set experiment syncronisation with syncid: {syncid}")
		with open(".sync", "w") as file:
			file.write(f"syncid:{syncid}, {datetime.datetime.now()}\n")

	def mount(self, server, share, username, password):
		"""
		Mount an SMB share at a specified mount point.
		
		:param server: SMB server address (e.g., 192.168.1.10)
		:param share: SMB share name (e.g., shared_folder)
		:param mount_point: Local directory to mount the share
		:param username: SMB username
		:param password: SMB password
		"""
		import platform

		if platform.system() == "Linux":
			log.debug("Plateform is Linux.")
			mount_point = "/mnt"
			mount_cmd = ["sudo", "mount", "-t", "cifs", f"//{server}/{share}", \
						f"{mount_point}/{share}", "-m", "-o", \
						f"username={username},password={password},rw,file_mode=0777,dir_mode=0777,uid=1000,gid=1000"]
			try:
				subprocess.run(mount_cmd, check=True)
				print(f"Mounted //{server}/{share} at {mount_point}/{share}.")
				time.sleep(5)
			except Exception as e:
				print(e)
				if "error(16)" in str(e):
					log.info("file_server is already mounted!")
			print(f"{mount_point} dir for reference: ", os.listdir(mount_point))
			self.server = f"{mount_point}/{share}/"
		elif platform.system() == "Darwin":
			log.debug("Plateform is Darwin (MacOS).")
			try:
				mount_point = "/Volumes"
				mount_cmd = ["open", f"smb://{username}:{password}@{server}/{share}"]
				subprocess.run(mount_cmd, check=True)
				print(f"Mounted //{server}/{share} at {mount_point}/{share}.")
				time.sleep(5)
				print("/Volumes dir for reference: ", os.listdir("/Volumes"))
				self.server = f"{mount_point}/{share}/"
			except subprocess.CalledProcessError as e:
				print(f"Error mounting SMB share: {e}")
		else:
			log.error("Unsupported plateform (os).")
			return

	def sync_dir(self, remove_source=False):
		files = [f for f in os.listdir(os.getcwd())]
		files = [file for file in files if not file.startswith(".")]
		if remove_source:
			files = [file for file in files if file not in ["expstate.pickle", \
													   		"experiment.yaml", \
													   		"sessions.yaml"]]

		# Create a ThreadPoolExecutor for parallel execution
		with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
			if not remove_source:
				results = executor.map(self.sync_file, files)
			else:
				from functools import partial
				sync_ = partial(self.sync_file, remove_source=remove_source)
				results = executor.map(sync_, files)

		# Collecting the results (just for demonstration purposes)
		for result in results:
			if result is not None:
				log.debug(result)

	def sync_file(self, file, remove_source=False, delay_sec=0):
		"""
		Run rsync for a specific file or directory.
		"""

		# To account for file write delays for example.
		if delay_sec:
			time.sleep(delay_sec)

		source_removal = []
		if remove_source:
			source_removal.append('--remove-source-files')
		try:
			# Running rsync command
			command = [
				'sudo', 'rsync', '-avz', '--progress', '--inplace', *source_removal,
				os.path.join(os.getcwd(), file),
				os.path.join(self.destination_dir, file)
			]
			result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			log.info(f"Rsync completed for {file}")
			if remove_source:
				with open(".sync", "a") as f:
					f.write(f"{file}, {datetime.datetime.now()}\n")
			return result.stdout.decode()
		except subprocess.CalledProcessError as e:
			log.error(f"Error occurred with {file}: {e.stderr.decode()}")
			return None



# Example usage
if __name__ == '__main__':
	source_directory = '/path/to/source/directory'
	destination_directory = '/path/to/destination/directory'
	
	# Set the maximum number of parallel workers
	max_parallel_workers = 4
	
	# Start the rsync process
	rsync_directory(source_directory, destination_directory, max_parallel_workers)



