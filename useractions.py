def capture(action, name, *args, **kwargs):
	"""
	Default capture 
	"""
	if not cam.is_open():
		cam.open()
		sleep(1)
	print(f"acq: {name}")
	
	if not action:
		action = "video"
	
	# File  uniqueness check
	if unique_check:
		if exp.active:
			if not exp.unique(name):
				print(f"{Fore.RED}File already exists - ignoring the call.{Fore.RESET}")
				return
	
	# Capture call -------------------------------
	cam.capture(action, name,  *args, **kwargs) #|
	#### -----------------------------------------

	#cam.close()
	
	if exp or exp.active():
		exp.log_event(name)

def preview(tsec):
	if cam:
		if cam.is_open():
			cam.preview(tsec=30)


def close_exp():
	"""
	Close experiment and reset the current directory to the original.
	"""
	exp.close()
	if cam:
		if cam.is_open():
			cam.close()
	print("--- Exiting experiment --\n")

# Overloaded Exit function
def exit():
	if exp:
		if exp.active:
			exp.close()
	if device_metadata["auto_fsync"]:
		SyncEngine.fsync(device_metadata)
	
	if cam:
		if cam.is_open():
			cam.close()
	sys.exit()

def LoadScript(scriptfile):
		print(f"{Fore.YELLOW}{'='*10} Executing: {Fore.WHITE}{scriptfile} {Fore.YELLOW} {'='*10}{Fore.RESET}")
		with open(scriptfile) as f:
			exec(f.read(), globals())