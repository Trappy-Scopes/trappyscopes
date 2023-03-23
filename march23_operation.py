import subprocess
import fluff
#from picamera import PiCamera

def convert_to_mp4(filename, fps):
	foldername = filename.split(".")[0]
	mp4name = os.path.join(foldername, (filename.split(".")[0] + ".mp4"))

	command = f"MP4Box --add {filename}:fps={fps} {mp4name}"
	process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, shell=True)
	return mp4name

def create_folder(filename):
	foldername = filename.split(".")[0]
	os.mkdir(foldername, mode = 0o777)
	return foldername

def postprocess(filename):
	"""
	Postprocessing of recorded videos.
	"""

	# 1
	foldername = create_folder(filename)

	# 2
	mp4name = convert_to_mp4(filename)

	# 3 Move h264 to the same folder
	import shutil.move as move
	move(filename, os.path.join(foldername, filename))


def set_lightsV(rV, gV, bV):
	import pyboard
	pyb = pyboard.Pyboard('/dev/ttyACM0', 115200)
	pyb.enter_raw_repl()
	
	ret = pyb.exec(f"set_color_ch('r', {rV})")
	print(ret)

	ret = pyb.exec(f"set_color_ch('g', {gV})")
	print(ret)

	ret = pyb.exec(f"set_color_ch('b', {bV})")
	print(ret)
	
	pyb.exit_raw_repl()


def record_video(filename, res=[1920, 1088], fps=30, tsec=30):
	"""
	Call fucntion to record a video
	"""
	camera = PiCamera()
	camera.resolution = tuple(res)
	camera.framerate = fps
	print("Camera object acquired!")

	camera.start_recording(filename, format="h264")          # Start recording
	camera.start_preview()
	camera.wait_recording(tsec)                    				# Wait for while 
																# the camera records
	camera.stop_recording()                                     # Stop the camera
	print("Recording finished!")

	camera.close()

def preview(tsec=30):
	"""
	Simple function for previews.
	"""
	camera = PiCamera()
	camera.resolution = (1920, 1088)
	camera.framerate = 30

	camera.start_preview()
	time.sleep(tsec)
	camera.stop_preview()

	camera.close()

if __name__ == "__main__":

	print(fluff.header())

	# Step 1 - Turn on illumination
	set_lightsV(2,2,2)

	# Step 2 - Record Videos
	filename = None
	record_video(filename, res=[1920, 1088], fps=30, tsec=30)

	# Step 3 - postprocess
	folder = postprocess(filename)
	print(folder)

	# Step 4 - Transfer
	transfer_files(folder)


