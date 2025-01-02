from abcs.camera import AbstractCamera


class Calibrator:

	def lux_profile(light, detector):

		if isinstance(detector, AbstractCamera):
			return __lux_by_camera__(light, detector)

		elif isinstance(detector, SpectroPhotometer):
			return __lux__by_spectrophotomerer__(light, detector)
		else:
			print("Calibrator:lux_profile: Unknown detector!")

	
	def __lux_by_camera__(light, camera):
		profile  = {}
		
		wait_time_s = 0.1
		step_size = 0.1

		light.off()
		for channel in "rgb":
			for i in [i*step_size for i in range(0, int(1.0/step_size))]:
				light.set_ch(channel, i)

				# Wait
				time.sleep(0.1)

				lux = camera.lux()
				profile[channel][i] = lux
			light.off()
		return profile


	def __lux__by_spectrophotomerer(light, spectrom):
		
		profile  = {}
		
		wait_time_s = 0.1
		step_size = 0.1

		light.off()
		for channel in "rgb":
			for i in [i*step_size for i in range(0, int(1.0/step_size))]:
				light.set_ch(channel, i)

				# Wait
				time.sleep(0.1)

				lux = spectrom.normalised_read()
				profile[channel][i] = lux
			light.off()
		return profile

	def resolution_USAFTarget(camera):
		pass
		## Capture some frames

		## Analyse the USAF-Target image profiles


