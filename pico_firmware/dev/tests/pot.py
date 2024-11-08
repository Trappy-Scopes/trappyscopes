from machine import Pin, ADC
from time import sleep
pot = ADC(Pin(26))



for i in range(100):
    
    read = pot.read_u16()
    print(read)
    sleep(0.5)
