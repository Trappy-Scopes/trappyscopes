import time
import datetime


description = \
"""
We trap a few cells (visually trackale amount) in 2mm traps and acclamatise them in red light for 10 mins.

## Operations

i.   Light for trapping: (red + small amount of green light for better visibility) + no recording.
ii.  Light for acclimatisation : red - 3.0V : record 30 seconds at the end of the period.
iii. Light for sticking : white light (3,3,3) : record for 10 minutes.

## Schematics

Trap -(Cell-set1)-> Acclimatise --> Adhere --> Acclimatise(n <= 3) --> Adhere --> Acclimatise(n <= 3) -> ...
								|
							  Flush
							  	|
							  Trap -(Cell-set2)->  Acclimatise --> Adhere --> Acclimatise(n <= 3) --> ...


## Schematics of measurement

∆t = 10seconds
Ns -> number of swimming cells


Trap(emit new MeasurementStream) :---: CellSeti -@-> t=(0+∆t)      : Ns=x1
											:	-@-> t=(5mins+∆t)  : Ns=x2
											:	-@-> t=(10mins+∆t) : Ns=x2
													  ...

## List of functions

0. name()-------------> defines the video filenames.
1. preview()----------> operations(i)
2. acclimatise()------> operations(2)
3. adhere()-----------> operations(3)
4. trapcellset()------> Indicates that its a different group of cells. It changes the name() function closure.
5. flush()------------> Creates an `ExpEvent.type = user_action` to indicate that the device was successfully flushed. Resets the `accl_cntr` variable.
"""								


dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
exp = Experiment(f"{scopeid}_{dt}_{time_str}_cell_stickyness_assay", append_eid=True)
exp.attribs["description"] = description
exp.attribs.update({"setup" : ["adherence_test", "cells"],
				    "res":[1920, 1080],
				    "fps": 20,
				    "magnification": 1.75,
				    "again":3,
				    "exposure_time_us":50000,				    
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "digital_gain":1,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,
				    "queue"      : False,

				    "quality" : 95,
				    "compress_level": 0,
				   })


## Measurement stream
global ms
ms = None

## Vars
global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min
cellset = 0
setitr = 0
accl_cntr = 0
accl_time_min = 10
addh_time_min = 30
sampling_duration_min = 5


### 0
def name(mode):
	"""
	Valid modes = acclamtise, adhere.
	"""
	global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min
	name_ = f"cellset{cellset}_trial{setitr}_acclmtime_{accl_cntr*accl_time_min}mins_{mode}.h264"
	return exp.newfile(name_)

## 1
@ScopeAssembly.changestatus("busy", "standby")
def preview(tsec=30):
	"""
	Preview: no camera configuration: lights: (1, 0.2, 0)
	"""
	scope.lit.setVs(1, 0.2, 0)
	print("Preview mode!")

	## Free float configuration
	cam.open()
	cam.preview(tsec)
	cam.close()

## 2
@ScopeAssembly.changestatus("busy", "standby")
def acclimatise():
	"""
	Acclamatisation functions: camera configured for red. lights: (3,0,0)
	"""
	global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min, ms
	scope.lit.setVs(2.8, 0, 0)
	#exp.delay(name("acclamatise"), accl_time_min*60)

	cam.close()
	cam.open()
	__configure_red__()

	cam.capture(vid_noprev, name("acclamatise"), tsec=30)
	cam.close()

	## Emit all measuremnts
	for i in range(int(addh_time_min/sampling_duration_min)+1):
		## Create measurements
		m = ms(accl_clock_s=((accl_cntr*accl_time_min) + i*sampling_duration_min)*60, adh_clock_s=0, 
			   accl_cntr=accl_cntr, phase="acclimatise", acq=name("acclamatise"), lit=[3,0,0], Ns=0)
	
	## Advance counter
	accl_cntr = accl_cntr+1


## 3
@ScopeAssembly.changestatus("busy", "standby")
def adhere():
	"""
	Adherence function: no camera configuration for red. lights: (3,3,3)
	"""
	global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min, ms
	scope.lit.setVs(3,3,3)

	cam.close()
	cam.open()
	cam.capture(vid_noprev, name("adhere"), tsec=30) ##TODO : Check if you can see the cells and then change it to addh_time_min.
	cam.close()


	## Emit all measuremnts
	for i in range(int(addh_time_min/sampling_duration_min)+1):
		## Create measurements
		m = ms(accl_clock_s=accl_cntr*accl_time_min*60, adh_clock_s=sampling_duration_min*i*60, 
			   accl_cntr=accl_cntr, phase="adhere", acq=name("adhere"), lit=[3,3,3], Ns=0)

	## Adherance does not advance

## 4
def trapcellset():
	"""
	Indicate that a cell is trapped by emitting an event.
	"""
	global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min, ms
	exp.log("Cells trapped", attribs={"type": "user_action_trap", "cellset": cellset})
	cellset = cellset + 1

	exp.start_timer() # Reset experiment timer
	ms = exp.new_measurementstream(f"cellset_{cellset}", monitors=["accl_clock_s", "adh_clock_s", "accl_cntr", "phase", "acq", "lit"], measurements=["Ns"])
	exp.__save__()

## 5
def flush():
	"""
	Indicate that the past number of cells were flushed.
	"""
	global cellset, setitr, accl_cntr, sampling_duration_min, accl_time_min, addh_time_min
	exp.log("Cells flushed", attribs={"type": "user_action_flush", "cellset": cellset})
	accl_cntr = 0
	exp.__save__()


def __configure_red__():
	def configure_camera():
		## Set Camera settings:

		cam.cam.create_video_configuration({"size":exp.attribs["res"]})
		cam.cam.video_configuration.controls.ExposureTime = exp.attribs["exposure_time_us"]
		cam.cam.video_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
		cam.cam.video_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
		cam.cam.video_configuration.controls.AnalogueGain = exp.attribs["again"]
		cam.cam.video_configuration.controls.Brightness   = exp.attribs["brightness"]
		cam.cam.video_configuration.controls.Contrast     = exp.attribs["contrast"]
		cam.cam.video_configuration.controls.ColourGains  = exp.attribs["colour_gains"]
		cam.cam.video_configuration.controls.Sharpness    = exp.attribs["sharpness"]
		cam.cam.video_configuration.controls.Saturation   = exp.attribs["saturation"]

		cam.cam.video_configuration.size  = (res[0], res[1])
		cam.cam.video_configuration.queue  = exp.attribs["queue"]
		cam.cam.video_configuration.buffer_count  = 6


		### Set compression and quality
		cam.cam.options["quality"] = exp.attribs["quality"]
		cam.cam.options["compress_level"] = exp.attribs["compress_level"]


		## Print -> set configuration
		read_config =  safepicam2_config(cam.cam.video_configuration)
		print(read_config)
