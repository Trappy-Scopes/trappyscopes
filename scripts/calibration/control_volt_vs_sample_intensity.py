import datetime
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
import numpy as np
import time
from sklearn.linear_model import LinearRegression


__description__ = \
"""
Procedure to calibrate the control voltage of the LED by measuring the light intensity at the sample stage.
Generates a measurement stream for each channel. And also generates sepearte streams for mixed modalities.

This script takes hours (more than 12) with stabilization_delay_s=3 recommended and complete 3 channel scan.
"""


def create_exp():
	# Start experiment
	global exp
	exp = Experiment.Construct(["light", "calibration", "volt_vs_intensity"])


	exp.params["volt_limits"] = {"red":[0, 3], "green":[0,3], "blue":[0,3]}
	exp.params["step_size"] = 0.2
	exp.params["measurements"] = [["red"], ["green"], ["blue"],
								  ["red", "green"], ["red", "blue"], ["green", "blue"],
								  ["red", "green",  "blue"]
								  ]
	exp.params["stabilization_delay_s"] = 3



def set_ch(channels, vals):
	global scope
	#scope = ScopeAssembly.current
	for ch in channels:
		global scope
		for val_idx, ch in enumerate(channels):
			scope.tree[ch].setV(float(vals[val_idx]))



def measure_stream(channels, beacon=False, sensor_name="sensor"):
	"""
	Open a measurement stream for each "measurement" and iterate over intensity values.
	"""
	global exp, scope
	
	if beacon:
		scope.beacon.on()
		time.sleep(exp.params["stabilization_delay_s"])
	else:
		scope.beacon.off()
		time.sleep(exp.params["stabilization_delay_s"])
	
	scope.lit.setVs(0,0,0) ## Reset

	name_stream = lambda chs :  '_'.join(chs)
	ms = exp.new_measurementstream(name_stream(channels), monitors=["channels", "beacon", "temp"], measurements=["volts", "counts"])
	
	channel_limits = {ch: exp.params["volt_limits"][ch] for ch in  channels}
	print("Measuring: ", channel_limits)
	lines = [np.arange(*exp.params["volt_limits"][ch], exp.params["step_size"]) for ch in channels]
	
	grid = np.meshgrid(*lines, indexing='ij')
	grid = np.array(grid).reshape(len(lines), -1).T
	for volts in grid:
		set_ch(channels, volts)
		time.sleep(exp.params["stabilization_delay_s"])
		count_value = scope[sensor_name].read()

		m = ms(channels=channels, counts=count_value, volts=list(volts), beacon=beacon, temp=scope.tandh.read()["temp"])
		print(m)

		


def start_measurements():
	global exp
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=False)
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=True)


def single_channel_calibration():
	"""Single Channel calibration uses the TSL2591 digital light sensor and constants for ThorLabs RGBE LED.
	"""
	global exp
	global scope
	## Maps wavelength in nanometers to Conversion constant of the sensor.
	wavelengths = [scope.red.params['lambda_nm'],
               scope.blue.params['lambda_nm'],
               scope.green.params['lambda_nm']]
	phi_map = {627.5:1.2, 630:1.2, 850:0.7, 525:1.1, 467.5:0.4}
	print("Phi map: ", phi_map)
	print("Wavelengths (nm): ", wavelengths)

	if not set(phi_map.keys()).issubset(wavelengths):
		raise Exception(f"Calibration constant is not defined for all wavelengths. Please check.")

	
	exp.params["measurements"] = exp.params["measurements"][:3]
	print(f"Measuring channels: {exp.params['measurements']}")
	
	## Take measurements -------------------------------------------------------
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=False)
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=True)

	## Now need to convert the counts to umol per m^2s using the calibration equation.
	sensor_gain = 16
	def convert_pfd(counts, lambda_nm=None, Ga=None, phi=None):
	    hc = 1.986 # x10^-25
	    Re = 257.5
	    umol = 6.022 #x10^17
	    power = 0.1
	    numerator = (counts * lambda_nm * power)/umol
	    denominator = 100.0 * (1/Ga) * Re * phi * hc
	    return np.divide(numerator, denominator)

	## For each measurement stream, calculate pfd for the given counts
	for ch in ["red", "blue", "green"]:
		ch_obj = scope[ch]
		wavelength = scope[ch].params.lambda_nm
		stream = exp.mstreams[ch]
		stream.df["pfd"] = stream.df.apply(convert_pfd, Ga=sensor_gain, lambda_nm=wavelength, phi=phi_map[wavelength])

		## Because volts is a list (planned for multichannel calibrations)
		stream.df["volts"] = stream.df["volts"].apply(lambda vlist: vlist[0])


		model = LinearRegression()
		model.fit(stream.df["volts"], stream.df["pfd"])

		ch_obj.params["calib_r_sq"] = model.score(stream.df["volts"], stream.df["pfd"])
		ch_obj.params["calib_coeff"] = model.coef_
		ch_obj.params["calib_intercept"] = model.intercept_
		ch_obj.params["calib_sensor_gain"] = sensor_gain
		ch_obj.params["volts"] = stream.df["volts"].to_list()
		ch_obj.params["pfd"] = stream.df["pfd"].to_list()
		ch_obj.params["counts"] = stream.df["counts"].to_list()
		ch_obj.params["calib_dt"] = datetime.datetime.now()


		print(f"Calibration done for channel: {ch}")
		print(ch_obj.params)

