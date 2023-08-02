import time
import config.common

def git_sync(deviceid):
	if deviceid["git_sync"]:
		os.system("git pull")

def fsync(deviceid):
	if deviceid["file_server"]:
		datadir = config.common.DATA_DIR
		if not datadir.endswith("/"):
			datadir += "/"
		os.system(["rsync", "-ar", datadir, \
				   deviceid["file_server"]])

def pico_fsync(deviceid, pico):
	if not "null" in str(deviceid["pico"][2]):
		pico.sync_files("./cameras/")
		pico.sync_files("./lights/")

		pico.sync(os.path.join(config.root, "/Trappy-Scopes/pico_firmware/")
