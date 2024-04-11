import yaml
"""
Obsolete to ScopeAssembly class in devicetree.py. Salvage!
"""

class Microscope:

	"""
	Class that describes the `Microscope`  object.
	"""


	def __init__(self, pins, config=None):
		self.name = None
		self.id = None
		self.port = None
		self.address = None

		self.session_id = None
		self.cam_open = False


		self.camera = None         # Camera object
		self.lights = None         # Lights / Illumination
		self.mcu = None            # Microcontroller Unit (MCU)
		self.pump = None           # Syrenge Pump
		self.mcu_firmware = None   # MCU Control Firmware
		self.gpio = None           # Raspberry Pi GPIO
		self.optics = None         # Hold infomration about the optical components
		self.chambers = None       # Represents the chamber(s) in the microscope


		# State Information
		self.run_state = Metadata()                       # Metadata object
		self.cam_config = yaml.load(".camconfig.yaml")  # Camera configuration
		self.state = yaml.load(".scopeconfig.yaml")       # Misc state information


		# Set Microscope Settings
		self.lights.set(self.state["color"], self.state["lux"])

		# Data
		self.frames = None
		self.sensor_data = None


	
		# Action Structure — A dictionary of 
		self.actions = { "image": self.__image__,
				    	 "video": self.__video__,
				         "preview": self.preview
				       }