
def cam_config(camera):
	config_dict = {
			'resolution'     : camera.resolution,
			'framerate'      : camera.framerate,
			'ISO'            : camera.iso,
			'ana_gain'       : camera.analog_gain,
			'dig_gain'       : camera.digital_gain,
			'exposure_speed' : str(camera.exposure_speed/1000) + ' ms',
			'exposure_mode'  : camera.exposure_mode,
			'max_resolution' : camera.MAX_RESOLUTION,
			'max.framerate' : str(camera.MAX_FRAMERATE),
			'drc_strengths'  : camera.DRC_STRENGTHS
				  }
	return config_dict
