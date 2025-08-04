import datetime
import datetime
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
import numpy as np
import time


__description__ = \
"""
Procedure to calibrate the control voltage of the LED by measuring the light intensity at the sample stage.
Generates a measurement stream for each channel. And also generates sepearte streams for mixed modalities.
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
	exp.params["stabilization_delay_s"] = 1



def set_ch(channels, vals):
	global scope
	#scope = ScopeAssembly.current
	for ch in channels:
		global scope
		for val_idx, ch in enumerate(channels):
			scope.tree[ch].setV(float(vals[val_idx]))



def measure_stream(channels, beacon=False):
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

	name_stream = lambda chs :  '_'.join(chs)
	ms = exp.new_measurementstream(name_stream(channels), monitors=["channels", "beacon"], measurements=["volts", "counts"])
	
	channel_limits = {ch: exp.params["volt_limits"][ch] for ch in  channels}
	print("Measuring: ", channel_limits)
	lines = [np.arange(*exp.params["volt_limits"][ch], exp.params["step_size"]) for ch in channels]
	
	grid = np.meshgrid(*lines, indexing='ij')
	grid = np.array(grid).reshape(len(lines), -1).T
	for volts in grid:
		set_ch(channels, volts)
		time.sleep(exp.params["stabilization_delay_s"])
		count_value = scope.sensor.read()

		ms(channels=channels, counts=count_value, volts=list(volts), beacon=beacon)

		


def start_measurements():
	global exp
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=False)
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=True)
