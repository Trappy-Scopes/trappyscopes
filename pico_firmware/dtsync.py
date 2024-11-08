import ntptime
import os
import json

from pico_firmware.logging import getLogger
from machine import RTC, Timer
#from pico_firmware.wifi import Wifi


# Clock synchronisation ----------------------------------------------    T2   ||  Timer 0

log = getLogger("main")
rtc = RTC()
class DTSync:
    """
    Date and time synchronisation module.
    """
    
    timer = None
    
    def sync(timer):
        """
        Default sync function: tries NTP server, then loads the last checkpoint.
        """
        global rtc
        if Wifi.connected:
            log.info("DTSync.sync: Local time before synchronization：%s" %str(rtc.datetime()))
            try:
                ntptime.settime()
                now = list(rtc.datetime())
                now[4] = (now[4] + 1) %24 #UTC+1 Timezone correction
                rtc.datetime(now)
                log.info("DTSync.sync: Local time after NTP sync：%s" %str(rtc.datetime()))
            except:
                log.error("DTSync.sync: NTP request failed.")
            
        else:
            DTSync.set_checkpoint()
               
    def set_checkpoint():
        """
        Updates the RTC with the last checkpoint.
        """
        if DTSync.has_checkpoint():
            now = DTSync.get_checkpoint()
            rtc.datetime(now)
            log.info("DTSync.sync: Local time after checkpoint sync：%s" %str(rtc.datetime()))
        else:
            log.error("DTSync.sync: No time checkpoint found - sync request failed.")
    
    def has_checkpoint():
        """
        Returns true if a checkpoint exixts on the device.
        """
        return "dt_checkpoint" in os.listdir("//vault")
    
    def get_checkpoint():
        """
        Returns the parsed and cleaned last dt checkpoint.
        """
        time_str = open("//vault/dt_checkpoint", "r").read()
        parsed = json.loads(time_str)
        return parsed
    
    def emit_checkpoint():
        """
        Emits a datetime_checkpoint
        """
        now = rtc.datetime()
        with open("//vault/dt_checkpoint", "w") as f:
            f.write(json.dumps(now))
            
    def start_checkpointing():
        def callback(timer):
            DTSync.emit_checkpoint()
            print("DTSync: dt checkpoint emitted.")
        DTSync.timer = Timer(period=60000, mode=Timer.PERIODIC, callback=callback)
            