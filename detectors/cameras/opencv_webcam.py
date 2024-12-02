import cv2
from detectors.cameras.abstractcamera import Camera as AbstractCamera

class Camera(AbstractCamera):

	# 1
	def __init__(self, *args, **kwargs):
		self.cam = None
		self.actions = {"img": self.__img__}

	# 2
	def open(self):
		return

	# 3
	def close(self):
		return

	def is_open(self):
		return True

	# 4
	def configure(self, config_file=None, res=None, fps=None):
		print("macos configuration!")


	# 5
	def preview(self, tsec=30):
		return

	def __img__(self, filename, *args, **kwargs):
		cap = cv2.VideoCapture(0)
		
		if not cap.isOpened():
			print("Error: Could not open camera.")
			return
		
		# Capture a single frame
		ret, frame = cap.read()
		
		if ret:
			# Save the captured frame as a PNG file
			cv2.imwrite(filename, frame)
			print(f"Image saved as {filename}")
		else:
			print("Error: Failed to capture image.")
		
		# Release the camera
		cap.release()
		cv2.destroyAllWindows()


	