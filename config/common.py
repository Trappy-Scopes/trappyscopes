import os
import yaml
from copy import deepcopy
from pprint import pprint

with open("config/deviceid.yaml") as f:
	deviceid = yaml.load(f, Loader=yaml.SafeLoader)

# --- Create skeleton of deviceid file ---
if deviceid["name"] == "MDev": #Development
	skeleton = deepcopy(deviceid)
	# Clear skeleton
	for key in skeleton:
		if isinstance(skeleton[key], dict):
			for nested_key in skeleton[key]:
				skeleton[key][nested_key] = None
		else:
			skeleton[key] = None

	with open("config/skeleton_deviceid.yaml", "w") as f:
		yaml.dump(skeleton, f, sort_keys=False)
## --

## Patch deviceid file from skeleton ----
with open("config/skeleton_deviceid.yaml", "r") as f:
	skeleton = yaml.load(f, Loader=yaml.SafeLoader)
for key in skeleton:
		if isinstance(skeleton[key], dict):
			for nested_key in skeleton[key]:
				if nested_key not in deviceid[key]:
					deviceid[key][nested_key] = None
					print(f"Added config in deviceid: {key}-{nested_key}")
		else:
			if key not in deviceid:
				deviceid[key] = None
				print(f"Added config in deviceid: {key}")


with open("config/deviceid.yaml", "w") as f:
	yaml.dump(deviceid, f,  sort_keys=False)
###


# DATA_DIR ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "experiments")
CALIB_DIR = os.path.join(os.path.expanduser("~"), "calibration")
if not deviceid["write_server"]:
	DATA_DIR = deviceid["write_server"]

	# Try direct link
	if not os.path.isdir(DATA_DIR):
		if os.path.isdir(os.path.join("/media/", os.getlogin(), DATA_DIR)):
			DATA_DIR = os.path.join("/media/", os.getlogin(), DATA_DIR)
		else:
			print("DATA_DIR resolution failed. Exiting!")
			exit(1)

print(f"Data directory: {DATA_DIR}")

if not os.path.isdir(DATA_DIR):
	os.mkdir(DATA_DIR)
	print(f"Created experiments directory: {DATA_DIR}")


# DATA_DIR ---