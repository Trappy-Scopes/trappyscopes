"""
Processor 2 standard operations
"""

from pico_firmware.dtsync import DTSync
import board
from pico_firmware.logging import Logger

import urequests
from machine import Pin
import gc
import math
import time
import webrepl
import board

def processor2():
    p2_init_time = time.ticks_ms()
    log = Logger("processor2")
    
    ### Parameters
    machine_auto_reset_hours = 24
    tick_duration_ms = 500
    wifi_reconn_counter = 0
    
    ## Resource Setup
    onboardled = Pin('LED', mode=Pin.OUT)
    onboardled.on()
    
    global buzzer, Wifi, rtc, processor2_stop
    processor2_stop = False
    
    
    
    ## Establish Wifi connection
    from pico_firmware.wifi import Wifi
    import pico_firmware.secrets as secrets
    if board.flag_wifi_connect:
        Wifi.connect(secrets)
        if Wifi.connected:
            print(wifi.info())
            DTSync.sync(True)
            webrepl.start()
            
    
    ######## ----------- Device Poll -----------------------
    while not processor2_stop:
        
        ## 0. Start time-keeping
        start_time = time.ticks_ms()
        
        
        
        # 1. LED Blink ---------
        if board.flag_wifi_connect:
            if not Wifi.connected:
                onboardled.on()
            else:
                onboardled.toggle()
            
        ### 2. Attempt Wifi Reconnection
        if board.flag_wifi_connect:
            if not wifi.connected:
                wifi_reconn_counter = wifi_reconn_counter + 1
                print(f"Processor2: Wifi reconnection counter: {counter}.")
                Wifi.connect(secrets)
            
                if Wifi.connected:
                    log.info(f"Processor2, wifi connected: {Wifi.info()}.")
                    webrepl.start()
                    wifi_reconn_counter = 0
                elif board.flag_wifi_reset:
                    if wifi_reconn_counter == 5: # Reset Device - if counter exceeds 5.
                        log.error("Processor2, Unable to connect to wifi. Auto-reseting device.")
                        onboardled.on()
                        sleep(2)
                        machine.reset()
        
        ###3 Date Time Synchronisation Callback
        if board.flag_dt_sync:
            try:
                DTSync.sync(True)
                DTSync.emit_checkpoint()
            except:
              log.error(f"Processor2, ntp request failed.") 

        ###4 Machine autoresets
        if board.flag_auto_machine_reset:
            if time.ticks_ms() - p2_init_time > ( 3600000 * machine_auto_reset_hours):
                log.info("Processor2, scheduled machine reset.")
                onboardled.on()
                sleep(2)
                machine.reset()
        
        
              
        ###5 Garbage Collection
        gc.collect()
        ###
        
        ### Appropriate Tick dealy
        end_time = time.ticks_ms()
        if not end_time - start_time >= tick_duration_ms:
            time.sleep(tick_duration_ms - math.fabs(end_time - start_time))


