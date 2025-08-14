import datetime
import time
from rich import print
from rich.panel import Panel
from rich.markdown import Markdown


from expframework.experiment import Experiment

print(Panel(Markdown(
"""Use `new_count(<strain>)` to start a new count (as a measurement stream.
Shorthand `strain[strainid]` can be used to access measurement streams."""), 
title="Cell counting utilities"))


## Define shorthand
strain = Experiment.current.mstreams



## Functions are defined

def new_count(strain):
	"""
	Create a new measurement stream based on the strain-id. The strain must be a unique identifier.
	"""
	pass

def fit_curve(strains):
	"""
	Fit and plot growth-curve data from a particular strain, or a list of strains
	"""
	pass


def measure_size(strain, no_fovs):
	"""
	Click `no_fovs` and use cell-segmentation to analyse the size of the cells based on area.
	For this to work, magnification must be properly calibrated.
	"""
	pass



def take_count():
	global exp
	