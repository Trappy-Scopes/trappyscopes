import datetime
from expframework.experiment import Experiment
from hive.assembly import ScopeAssembly
import numpy as np
import time
#from sklearn.linear_model import LinearRegression


__description__ = \
"""
Procedure to calibrate the control voltage of the LED by measuring the light intensity at the sample stage.
Generates a measurement stream for each channel. And also generates sepearte streams for mixed modalities.

The light meter is lux1 (scope.lightmeter): a TSL2561 T/FN/CL on a Seeed Grove Digital Light Sensor,
read at 16x gain and 101 ms. single_channel_calibration() checks this before it measures, because
its conversion constants (SENSOR below) only hold for that chip and those settings.

single_channel_calibration() takes a few minutes. The complete multi-channel scan
(start_measurements()) takes many hours.
"""


## Conversion constants for the light meter. AI Generated (Claude, Anthropic), 2026-11-16.
## Source: TAOS TSL2560/TSL2561 datasheet, TAOS059N (March 2009).
##   Re_640nm: irradiance responsivity of ch0 at 640 nm, 16x gain, 101 ms, TSL2561T/FN/CL column (typical).
##             The same table allows 750-1250 counts for a nominal 1000, i.e. +-25% between chips.
##   colour_factors: ch0 responsivity at each LED's peak wavelength relative to 640 nm, read off Figure 4
##             (red 627.5 nm, green 525 nm, blue 467.5 nm).
## Until 2026-11-16 this script used Re = 257.5 (a TSL2591 value) and factors 1.2 / 1.1 / 0.4,
## which made PFD about 1.4x too high for red and green and about 3.5x too high for blue.
SENSOR = {
	"chip": "TSL2561T/FN/CL",
	"gain": 16,
	"integration_ms": 101,
	"Re_640nm": 27.5,                       ## counts per uW/cm2
	"colour_factors": {"red": 1.00, "green": 0.91, "blue": 0.81},
	"source": "TAOS059N (March 2009): Re table and Figure 4",
}


def check_sensor():
	"""Stop unless the light meter is the chip, gain and integration time that SENSOR is for.

	scope.lightmeter.config is what the sensor reported about itself at handshake.
	"""
	global scope
	config = scope.lightmeter.config
	expected = {key: SENSOR[key] for key in ("chip", "gain", "integration_ms")}
	found = {key: config.get(key) for key in expected}
	if found != expected:
		raise RuntimeError(f"Light meter does not match the conversion constants: expected {expected}, "
		                   f"found {found}. Is lux1 connected, with the LightMeter firmware?")
	return config


def convert_pfd(counts, lambda_nm, colour):
	"""ch0 counts -> photon flux density in umol/m2/s, for a narrow-band LED of the given colour."""
	re = SENSOR["Re_640nm"] * SENSOR["colour_factors"][colour]     ## counts per uW/cm2
	irradiance_w_m2 = counts / re * 0.01                            ## uW/cm2 -> W/m2
	return irradiance_w_m2 * lambda_nm / 119.6                      ## W/m2 -> umol/m2/s (h*c*N_A)


def create_exp():
	# Start experiment
	global exp
	exp = Experiment.Construct(["light", "calibration", "volt_vs_intensity"])


	exp.params["volt_limits"] = {"red":[0, 3], "green":[0,3], "blue":[0,3]}
	exp.params["step_size"] = 0.1
	exp.params["measurements"] = [["red"], ["green"], ["blue"],
								  ["red", "green"], ["red", "blue"], ["green", "blue"],
								  ["red", "green",  "blue"]
								  ]
	exp.params["stabilization_delay_s"] = 0.2



def set_ch(channels, vals):
	global scope
	#scope = ScopeAssembly.current
	for ch in channels:
		global scope
		for val_idx, ch in enumerate(channels):
			scope.tree[ch].setV(float(vals[val_idx]))



def measure_stream(channels, beacon=False, sensor_name="lightmeter"):
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
	if not name_stream(channels) in exp.mstreams.keys():
		ms = exp.new_measurementstream(name_stream(channels), monitors=["channels", "beacon", "temp"], measurements=["volts", "counts", "ch1", "saturated"])
	else:
		ms = exp.mstreams[name_stream(channels)]
	channel_limits = {ch: exp.params["volt_limits"][ch] for ch in  channels}
	print("Measuring: ", channel_limits)
	lines = [np.arange(*exp.params["volt_limits"][ch], exp.params["step_size"]) for ch in channels]
	
	grid = np.meshgrid(*lines, indexing='ij')
	grid = np.array(grid).reshape(len(lines), -1).T
	for volts in grid:
		set_ch(channels, volts)
		time.sleep(exp.params["stabilization_delay_s"])
		reading = scope[sensor_name].read()      ## {"ch0", "ch1", "saturated"}; counts is ch0

		m = ms(channels=channels, counts=reading["ch0"], ch1=reading["ch1"], saturated=reading["saturated"],
		       volts=list(volts), beacon=beacon, temp=scope.tandh.read()["temp"])
		print(m)

		


def start_measurements():
	global exp
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=False)
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=True)


def single_channel_calibration():
	"""Single Channel calibration with the TSL2561 light meter (lux1) and constants for ThorLabs RGBE LED.
	"""
	global exp
	global scope
	sensor = check_sensor()
	exp.attribs["lightmeter"] = sensor
	print("Light meter: ", sensor)
	print("Conversion constants: ", SENSOR)

	exp.params["measurements"] = exp.params["measurements"][:3]
	print(f"Measuring channels: {exp.params['measurements']}")
	
	## Take measurements -------------------------------------------------------
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=False)
	for channels in exp.params["measurements"]:
		measure_stream(channels, beacon=True)

	## Convert the counts to umol per m^2s using the sensor's constants (SENSOR, above).
	for ch in ["red", "blue", "green"]:
		ch_obj = scope[ch]
		wavelength = scope[ch].params["lambda_nm"]
		stream = exp.mstreams[ch]
		stream.df["pfd"] = stream.df["counts"].apply(convert_pfd, lambda_nm=wavelength, colour=ch)

		## Because volts is a list (planned for multichannel calibrations)
		stream.df["volts"] = stream.df["volts"].apply(lambda vlist: vlist[0])

		## Fitting. Saturated readings are at the sensor's ceiling, not the light level: left out.
		unsaturated = ~stream.df["saturated"].astype(bool)
		print(f"{ch}: {int((~unsaturated).sum())} saturated readings left out of the fit")
		coefficients, cov_matrix = np.polyfit(stream.df["volts"][unsaturated].to_numpy(dtype=float),
		                                      stream.df["pfd"][unsaturated].to_numpy(dtype=float), 1, cov=True)
		slope = coefficients[0]
		intercept = coefficients[1]

		ch_obj.params["calib_cov_matrix"] = cov_matrix
		ch_obj.params["calib_slope"] = slope
		ch_obj.params["calib_intercept"] = intercept
		ch_obj.params["calib_sensor_gain"] = SENSOR["gain"]
		ch_obj.params["calib_sensor"] = sensor                          ## what the light meter reported
		ch_obj.params["calib_constants"] = {**SENSOR, "Re_effective": SENSOR["Re_640nm"] * SENSOR["colour_factors"][ch]}
		ch_obj.params["calib_eid"] = exp.eid
		ch_obj.params["calib_exp_dir"] = exp.exp_dir
		ch_obj.params["calib_volts"] = stream.df["volts"].to_list()
		ch_obj.params["calib_pfd"] = stream.df["pfd"].to_list()
		ch_obj.params["calib_counts"] = stream.df["counts"].to_list()
		ch_obj.params["calib_dt"] = datetime.datetime.now()


		print(f"Calibration done for channel: {ch}")
		print(ch_obj.params)

def generate_single_point_calibration_report(exp):
	global scope
	import matplotlib.pyplot as plt

	fig, ax = plt.subplots(figsize=(12,4))
	ax.set_ylabel("PFD (umol/m2/s)")
	ax.set_xlabel("Control Voltage(V)")
	ax.set_title("Illumination source:: control volt vs intensity (PFD) calibration plot")
	for ch in ['red', 'green', 'blue']:
		ch_obj = scope[ch]
		ax.plot(ch_obj.params["calib_volts"], ch_obj.params["calib_pfd"], ".-", color=ch, label=ch)
		ax.plot(ch_obj.params["calib_volts"], ch_obj.params["calib_pfd"], "-", color=ch, label=f'PFD={ch_obj.params["calib_slope"]:.3f}V + {ch_obj.params["calib_intercept"]:.3f}')
	plt.legend()
	plotpng = "control_volt_vs_intensity_calibration_plot.png"
	fig.savefig(plotpng)
	#exp.add_image(plotpng, caption="Light calibration plots. PFD is photon flux density in units of umol per square meter per second.")
	#exp.generate_report()
	return fig, ax



