import threading
import schedule


class LifeTimeSampler(Machine):
	"""docstring for LifeTimeSampler"""
	def __init__(self, attribs):
		super(Machine, self).__init__()
		self.attribs = attribs
	
## Setup machine configuration
scope.machine = LifeTimeSampler(acq_time_min=5, acq_delay_min=55, tandh_speriod_min=5)
#scope.assert_device("actuators", "light")
#scope.assert_device("actuators", "pump")


if exp.state.setup:

	## Job 1 - record temperature and humidity every few minutes------------------
	exp.periodic(scope.sensors.tandh.log, tandh_speriod_min*60, mode="parallel")

	## ----------------------------------------------------------------------------




	## Job 2 - Keep a control prompt always running --------------------------------
	class Handler:
		break_ = False
		result = {"success": False}
		def pump_flow(prompt):
			if isinstance(prompt, float) or isinstance(prompt, int):
				exp.measurement({"fill_duration_s": exp.timer_elapsed(), 
								 "mL": prompt, "success": True})
				return True
		def tell_time(prompt):
				if prompt == "time":
					print("Elapsed time: ", exp.timer_elapsed(), "s")
					return True
		def end(prompt):
			if prompt == "end":
				Handler.break_ = True
				Handler.result["end"] : exp.timer_elapsed()
				schedule.clear()
		def pulse_pump(prompt):
			if prompt == "start-pump":
				def pulse_callback():
					scope.actuators.pump.speed(0.035)
					time.sleep(2)
					scope.actuators.pump.hold()
				exp.schedule.every(1).hour()

	
	def promptfn():
		while not Handler.break_:
			exp.multiprompt([Handler.pump_flow, Handler.tell_time, 
							 Handler.end, Handler.pulse_pump],
					   		labels=["<record-flow-mL>", "time", 
					   				 "end", "start-pump"])


	
	prompt = threading.Thread(name=prompt, target=promptfn())

	## --------------------------------------------------------------------------------


	## Job 3  Acquisitions  -----------------------------------------------------------
	def acq_fn():
		dt = str(datetime.date.today()).replace("-", "_")
		t = time.localtime(time.time())
		cam.acquire(exp.newfile(f"{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}"))
		exp.delay("Acquisition waiting time", 55*60)
	exp.schedule.every(1).hours.do(acq_fn)


	## --------------------------------------------------------------------------------

if exp.state.run:
	exp.schedule.run_all()
	prompt.start()
