pins = {"relay" : 14,
        "buzzer" : 20,
        "lightmatrix" : 0, 

        #mosfet : 27
        "tanh1" : 14,
        "tanh2" : 27,

        "sw1" : 15,
        "sw2" : 17,
    }
from pico_firmware.actuators.lightmatrix import LightMatrix
global lm
lm = LightMatrix(pins["lightmatrix"], size=[7,3])

from machine import Pin
import time
global sw1, sw2
sw1 = Pin(pins["sw1"], Pin.IN)
sw2 = Pin(pins["sw2"], Pin.IN)


from pico_firmware.beacon import Beacon
global buzzer
buzzer = Beacon(pins["buzzer"])

from machine import Timer
global states
states = [[255,0,0], [0,255,0], [0,0,255], [255,255,255]]
global i
i = 0

global toggle
def toggle():
    """
    Toggle light states.
    """
    global lm
    global i
    lm.fill(states[i])
    i = i + 1
    if i == 4:
        i = 0

global off
def off():
    """
    Turn off the light matrix.
    """
    global lm
    lm.fill([0,0,0])
    
def button_press(timer):
    global toggle
    global off
    global buzzer
    if sw1.value() == 1:
        toggle()
        buzzer.pulse(1)
    if sw2.value() == 1:
        off()
        buzzer.pulse(1)
    
### Set timers
timer = Timer(period=int(1000*0.25), mode=Timer.PERIODIC, callback=button_press)
buzzer.pulse(3)
    
    

