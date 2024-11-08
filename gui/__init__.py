
def open():
	import subprocess
	import sys

	# Launch a new process (e.g., opening a Python script or application)

	subprocess.Popen(["python", "gui/viewer.py"])

	# End the current session
	sys.exit()