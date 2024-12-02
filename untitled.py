import numpy as np



## Take images for different Exposure times.

def exposure_scan(scope, min_exposure, max_exposure, levels=10)
	for exposure in np.arange(min_exposure, max_exposure, levels):
		
		log.info(f"Exposure set to: {exposure}")
		scope.cam.configure("exposure", exposure)
		fname = f"exposure_{exposure}.png"
		img = scope.cam.capture("frame", fname)
		img
