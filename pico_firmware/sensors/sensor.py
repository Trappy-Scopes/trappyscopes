# TODO: Implementation

class Sensor:
	"""
	Defines the common communication protocol for any/all sensors.

	Required structured fields:

	sensor-output:
		- pckt-id
		- time
		- unique-id:
			- pico-device-id
			- sensor-id
		- data-struct
		- op-mode

	"""
	roll = []
	def add(sensorobj):
        roll.append(sensorobj)
    
	def __init__(self, name, type_, fields):
		self.struct = {}
		self.name = name
		self.type = type_
		self.deviceid = "picoid"

		self.uid = f"{deviceid}-{self.name}-{self.type}"
		self.pckt_id = 0


		self.op_mode = "singleshot"

	def read():
		"""
		Read the sensor.
		"""
		pass

	def transmit(self, data):
		struct = {}

		self.pckt_id = self.pckt_id + 1
		struct["pckt_id"] = self.pckt_id
		struct["time"] = self.rtc.datetime()
		struct["uid"] = self.uid
		struct["data"] = data
		struct["op_mode"] = self.op_mode

		return self.struct

	def periodic_sample(self, period):
		self.op_mode = "periodic"

		self.timer = Timer(period=1000*config.tandh_sample_period_s, mode=Timer.PERIODIC, \
		                     callback=tandh_callback)