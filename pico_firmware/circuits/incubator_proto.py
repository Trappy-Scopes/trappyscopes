# LCD-Vcc is connected to the USB bus - 5V.
 # LCD-GND is connected to GND pin B8.

### Pin assignments
pins = {
        "buzzer" : 2,
        "lcd" : {"din":  11, "clk":10, "cs":9, "dc":12, "rst":13},
        "lm1" : 0,    						## DC connections need to be aditionally grounded to the board -> DC1- to LM1-GND.
        "rtc" : {"scl":17, "sda":16}}



from pico_firmware.beacon import Beacon
beacon = Beacon(pins["buzzer"])
beacon.pulse(3)
buzzer = beacon
status = beacon.devicestatus


## Define light resources ---------------------------------------------------

#from pico_firmware.peripherals.lcd import LCD_0inch96
#lcd = LCD_0inch96(pins["lcd"])
#lcd.intro_seq()


## Define two light matrices
from pico_firmware.actuators.lightmatrix import LightMatrix
lm1 = LightMatrix(pins["lm1"], size=[11,8])

## Define circadian cycler
from pico_firmware.controllers.circadian_cycle_controller import CircadianScheduler
cs1 = CircadianScheduler(lm1, day_start=[8,0], night_start=[20,0])
cs1.set_timers(mode="short")

## Both of them need to be turned on -----------------------------------------








## Init extra rtc
from machine import RTC
#rtc2 = RTC_PCF85063TP(scl=pins["rtc"]["scl"], sda=pins["rtc"]["sda"])
#global rtc
#rtc = RTC()
#def rtc2_write():
#    now = rtc.datetime()
#    rtc2.write(now)
#    print(f"Updated RTC2: {now}")
    

    






"""
To be added later.
lcd.rect(0,0, 80,50, lcd.RED, True)
lcd.update()
lcd.display()
lcd.rect(0,0, 50,80, lcd.RED, True)
lcd.display()
lcd.update()
lcd.rect(50,0, 50,80, lcd.GREEN, True)
lcd.display()
lcd.rect(100,0, 50,80, lcd.WHITE, True)
lcd.display()
"""
