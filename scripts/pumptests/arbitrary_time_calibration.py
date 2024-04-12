import datetime
from time import sleep
import time
from experiment import Calibration
from rich import print
from rich.markdown import Markdown


# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())

exp = Calibration(f"{scopeid}_motor_calib_arbitrary_time_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}", append_eid=True)
exp.delay("Start delay", 5)



## Go through different speeds

#speedset = [0.05, 0.10, 0.15, 0.2, 0.25, 0.3, 0.5, 0.75, 0.8, 0.95]
#speedset = [0.99, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09]

## extensive
fill_mL = 20
freq = 10
speedset = [0.027, 0.028, 0.029, 0.030, 0.031, 0.032, 0.033, 0.034, 0.035, 0.036, 0.037, \
			0.038, 0.040, 0.050, 0.070, 0.090, 0.100, 0.120, 0.150, 0.170, 0.190, 0.210, 0.250]
exp.logs["speed_set"] = speedset
exp.logs["pwm_freq"] = freq
exp.logs["speedset"] = speedset
exp.logs["lit"] = "arbitrary"
exp.logs["results"] = {}
### Get a motor
motor_id = "motor2"
motor = scope[motor_id]
print(motor)
exp.logs["motor"] = motor_id

### Pico decision
motor_pico = pico


### Set motor properties
motor.fwdpin.freq(freq)
motor.revpin.freq(freq)
print(f"Fwd pin freq: {motor_pico(f'print({motor_id}.fwdpin.freq())')}")

print(f"Speeds: {speedset}")
print(f"Will test {len(speedset)} speeds!")



from fluidicsdevice import FluidicsDevice
trap = FluidicsDevice("2mm-inhouse", dia_mm=2, id_="37b8b8c592")
exp.logs["fluidicsdevice"] = trap

for i, speed in enumerate(speedset):
	

	break_ = False
	mcnt = 0
	result = {"success": True}
	
	def end_cycle(prompt):
		if prompt == "end":
			break_ = True
			result["end"] : exp.timer_elapsed()
			return True
	def mark_fail(prompt):
		if prompt == "fail":
			result["success"] = False
			return True
	def measure(prompt):
		if isinstance(prompt, float):
			result.extend({"duration_s": exp.timer_elapsed(), "mL": prompt})
			return True
	def tell_time(prompt):
		if prompt == "time":
			print("Elapsed time: ", exp.timer_elapsed(), s)
			return True


	print(f"Motor speed: {speed}")
	exp.user_prompt("start")

	start = exp.start_timer()
	motor.speed(speed)

	### Internal loop
	while not break_:

		prompt = exp.multiprompt([end_cycle, mark_fail, tell_time, measure], labels=["end", "fail", "time", "<mL : float>"])
	
	
	motor.hold()
	stop = time.perf_counter()
	dur = stop-start

	### Fix this
	result_ = {"duty":(pico(f"print({motor_id}.duty)").rstrip("\r\n")), "motor_id": motor_id,
				  "speed": speed, "freq":freq,  "duration":dur, "mL":fill_mL,
				  "setup": "syringe_to_syringe", "overflow": 0, "fluidics": trap.__getstate__(),
				  "experiment_type": "duty_perturbation"}
	result.extend(result_)
	
	print(Markdown("#Result"), result)

	exp.logs["results"].append()
	exp.__save__()

	

	
motor.hold()
exp.close()