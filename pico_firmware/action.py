# Inspired by: https://gist.github.com/jedie/8564e62b0b8349ff9051d7c5a1312ed7
from machine import Pin
import utime



class Action:
    def __init__(self, pin, callback, trigger=Pin.IRQ_FALLING, debounce_ms=300):
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.pin = pin
        self.block = False
        
        self._next_call = utime.ticks_ms() + self.debounce_ms

        self.pin.irq(trigger=trigger, handler=self.debounce_handler)

    def __call__(self, pin):
        self.callback(pin)

    def debounce_handler(self, pin):
        if utime.ticks_ms() > self._next_call and not self.block:
            self._next_call = utime.ticks_ms() + self.debounce_ms
            self.__call__(pin)
        #else:
        #    print("debounce: %s" % (self._next_call - time.ticks_ms()))
    

if __name__ == "__main__":
    print("No tests for Action.")
