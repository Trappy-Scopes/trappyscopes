## !!! Changes sync globally across all devices
## !!! Do not block the REPL for long

"""
Stand main executable for all standard pico devices.
"""


import os
from machine import Pin, PWM
from time import sleep


## 0. Print welcome message
print("Executing default main.py: pico_firmware/main.py")

### 1. Verify required files -----------------------------
### Construct boot and webrepl config
if "boot.py" not in os.listdir("/"):
    print("pico_firmware/main.py : Emitting: boot.py")
    with open("boot.py", "w") as f:
        f.write("import webrepl\nwebrepl.start()\n") 

if "webrepl_cfg.py" not in os.listdir("/"):
    print("pico_firmware/main.py : Emitting: webrepl_cfg.py")
    with open("webrepl_cfg.py", "w") as f:
        f.write("PASS = \'trappy_cr\'\n")
        
        
board_str = \
"""# TRAPPY-SCOPES: BOARD CONFIGURATION ###
name = \"picodev\"
circuit_id = \"idle_device_that_blinks\"
flag_wifi_connect = True
flag_wifi_autoreset = True
flag_dt_sync = True
deice_status_str = \"device_clueless\"
"""

if "board.py" not in os.listdir("/"):
    print("pico_firmware/main.py: Emitting: board.py")
    with open("board.py", "w") as f:
        f.write(board_str)
        
if "vault" not in os.listdir("/"):
        print("pico_firmware/main.py: Emitting: vault directory.")
        os.mkdir("vault")


### -----------------------------------------------------
import board
import pico_firmware.pinassignments as pins
from pico_firmware.handshake import Handshake

### 2. processor-2 instruction execution-----------------
import _thread
#from pico_firmware.processor2 import processor2
#processor2_thread = _thread.start_new_thread(processor2, ())      
# -------------------------------------------------------        

### 3. Common Resources ---------------------------------
#from sensor import Sensor
#sensors = Sensor()
#--------------------------------------------------------

## 4. Device Initalisation ------------------------------

# cid : 0
if board.circuit_id == "idle_device_that_blinks":
    print("pico_firmware/main.py : Device initalised as : idle_device_that_blinks")
    led = Pin("LED", Pin.OUT)
    i = 0
    while i < 10:
        led.toggle()
        sleep(0.5)
        i = i + 1


# cid : 2   
if board.circuit_id == "4_clustcontrol_v1_proto":
    from pico_firmware.beacon import Beacon
    global buzzer
    buzzer = Beacon(pins.buzzer)
    
    from pico_firmware.controllers.rpicontroller import RPiController
    rpi1 = RPiController(pins.rpictrl[1]["RUN"], pins.rpictrl[1]["GLOBAL_EN"])
    rpi2 = RPiController(pins.rpictrl[2]["RUN"], pins.rpictrl[2]["GLOBAL_EN"])
    rpi3 = RPiController(pins.rpictrl[3]["RUN"], pins.rpictrl[3]["GLOBAL_EN"])
    rpi4 = RPiController(pins.rpictrl[4]["RUN"], pins.rpictrl[4]["GLOBAL_EN"])
    rpiset = {}
    rpiset[1] = rpi1; rpiset[2] = rpi2; rpiset[3] = rpi3; rpiset[4] = rpi4
    RPiController.buzzer = buzzer
    
    from pico_firmware.sensors.tandhsensor import TandHSensor
    tandh = TandHSensor(pins.sensors["tandh"], "dh11")
    
# cid : 3
if board.circuit_id == "2ch_peristat_kitroniks_vx_shield":
    print("main.py : Device initalised as : 2ch_peristat_kitroniks_vx_shield")
    ## Motor object
    from pico_firmware.actuators.dcmotor import DCMotor
    motor1 = DCMotor(pins.m1_fwdpin, pins.m1_revpin)
    motor2 = DCMotor(pins.m2_fwdpin, pins.m2_revpin)
    ## TODO motor 2
    #motor.set_speed_controller(pin.potentiometer)
    motor = motor1
    motorset = [motor1, motor2]

   
if board.circuit_id == "4ch_peristatpump_v1_proto":
    pass


elif f"{board.circuit_id}.py" in os.listdir("pico_firmware/circuits"):
    try:
        execfile(f"pico_firmware/circuits/{board.circuit_id}.py")
        print(f"main.py : Device initalised as : {board.circuit_id}")
    except Exception as e:
        print(f"main.py: Device init failed! ::: {board.circuit_id}")
        print(e)

else:
    print(f"Undefined circuit! :: {board.circuit_id}")
    

#---------------------------------------------------------




