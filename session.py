import datetime


def create_session(scope_name, datastore):

	"""
	Create a session in the `data` folder.
	"""

	# 1. ´data´ folder exists
	if not os.path.exists("./data"):
		os.mkdir("./data")
		print("Created `data` folder — primary node.")

	# 2. Create date folder
	now = datetime.datetime.now()
	date_folder = f"{scope_name}__{now.day}__{now.month}__{now.year}"
	extended_path = os.path.join("./data", date_folder)
	if not os.path.exists(os.path.join("./data", date_folder)):
		os.mkdir(extended_path)
		print(f"Created today's session folder: {os.abspath(extended_path)}")

	# 3. Create sessions folder
	session_md = MetaData("session")

	# This will persist until the Session is terminated
	session_defaults = {
							"cell_strain"     : "CC125",
							"cell_culture_id" : None,
							"temp_C"          : None,
							"humidity"        : None,
							"session_time"    : None
	}


	session_folder_name = session_md.file_descriptor(include=[scope_name])
	os.mkdir(session_folder_name)
	print(f"Session generated: {session_folder_name}")
	
	#datastore.new(session_md.file_descriptor())

def create_acquisition():

	# Default Aquisitions
	acq_defaults = {
						"mode"           : "video",
						"tsec"           : 30,
						"illumination_V" : (2,2,2),
						"preview"        : True,

						# Can be skipped
						"iterations"     : 1,
						"delay_s"        : 0,

						# To be calculated after acquisition
						"acq_time_s"     : None,
						"capture_lag"    : None
					}

	acq_md = MetaData("start acquisition"):
	acq_md.add_que('Acquisition mode ["video", "image", "timelapse"]: ', label="acq_mode")
	for key in acq_defaults.keys()[1:]:
		acq_md.add_que(key)

	acq_md.collect()

	if acq_md.collected:
		return acq_md.metadata
	else:
		return acq_defaults