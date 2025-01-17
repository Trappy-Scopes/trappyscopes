from rich import print
from experiment import Experiment
from core.bookkeeping.user import User
import datetime
import time

def yeast_capture(sample, tsec=10, force=False):
	"""
	Function to capture yeasty images.

	sample: sample name
	tsec: number of seconds before preview
	force: set true to rewrite images
	"""
	global exp, scope

	## Assert the write conditions
	if Experiment.current == None or Experiment.current.name != "Arrest_Ana_Yeast_Photos":
		exp = Experiment("Arrest_Ana_Yeast_Photos")

	## Login
	if User.info["user"] != "AG":
		User.login("AG")

	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	filename = f"{sample}_{dt}_{time_str}.png"

	if os.path.isfile(filename):
		print(f"[red][bold] ERROR : [red] Filename already exists: {filename}")
		print("[red] Choose a new one or pass force=True")
		return

	## Capture
	scope.cam.read("img", filename, tsec=tsec)


	## Sync
	exp.sync_dir()