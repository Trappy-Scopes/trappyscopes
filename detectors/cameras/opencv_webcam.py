import cv2
import time

from detectors.cameras.abstractcamera import Camera as AbstractCamera

class Camera(AbstractCamera):

	# 1
	def __init__(self, *args, **kwargs):
		super().__init__()
		self.cam = None
		self.actions = {"img": self.__img__, "video":self.__video__}

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

	def __video__(self, filename, *args, **kwargs):

		tsec=kwargs["tsec"]
		frame_width = 640
		frame_height = 480
		fps = 30  # Frames per second

		# Initialize video capture (webcam, index 0)
		cap = cv2.VideoCapture(0)

		if not cap.isOpened():
		    print("Error: Cannot access the camera")
		    exit()

				# We need to set resolutions. 
		# so, convert them from float to integer. 
		frame_width = int(cap.get(3)) 
		frame_height = int(cap.get(4)) 


		# Set capture properties (optional, depending on your needs)
		cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
		cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
		cap.set(cv2.CAP_PROP_FPS, fps)

		# Define video writer
		fourcc = cv2.VideoWriter_fourcc(*'MJPG')  # Codec for .avi files
		out = cv2.VideoWriter(filename, fourcc, fps, (frame_width, frame_height))

		# Start recording
		start_time = time.time()

		while True:
		    ret, frame = cap.read()

		    if not ret:
		        print("Error: Failed to capture frame")
		        break

		    # Write frame to output file
		    out.write(frame)

		    # Display the frame (optional)
		    cv2.imshow('Recording...', frame)

		    # Check if the specified duration has elapsed
		    elapsed_time = time.time() - start_time
		    if elapsed_time >= tsec:
		        print("Recording complete")
		        break

		    # Exit early if 'q' is pressed
		    if cv2.waitKey(1) & 0xFF == ord('q'):
		        print("Recording stopped by user")
		        break

		# Release resources
		cap.release()
		out.release()
		cv2.destroyAllWindows()



	