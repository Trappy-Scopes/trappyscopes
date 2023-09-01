from configr import Configr
from metadata2 import MetaData


# TODO:
# submodule Configr
# Publish metadata2 and submodule it
# 

def device_perma_state():
	"""
	Device state which is not subject to change and can be reliably collected anytime.
	"""
	from uuid import getnode as get_mac
	from socket import gethostname, gethostbyname
	mac=get_mac()
	mac_str=':'.join(("%012X" % mac) [i:i+2] for i in range(0,12,2))

	# If the IP address thing doesn't work.

	# Non-mutable configs
	ds =  {

		   # Hardware/Raspberry Pi Settings
		   "rpi_mac_address" : mac_str,
		   "rpi_ip_address"  : gethostbyname(gethostname()),
		   "rpi_username"    : gethostname(),
		   "rpi_os"          : platform.system(),
		   "rpi_os_release"  : platform.release(),

		   # Calibration Data
		   "calibration": {
		   					"illumination_last_date" : None,
		   					"illumination_channels"  : {},
		   					"th_last_date"           : {},
		   					"th_temperature"         : {},
		   					"th_humidity"            : {}
		   				  },

		   	"alignment": {"last_alignment_date" : None,
		   				  "global_alignment"    : False,
		   				  "section_alignment"   : False             
		   				 }
		  }
	return ds

def device_state(reconfig=None):
	"""
	Collects device state and returns it.
	It does not include anything that can be collected on site.
	"""
	ds_ref = {
				# Microscope ID
				"scope_name" : "trappy-scope",
				
				# Chamber
				"chamber_dia_mm" : 4,
				"chamber_fab_date" : None,
				"chamber_install_date" : None,

				# Optics
				"led_controls" : "pwm",
				"magnification": 1,
				"black_box" : False,
				"no_diffusers" : 2,
				"object_distance_mm" : None,
				"sample_condensor_distance_mm" : None,
				"led_height_mm" : None,
				"led_condensor_height_mm" : None
	}

	# Collect Microscope ID file
	device_state = 	Configr(ext=".yaml", ref=ds_ref):
	device_state.default_config_name = "trappy_config.yaml"
	
	config_file = device_state.find_config(self, dir_path=".config", ext="yaml", \
							 			   file_key="config", alphabatical=True)

	if not config_file:
		config_file = device_state.export_def_config()


	device_state.load(config_file)

	# Return State
	if not reconfig:
		return device_state.config
	
	# Reconfigure device state and write to file.
	else:
		print("Entering device state reconfiguration.")
		ds_reconfigr = Metadata("scope state")
		config_list = self.configr.keys()
		for key in config_list:
			self.add_que(f" {key}? [old value: {config_list[key]}]", label=key)

		ds_reconfigr.collect()

		if ds_reconfigr.collected:

			# Replace — only if new value is not None
			for key in config_list:
				if ds_reconfigr.metadata[key] != None:
					device_state.config[key] = ds_reconfigr.metadata[key]

			# Export file — !!! Replaces the old one
			ds_reconfigr.export("trappy_config.yaml", ds_reconfigr.config)

