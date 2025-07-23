from PIL import Image
import numpy as np
import os
from skimage import draw, morphology
from skimage.measure import centroid
from matplotlib.gridspec import GridSpec

SAMPLE_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "scripts", "trappyscope_alignment_tools", "sample_frame.png")

def load_image(path=SAMPLE_IMAGE_PATH):
	return np.array(Image.open(path))


def image_centroid(frame, radius=100, disk_thickness=10):
	"""
	Calculate the image centroid for a given grayscale frame.
	"""
	import matplotlib.pyplot as plt
	centroid_ = centroid(frame)

	## Add the deviation circle
	from skimage.draw import circle_perimeter
	mask = np.ones(frame.shape, dtype=np.uint8)
	rr, cc = circle_perimeter(int(frame.shape[0]/2), int(frame.shape[1]/2), radius)
	mask[rr, cc] = 0

	fig = plt.figure(figsize=(6, 6))
	gs = GridSpec(2, 2, 
				  width_ratios=[6, 1],    # 80% width for image, 20% for y-profile
				  height_ratios=[6, 1],   # 80% height for image, 20% for x-profile
				  wspace=0.05, hspace=0.05)

	# Top: Image plot
	ax = fig.add_subplot(gs[0, 0])
	img = ax.imshow(frame*mask, aspect='equal', origin='lower', interpolation=None)

	ax.set_ylabel('Y [px]')
	#ax.set_xticks([])

	xprof = frame[int(centroid_[1]):int(centroid_[1])+1,:].squeeze()
	yprof = frame[:, int(centroid_[0]):int(centroid_[0])+1].squeeze()


	# Bottom: Intensity profile
	ax2 = fig.add_subplot(gs[1, 0], sharex=ax)
	ax2.plot(xprof, color="red")
	ax2.set_xlabel('X [px]')

	# Right: Intensity profile
	ax3 = fig.add_subplot(gs[0, 1], sharey=ax)
	ax3.plot(yprof, np.arange(0, len(xprof)), color="blue")
	ax3.invert_xaxis()
	#ax3.invert_yaxis()
	ax3.yaxis.tick_left()
	ax3.xaxis.tick_top()


	ax.scatter(centroid_[1], centroid_[0], label='centroid', marker="x", color="red")
	
	ax.axvline(centroid_[1], linestyle="--", color="k")
	ax.axhline(centroid_[0], linestyle="--", color="k")

	delta_x = np.abs((centroid_[1]-int(frame.shape[0]/2)))
	delta_y = np.abs((centroid_[0]-int(frame.shape[1]/2)))
	ax.set_title(fr"$x_c$={centroid_[1]:.1f} $y_c$={centroid_[0]:.1f}{'\n'}$r$={radius} $\Delta_x$={delta_x:.2f} $\Delta_y$={delta_y:.2f}")

	return fig


def contrast_histogram(image, bins=256, lower_percentile_threshold=1.5):
	"""
	Calculates the histogram and Weber contrast value for a given image,
	lower_percentile_threshold: percentile of lower bound to be considered as "dark pixels".
	"""
	import matplotlib.pyplot as plt
	from skimage import img_as_float, exposure
	
	fig, ax = plt.subplots()

	# Display histogram
	hist, bins_, patches = ax.hist(image.ravel(), bins=np.arange(0, 256), histtype='step', color='black')

	ax.ticklabel_format(axis='y', style='scientific', scilimits=(0, 0))
	ax.set_xlabel('Pixel intensity')
	ax.set_ylabel('Number of pixels')
	ax.set_xlim(0, 256)

	finite_range_min = bins_[:-1][hist > 0].min()
	finite_range_max = bins_[:-1][hist > 0].max()
	ax.axvline(finite_range_min, color="maroon", linestyle="--", label="dark pixels")
	ax.axvline(finite_range_max, color="gray", linestyle="--", label="finite value range")


	percentile_ = np.percentile(image, (lower_percentile_threshold))
	ax.axvline(percentile_, color="maroon", linestyle="--", label="background region")

	dark_pixels = image.ravel()[image.ravel() < percentile_]

	I_b = hist.argmax()
	I_s = dark_pixels.mean()
	ax.axvline(I_b, color="blue", linestyle="--", label="background value")
	ax.axvline(I_s, color="red", linestyle="--", label="dark mean")
	weber_contrast = (I_b - I_s)/I_b
	ax.set_title(fr"$C$ = {weber_contrast:.2f} $I_s=${I_s:.2f} $I_b=${I_b:.2f}")
	fig.suptitle("Frame histogram and Weber contrast calculations")
	plt.legend()
	return fig

if __name__ == "__main__":
	image = load_image()
	fig = image_centroid(image)
	fig.show()
	fig = contrast_histogram(image)
	fig.show()