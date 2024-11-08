from machine import Pin
from time import sleep

class Buzzer(Pin):
    

    def buzz(self, count=0, fcount=0):        
        if not count and not fcount:
            count = 1
        
        if count:   
            for _ in range(count):
                self.on()
                sleep(0.75)
                self.off()
                sleep(0.2)
        if fcount:
            for _ in range(fcount):
                self.on()
                sleep(0.2)
                self.off()
                sleep(0.1)    
        
    def buzzlong(self, count=1):
        for _ in range(count):
            self.on()
            sleep(0.75)
            self.off()
            sleep(0.2)
    
    def buzzfast(self, count=1):
        for _ in range(count):
            self.on()
            sleep(0.2)
            self.off()
            sleep(0.1)
    def buzz_(self, t):
        self.buzzfast(count=1)
