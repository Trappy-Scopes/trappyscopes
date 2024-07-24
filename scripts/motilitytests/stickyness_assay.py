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

## List of functions

0. name()  --> defines the video filenames.
1. preview() -> operations(i)
2. acclimatise() -> operations(2)
3. adhere()  --> operations(3)
4. trap()    --> Indicates that its a different group of cells. It changes the name() function closure.
5. flush()   --> Creates an `ExpEvent.type = user_action` to indicate that the device was successfully flushed. Resets the `accl_cntr` variable.
"""								


dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
time_str = f"{t.tm_hour}hh_{t.tm_min}mm"
exp = Experiment(f"{scopeid}_{dt}_{time_str}_cell_stickyness_assay", append_eid=True)



## Vars
global cellset, setitr, accl_cntr
cellset = 0
setitr = 0
accl_cntr = 0
accl_time_min = 10
addh_time_min = 30

### 0
def name(mode):
	"""
	Valid modes = acclamtise, adhere.
	"""
	name_ = f"cellset{cellset}_trial{setitr}_acclmtime_{accl_cntr*accl_time_min}mins_{mode}.h264"
	return exp.newfile(name_)

## 1
def preview(tsec=30):
	scope.lit.setVs(1, 0.2, 0)
	print("Preview mode!")

	## Free float configuration
	cam.open()
	cam.preview(tsec)
	cam.close()

## 2
def acclimatise():
	scope.lit.setVs(3, 0, 0)
	exp.delay(name("acclamatise"), accl_time_min*60)
	accl_cntr = accl_cntr+1

	cam.open()
	#configure("red")
	cam.acquire(vid_noprev, name("acclamatise"), tsec=30)
	cam.close()



## 3
def adhere():
	scope.lit.setVs(3,3,3)

	cam.open()
	cam.acquire(vid_noprev, name("adhere"), tsec=30) ##TODO : Check if you can see the cells and then change it to addh_time_min.
	cam.close()

## 4
def trap():
	global cellset
	exp.log("Cells trapped", attribs={"type": "user_action_trap", "cellset": cellset})
	cellset = cellset + 1
	exp.__save__()

## 5
def flush():
	global accl_cntr
	exp.log("Cells flushed", attribs={"type": "user_action_flush", "cellset": cellset})
	accl_cntr = 0
	exp.__save__()



