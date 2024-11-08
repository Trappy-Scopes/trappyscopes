from rp2 import PIO, StateMachine, asm_pio
from machine import Pin
import time

class Beacon:
    current = None
    smlog = [-1]
    
    @asm_pio(set_init=PIO.OUT_LOW)
    def __off__():
        set(pins, 0)

    @asm_pio(set_init=PIO.OUT_LOW)
    def __on__():
        set(pins, 1)
        
    @asm_pio(set_init=PIO.OUT_LOW)
    def __pulse__():
        label("loop")
        push()
        mov(isr, y)
        
        set(pins, 1)
        nop()     [31]
        nop()     [31]
        nop()     [31]
        nop()     [31]
        nop()     [31]
        set(pins, 0)
        
        jmp(y_dec, "loop")

    
    def __init__(self, pin_no):
        self.pin_no = pin_no
        self.pin = Pin(pin_no)
        self.sm1 = None
        self.sm2 = None
        self.pin.value(False)
        
        sm_id = Beacon.smlog[-1] + 1
        self.off_fn = StateMachine(sm_id, Beacon.__off__, freq=10001, set_base=self.pin)
        print(self.off_fn)
        self.on_fn = StateMachine(sm_id+1, Beacon.__on__, freq=10000, set_base=self.pin)
        print(self.on_fn)
        Beacon.smlog.append(sm_id)
        Beacon.smlog.append(sm_id+1)
        Beacon.current = self
        
        
    def blink(self):
        self.off_fn.active(1)
        self.on_fn.active(1)

    def on(self):
        self.off_fn.active(0)
        self.on_fn.active(1)

    def off(self):
        self.off_fn.active(1)
        self.on_fn.active(0)
        
    def pulse(self, no):
        #self.on_fn = StateMachine(1, Beacon.__pulse__, freq=10000, set_base=self.pin)
        #self.on_fn.put(hex(no))
        for _ in range(no):
            self.on()
            time.sleep(0.25)
            self.off()
            time.sleep(0.25)
            

    def devicestatus(self, status):
        if status ==  "standby":
            self.on()
            return True
        elif status == "off":
            self.off()
            return True
        elif status == "busy":
            self.blink()
            return True
        else:
            return False

        