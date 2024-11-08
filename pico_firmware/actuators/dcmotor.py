from machine import PWM, Pin, ADC, Timer
import math

# Will return a integer
def convert(value, from_low, from_high, to_low, to_high):
    """
    ### Chat GTP
    Maps a value from one range to another.

    Parameters:
    - value: The input value to be mapped.
    - from_low: The lower bound of the input range.
    - from_high: The upper bound of the input range.
    - to_low: The lower bound of the output range.
    - to_high: The upper bound of the output range.

    Returns:
    The mapped value in the output range.
    """
    # Ensure the input value is within the specified range
    value = max(min(value, from_high), from_low)
    
    # Calculate the mapping
    from_range = from_high - from_low
    to_range = to_high - to_low
    mapped_value = to_low + (value - from_low) * to_range / from_range
    
    return mapped_value

class DCMotor:
    
    def __init__(self, fwdpin, revpin):
        self.pin_no = {"fwd": fwdpin, "rev":revpin}
        self.fwdpin = PWM(Pin(fwdpin))
        self.revpin = PWM(Pin(revpin))
        
        self.fwdpin.freq(10) #10k Hertz
        self.revpin.freq(10)
        
        self.dir = +1
        self.duty = 0 # range: 0-65535
        self.speed_ = 0 #Here, defined only when self.duty == 0.
        self.fwdpin.duty_u16(int(self.duty))
        self.revpin.duty_u16(int(self.duty))
        self.pot = None
        self.feedback = None
        self.feedback_verbose = True
        
    def speed(self):
        return self.dir * self.speed_
        
    def speed(self, unit_speed):
        
        if unit_speed == None:
            unit_speed = self.speed_
        unit_speed = math.fabs(unit_speed)
        unit_speed = unit_speed * (unit_speed <= 1.0) + 1 * (unit_speed > 1.0)
        
        ## Map speed and set
        self.speed_ = unit_speed
        self.duty = convert(unit_speed, 0.0, 1.0, 0, 65535)
        if self.dir == 1:
            self.revpin.duty_u16(0)
            self.fwdpin.duty_u16(int(self.duty))
        elif self.dir == -1:
            self.fwdpin.duty_u16(0)
            self.revpin.duty_u16(int(self.duty))
        
    def min_speed(self, speed):
        self.speed(0.05)
        
    def max_speed(self, speed):
        self.speed(1.0)
        
    def fwd(self, speed=None):
        self.dir = 1
        if speed:
            self.speed(speed)
            
    def rev(self, speed=None):
        self.dir = -1
        if speed:
            self.speed(speed)
            
    def hold(self):
        self.fwdpin.duty_u16(65535)
        self.revpin.duty_u16(65535)
        
    def release(self):
        self.fwdpin.duty_u16(0)
        self.revpin.duty_u16(0)
        
    def set_speed_controller(self, potpin):
        
        ## Disable old controller
        if isinstance(self.feedback, Timer):
            self.unset_speed_controller()
        
        
        self.pot = ADC(Pin(potpin))
        def speedcontrol(Timer):
            read = self.pot.read_u16()
            ##print("pot", read)
            val = convert(read, float(0), float(65535), 0.0, 1.0)
            self.speed(val)
            if self.feedback_verbose:
                print(val)
        self.feedback = Timer(period=500, mode=Timer.PERIODIC, \
                                    callback=speedcontrol)
    
    def unset_speedcontrol(self):
        self.feedback.deinit()
        