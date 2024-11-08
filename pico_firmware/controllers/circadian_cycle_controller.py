from machine import RTC, Timer
import math
from neopixel import NeoPixel

from pico_firmware._logger import Logger as Log

"""
TODO
----

1. Implement Finite Cycles
2. Possibility of having multiple schedules. Name based file assignments.
3. Status sheet for LCD display
"""

class CircadianScheduler:
    """
    Sets up Circadium Rhythm Scheduler.
    lightmatrix: Neopixel Array to control
    buzzer: used for auditary feedback on processes.
    """
    def __init__(self, lightmatrix, name=None, day_start=[8,0], night_start=[20,0],
                 lightmap={"day" :[255, 255, 255], "night" :[0, 0, 0]},
                    bomdia=None, bonnoite=None

                 ):
        
        self.name = name
        self.lightmatrix = lightmatrix
        ## Is a list now -> this means that multiple displays can be updated.
        self.partitions = []


        ## Assume infinite cycles or that the object has to be stopped.
        self.lightmap = lightmap
        self.day_start   = day_start   # hh, mm
        self.night_start = night_start # hh, mm
        
        if not bomdia:
            self.bomdia = lambda lightmatrix: lightmatrix.fill(self.lightmap["day"])
        else:
            self.bomdia = bomdia
        if not bonnoite:
            self.bonnoite = lambda lightmatrix: lightmatrix.fill(self.lightmap["night"])
        else:
            self.bonnoite = bonnoite

        self.rtc = RTC()
        self.timer = Timer()
        from pico_firmware.beacon import Beacon
        self.buzzer = Beacon.current
        
        self.is_active = True
        self.phase_map = {"day": 0, "night": 1}
        

        ## Status
        self.status = {"phase": "day", "active": True}

        
        
        # Bookeeping and Interrupt Usage
        self.last_day_callback = (0,0,0,0,0,0,0,0)
        self.last_night_callback = (0,0,0,0,0,0,0,0)
        
        ### If we assume that the incubator divides the y
        self.time_based(self.day_start, self.night_start)
          
    
    def time_based(self, day_start, night_start, cycles=0):
        """
        Set a time based Schedule.
        Input [hours, minute]s in 24 hour format.
        cycles = 0 : Run cycle forever.
        """
        self.last_day_callback = (0,0,0,0,0,0,0,0)
        self.last_night_callback = (0,0,0,0,0,0,0,0)
        
        #--------
        def str_to_time(string):
            # Format should be hh:mm
            if isinstance(string, list):
                return string
            
            
            string = string.strip(" ").split(",")
            time_ = [int(t) for t in string]
            return time_[:2]
        
        def is_valid_time(time):
            return (time[0] >= 0 and time[0] <= 23) and \
                   (time[1] >= 0 and time[1] <= 60)
        #--------

        day_start = str_to_time(day_start)
        night_start = str_to_time(night_start)
      
        if is_valid_time(day_start) and is_valid_time(night_start):
            self.day_start   = day_start
            self.night_start = night_start
            self.cycles      = cycles
            self.remaining_cycles = self.cycles
            if self.cycles == 0:
                self.remaining_cycles = 2000
            Log.write("out", f"Set Circadium Scheduler: {self.day_start}, {self.night_start}, {self.cycles}")
        else:
            Log.write("out", "Invalid time entry!")
            self.buzzer(count=10)
            return
          
        #with open("/vault/circadium.config") as file:
        #    file.write(f"{day_start}\n{night_start}\n{cycles}\n")
        #    self.is_active = True
            
        # Set the current state as per the time
        now = self.rtc.datetime()
        if self.phase_detect(now) == "day":
            Log.write("out", "Phase detection: day")
            self.__set_day__(now)
        elif self.phase_detect(now) == "night":
            Log.write("out", "Phase detection: night")
            self.__set_night__(now)
        else:
            Log.write("out", "Could not detect phase.")
    
    
    def set_from_config(self):
        """
        Sets time values from the circadium.config state file.
        """
        data = None
        with open("/vault/circadium.config") as file:
            data = file.read()
        data.rstrip("\n")
        
        lines = data.split("\n")
        lines = [line.lstrip("[").rstrip("]") for line in lines]
        self.time_based(lines[0], lines[1], cycles=int(lines[2]))
        

            

    def short_callback(self, timer):
        
        now = self.rtc.datetime()
        print("Scheduler Callback!")
        
        print(self.__minute_diff__(now, self.day_start))
        print(self.__minute_diff__(now, self.night_start))
        

        
        # Is it day?
        if math.fabs(self.__minute_diff__(now, self.day_start))*60 <= 30 and \
           math.fabs(self.__minute_diff__(now, self.last_day_callback)) > 5 and \
           self.is_active:
            # Bom Dia!
            self.__set_day__(now)
        
        
        # Is it night?
        if math.fabs(self.__minute_diff__(now, self.night_start))*60 <= 30 and \
           math.fabs(self.__minute_diff__(now, self.last_night_callback)) > 5 and \
           self.is_active:
            # Bon Noite!
            self.__set_night__(now)
        
        # Test for cycles
        if self.remaining_cycles == 0:
            self.is_active = False
        
            
                
            
    # ------------
    def __set_day__(self, now):    
        print("Bom Dia!")
        self.buzzer.pulse(5)
        
        self.bomdia(self.lightmatrix)

        self.lightmatrix.write()
        self.phase = "day"
        Log.write("out", f"Transitioning to day light conditions: {self.lightmap['day']}")
        self.last_day_callback = now
        self.remaining_cycles = float(self.remaining_cycles) - 0.5
        
    def __set_night__(self, now):
        #print("diff", self.__minute_diff__(now, self.last_night_callback))
        print("Boa Noite!")
        self.buzzer.pulse(5)
        
        self.bonnoite(self.lightmatrix)
        
        self.lightmatrix.write()
        self.phase = "night"
        Log.write("out", f"Transitioning to night light conditions: {self.lightmap['night']}")
        self.last_night_callback = now
        self.remaining_cycles = float(self.remaining_cycles) - 0.5
        
    def phase_detect(self, now):
        print(self.__minute_diff__(now, self.day_start))
        print(self.__minute_diff__(now, self.night_start))
        if self.__minute_diff__(self.day_start, now) >= 0 and \
           self.__minute_diff__(self.night_start, now) <= 0:
            return "day"
        else:
            return "night"
            
     
    def __minute_diff__(self, t1, t2):
        """
        Outputs t1 - t2 in minutes.Only [hh,mm]'s difference is calculated.
        time values can be machine.RTC() datetime tuple or [hh,mm].
        """
        def selector(time):
            if len(time) == 2:
                return time
            else: # Assume machine.RTC() datetime tuple
                return (time[4], time[5])
        t1 = selector(t1)
        t2 = selector(t2)
        
        diff = ((t2[0]*60)+t2[1]) - ((t1[0]*60)+t1[1])
        
        hours_diff = (t1[0] - t2[0] + 24) % 24
        min_diff = (t1[1] - t2[1] + 60) % 60
        #return (hours_diff * 60) + min_diff
        #print(diff)
        return diff
    
    
    def set_timers(self, mode="short"):
        """
        Set a timer to query scheduler state.
        mode == "short" : queries state every config.cs_callback_s seconds.
        mode == "long"  : executes two callbacks every single cycle based on
                           precise time calculations. [TODO]
        """
        if mode == "short":
            self.timer.init(mode=Timer.PERIODIC, period=30*1000, callback=self.short_callback)
            Log.write("out", f"Timer for Circadium Scheduler set: {self.timer}")
        
        elif mode == "long":
            
            # Determine what mode it is now
            # Flick the phase switch
            # setup timer
            
            Log.write("out", "CircadiumScheduler: Timer mode long is not implemented.")
            return
            

    def short_callback(self, timer):
        
        now = self.rtc.datetime()
        print("Scheduler Callback!")
        
        print(self.__minute_diff__(now, self.day_start), self.__minute_diff__(now, self.night_start))
        

        
        # Is it day?
        if math.fabs(self.__minute_diff__(now, self.day_start))*60 <= 30 and \
           math.fabs(self.__minute_diff__(now, self.last_day_callback)) > 5 and \
           self.is_active:
            # Bom Dia!
            self.__set_day__(now)
        
        
        # Is it night?
        if math.fabs(self.__minute_diff__(now, self.night_start))*60 <= 30 and \
           math.fabs(self.__minute_diff__(now, self.last_night_callback)) > 5 and \
           self.is_active:
            # Bon Noite!
            self.__set_night__(now)
        
        # Test for cycles
        if self.remaining_cycles == 0:
            self.is_active = False
        
        
          
