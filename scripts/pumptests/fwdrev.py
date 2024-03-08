import datetime
from experiment import Test
import numpy as np
import time

# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Test(f"{scopeid}_fwd_rev_test_{dt}")
test = exp


### Optional ------------------------
## Incase of additional pico board
#motor_pico = RPiPicoDevice(connect=False)
#motor_pico = NullRPiPicoDevice(connect=False)
#motor_pico.auto_connect()
#motor_pico.connect("/dev/ttyACM0")
#motor_pico.exec_main()
#print(motor_pico)
### ---------------------------------

##OR
motor_pico = pico


speed = 0.4
## Test opening and closing of camera
for i in range(15):
	motor_pico(f"motor.fwd(speed={speed})")
	sleep(1)
	motor_pico(f"motor.rev(speed={speed})")
	sleep(1)
motor_pico("motor.hold()")
test.close()