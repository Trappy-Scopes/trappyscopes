import gc
from .mscope import MicroscopeType


## Setup machine configuration
scope.type = MicroscopeType(
				type="lifetime_sampler",
				duration_h=12,
				chunk_size_h=0.5, 
				tandh_speriod_min=5)


scope.assert_device("lit")
scope.assert_device("tandh")
scope.assert_device("cam")

## Crete experiment
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
tstr = f"{t.tm_hour}_{t.tm_min}"
exp = Experiment(f"{scopeid}_{dt}_{tstr}_lifetimemachine_{scope.type.duration_h}h", append_eid=True)




## Job 1 - record temperature and humidity every few minutes------------------
tandhstream = exp.new_measurementstream(measurements=["temp", "humidity"])
tandhsample = lambda: tandhstream(**scope.tandh.read())

## Start periodic task
exp.schedule.every(scope.type.tandh_speriod_min).minute.do(tandhsample)
## ----------------------------------------------------------------------------


## Job 2 - Keep a control prompt always running --------------------------------
class Handler:
	break_ = False
	result = {"success": False}
	def tell_time(prompt):
		if prompt == "time":
			print("Elapsed time: ", exp.timer_elapsed(), "s")
			return True
	def stop(prompt):
		if prompt == "end":
			Handler.break_ = True
			Handler.result["end"] : exp.timer_elapsed()
			cam.cam.stop_recording()
			exp.schedule.clear()
			prompt.exit()
def promptfn():
	while not Handler.break_:
		exp.multiprompt([Handler.tell_time, 
						 Handler.stop],
				   		labels=["time", "stop"])
		
prompt = threading.Thread(name=prompt, target=promptfn())
## --------------------------------------------------------------------------------


## Job 3  Acquisitions  -----------------------------------------------------------
no_chunks = scope.type.duration_h/scope.type.chunk_size_h
print(f"Number of video segments: {no_chunks}".)
print("Scope is ready. Use run_acq() to begin acquisition.")
scope.beacon.status("standby")
def run_acq():
	gc.collect()

	for chunk in range(no_chunks):
		gc.collect()
		scope.beacon.status("busy")
		filename = exp.newfile(f"{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}_chunk{chunk}.mjpeg", fullpath=False)
		#cam.close()
		#cam.open()
		#cam.configure()
		cam.capture("vid_noprev", filename, scope.type.chunk_size_h*3600)
	scope.beacon.status("standby")
	cam.close()
## --------------------------------------------------------------------------------


