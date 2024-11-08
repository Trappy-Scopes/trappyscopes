from machine import Pin
import time


class RPiController:
    buzzer = None
    
    def buzz(func, *args, **kwargs):
        def wrapper( *args, **kwargs):
            if RPiController.buzzer != None:
                RPiController.buzzer.pulse(1)
            ret = func( *args, **kwargs)
            return ret
        return wrapper
    
    def __init__(self,  run_pin, gl_en_pin):

        self.pins = {"run": run_pin, "gl_en":gl_en_pin}
        self.run_pin = Pin(run_pin, Pin.IN)
        self.gl_en_pin = Pin(self.pins["run"], Pin.IN) ## For high impedence
        self.buzzer = None
        
    def is_booted(self):
        return  self.run_pin.value()

    @buzz
    def boot(self):
        if self.run_pin.value() == 0:
            self.__pulse_gl_en__()

    @buzz
    def shutdown(self):
        ### --> initiate softwre shutdown
        if self.run_pin.value() == 1:
            self.gl_en_pin = Pin(self.pins["run"], Pin.OUT, value=0)
            self.gl_en_pin.value(0)
    @buzz
    def reboot(self):
        ### Recheck logic
        if self.run_pin.value() == 0:
            self.__pulse_gl_en__()
        
        time.sleep(1)

        if self.run_pin.value() == 0:
            self.__pulse_gl_en__()
        else:
            print("Power-up failed!")
            return False


    def __pulse_gl_en__(self):
        self.gl_en_pin = Pin(self.pins["run"], Pin.OUT, value=0)
        self.gl_en_pin.value(0)
        time.sleep(0.5)
        self.gl_en_pin.value(1)

        ### Set to high Z input mode
        self.gl_en_pin = Pin(self.pins["run"], Pin.IN)

