from machine import RTC
import os

class Logger:
    
    channels = ["out", "in", "err", "dtsync"]

    log = str()
    rtc = RTC()
    files = {key:None for key in channels}
    debug = True
    lcd_ = None
    __lcd_i__ = 1
    

    for file in channels:
        name = f"{file}.txt"
        
        # Check if file exists
        if name not in os.listdir():
            with open(name, "w") as f:
                pass 
       
        # Mount file
        files[file] = open(name, "a")
        
        
        files[file].write(f"{file}\n")
        files[file].flush()
        
    #def __get_item__(key):
    #   return Logger.files[key]
    
    def write(key, log):
        Logger.log = f"{key}, {Logger.rtc.datetime()}, {log}\n"
        Logger.files[key].write(Logger.log)
        Logger.files[key].flush()
        
        if Logger.debug:
            print(Logger.log)
    
    def __del__():
        for file in Logger.files:
            Logger.files[file].close()
    
    #def dump(key):
    #    return Logger.files[key].read()
    
    def lcd(text):
        if Logger.display:
            if Logger.__lcd_i__ % 3 == 1:
                Logger.display.top(f"{Logger.__lcd_i__}. {text}")
                Logger.__lcd_i__ += 1
                return
            elif Logger.__lcd_i__ % 3 == 2:
                Logger.display.middle(f"{Logger.__lcd_i__}. {text}")
                Logger.__lcd_i__ += 1
                return
            else:
                Logger.display.middle(f"{Logger.__lcd_i__}. {text}")
                Logger.__lcd_i__ += 1
                return