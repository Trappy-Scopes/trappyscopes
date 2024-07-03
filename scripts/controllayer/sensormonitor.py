# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Test(f"{scopeid}_test_cameraclosure_{dt}")
test = exp


for i in range(0, 300):
	
	## Change actuator state
	scope.actuators.motor.speed(0.01*i)

	## Actuator monitor
	val = pico.actuators.motor.speed()

	