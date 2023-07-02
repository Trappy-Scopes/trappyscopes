import sys
sys.path.append("./cameras/")

def CameraSelector(device):
	device = device.strip().lower()

	if device == "rpi_hq_picam2":
		from  rpi_hq_picam2 import Camera
		return Camera()
	
	if device == "rpi_hq_picam1":
		from rpi_hq_picam1 import Camera
		return  Camera()
	
	if device == "alliedvision":
		from alliedvision import Camera
		return Camera()

	if device == "null":
		from abcs.camera import Camera
		return Camera()

	log.error(f"Invalid camera mode: {device}")
