import cv2


class Camera:

	# 1
	def __init__(self, *args, **kwargs):
		print("NullCamera initialised.")
		self.cam = None

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
		return

	# 5
	def capture(self, action, filepath, tsec=1,
				it=1, it_delay_s=0, init_delay_s=0):
		# Write a dummy file
		for i in range(it):
			if it == 1:
				cap = cv2.VideoCapture(0)
	
				if not cap.isOpened():
					print("Error: Could not open camera.")
					return
				
				# Capture a single frame
				ret, frame = cap.read()
				
				if ret:
					# Save the captured frame as a PNG file
					cv2.imwrite(filepath, frame)
					print(f"Image saved as {filepath}")
				else:
					print("Error: Failed to capture image.")
				
				# Release the camera
				cap.release()
				cv2.destroyAllWindows()

			else:
				with open(f"{i}_{filepath}", "w"):
					pass

	# 6
	def preview(self, tsec=30):
		return


	