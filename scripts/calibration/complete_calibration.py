from datetime import timedelta
import datetime
import time
from rich import print
import ast
from rich.panel import Panel
from rich.pretty import Pretty

from expframework.experiment import Experiment
import schedule

from scripts.alignmenttools import framealignment
from scripts.calibration import control_volt_vs_sample_intensity

__description__ = \
"""
Carry out a series of alignments in series: "alignment", "beads", "usaf", "light".

When alignment is done we also have an image for bead analysis.
"""

def do_complete_calibration():
	## Create a calibration context
	global exp, scope
	exp = Experiment.Construct(["calibrations", "alignment", "beads", "usaf", "light"])
	scope.beacon.on()

	print("do_alignment() : Alignment process.")
	print("do_usaf_image() : Take image of USAF test target.")
	print("do_light_calibration() : Perform light calibration.")


def do_alignment():
	global scope
	framealignment.take_calib_image()
	calib_image = framealignment.load_calib_image()
	framealignment.start_alignment()
	framealignment.view_all()



def do_usaf_image():
	global scope
	scope.cam.read("img", "usaf_tt.png", tsec=3, show_preview=False)


def do_light_calibration():
	global exp, scope
	exp.params["volt_limits"] = {"red":[0, 3], "green":[0,3], "blue":[0,3]}
	exp.params["step_size"] = 0.1
	exp.params["measurements"] = [["red"], ["green"], ["blue"]]
	exp.params["stabilization_delay_s"] = 1

	control_volt_vs_sample_intensity.single_channel_calibration()
	control_volt_vs_sample_intensity.generate_single_point_calibration_report(exp)

