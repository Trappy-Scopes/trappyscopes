def instasync(samplename, tsec=10, force=False, camera_mode="img", 
			  expname=None, user="ghost", newexp=None):
	"""
	Function to capture yeasty images.

	sample: sample name
	tsec: number of seconds before preview
	force: set true to rewrite images
	expname: Overrides (newexp, and user.)
	"""
	global exp, scope

	if expname:
		exp_name = "TS_VWR__AG__persistent_experiment"
	else:
		exp_name = f"{scopeid}__{newexp}__{user}"
	

	## Login
	User.login(user)

	## Assert the write conditions
	if Experiment.current == None or Experiment.current.name != exp_name:
		exp = Experiment(exp_name, append_eid=True)

	
	dt = str(datetime.date.today()).replace("-", "_")
	t = time.localtime(time.time())
	time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
	filename = f"{samplename}_AG_{dt}_{time_str}.png"

	if os.path.isfile(filename) and not force:
		print(f"[red][bold] ERROR : [red] Filename already exists: {filename}")
		print("[red] Choose a new one or pass force=True")
		return

	## Capture
	scope.cam.read(camera_mode, filename, tsec=tsec)

		## Sync
	print("[yellow] ------------ syncing -------------")
	exp.sync_dir()
	print("[yellow] ------------ syncing -------------")