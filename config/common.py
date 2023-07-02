import os



# ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "experiments")

if not os.path.isdir(DATA_DIR):
	os.mkdir(DATA_DIR)
	print(f"Created experiments directory: {DATA_DIR}")