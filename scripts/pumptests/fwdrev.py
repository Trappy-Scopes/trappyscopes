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


## Init flow
motor_pico(f"motor.fwd(speed={speed})")
sleep(7)
motor_pico("motor.hold()")


speed = 0.4
mode = "continuous" # "interrupted"
## Test opening and closing of camera
for i in range(15):
	if mode == "interrupted":
		motor_pico(f"motor.fwd(speed={speed})")
		sleep(2)
		motor_pico("motor.hold()")
		sleep(2)
		motor_pico(f"motor.rev(speed={speed})")
		sleep(2)
		motor_pico("motor.hold()")
		sleep(2)
	else:
		motor_pico(f"motor.fwd(speed={speed})")
		sleep(2)
		motor_pico(f"motor.rev(speed={speed})")
		sleep(2)
motor_pico("motor.hold()")
test.close()