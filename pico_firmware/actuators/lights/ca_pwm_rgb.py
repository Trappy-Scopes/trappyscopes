import sys



class CaPwmRgbLed():
    """
    Object used to control Multichannel Common Anode LED
    with Raspberry Pi Pico.
    """

    # CONSTANTS
    DUTYMIN = 0
    DUTYMAX = 2**16 - 1
    
    # 1
    def __init__(self, rpin, gpin, bpin):

        self.type = "ca_pwm_rgb"
        self.channels = "rgb"
        self.pin_map  = {'r': rpin, 'g': gpin, 'b': bpin}
        self.ch_map   = {'r': Pin(rpin), 'g': Pin(gpin), 'b': Pin(bpin)}
        self.dc_map   = {'r': self.DUTYMAX, 'g': self.DUTYMAX, 'b': self.DUTYMAX} # Duty Cycle
        self.freq     = int(30*1e5) # 3MHz
        self.normalize = False
        self.lux = 0
        self.limits = {"r": [0, 3.3],  "g": [0, 3.3], "b": [0, 3.3]}
        
        #self.rnorm = [1.0, 
        #              3.0 - 1.8 + (3.2-3.0)/(2.0 -1.8),
        #              3.0 - 1.8 + (3.2-3.0)/(2.0 -1.8)]


    #2
    def on(lux=0.0, ch="rgb"):
        """
        Initializes the PWM object on the given channel.
        and sets the frequency. Operation required after
        blocking a channel.
        """
        for ch in channels:
            if ch in self.channels:
                self.ch_map[ch] = \
                PWM(Pin(self.pin_map[ch], mode=Pin.OUT))
                self.ch_map[channel].freq(self.freq)
                self.set_ch(ch, lux=0.0)

    #3
    def off(ch="rgb"):
        if channels == None:
            channels = "rgb"

        for ch in channels:
            if ch in self.channels:
                self.set_ch(ch, lux=0.0)
    
    #4 ## NOK
    def block(self, ch="rgb"):
        if channel in self.channels:
            if isinstance(ch_map[channel], PWM):
                self.ch_map[channel].deinit()
                print(isinstance(self.ch_map[channel], PWM))
            
            self.ch_map[channel] = Pin(self.pin_map[channel], mode=Pin.OUT)
            self.ch_map[channel].on()

    #5 ## OK
    def set_ch(self, ch, lux=1.0):
        """
        Maps Lux to the controlling parameter of the actual device.
        Control method: Negative PWM gating on 3.3V applied Voltage.
        """
        def interpolate(in_val, in_min, in_max, out_min, out_max):
            in_span = in_max - in_min
            out_span = out_max - out_min
            out_val = float(in_val - in_min) / float(in_span)
            return out_min + (out_val * out_span)
        
        self.lux = lux
        if channel in self.channels:
            dutycycle_u16 =  65535 - int(interpolate(lux, 0.0, 1.0, 1, 65535))
            self.ch_map[channel].duty_u16(int(dutycycle_u16))


    #6 ##OK
    def setV(self, ch, volt):
        if channel in self.channels:
            dutycycle_u16 =  65535 - int(float(volt)/3.3*65535)
            self.ch_map[channel].duty_u16(int(dutycycle_u16))
            self.lux = interpolate(int(dutycycle_u16), 1, 65535, 0.0, 1.0)



    #7 ##OK
    def setVs(self, rV, gV, bV):
        self.setV('r', rV)
        self.setV('g', gV)
        self.setV('b', bV)

    #8
    def setIs(self, rI_mA, gI_mA, bI_mA):
        raise Exception("setIs: Method not implemented!")

    #9 #NOK
    def setI(self, ch, current_mA):
        raise Exception("setI: Method not implemented!")

    #10 ## NOK
    def sweep(self, period_s=0.1, steps=20, ch="rgb"):
        rangevect = list(range(0, steps))
        rangevect = [float(val) * (1.0/steps) for val in rangevect] 
        for channel in ch:
            for lux in rangevect:
                self.set_ch(channel, lux=int(lux))
                sleep(period_s)

    
    #11  ##OK
    def set_max(self, ch="rgb"):
        for c in ch:
            if c in self.channels:
                self.set_ch('r', lux=1.0)
    
    #12 ##OK
    def red(lux=1.0):
        self.set_ch('r', lux=lux)
  
    #13  ##OK
    def green(lum=1.0):
        self.set_ch('g', lux=lux)

    #14 ##OK
    def blue(lum=1.0):
        self.set_ch('b', lux=lux)

    #15 ##OK
    def white(lux=1.0):
        # TODO: balance colors
        self.set_ch('r', lux=lux)
        self.set_ch('g', lux=lux)
        self.set_ch('b', lux=lux)


    #17 ##NOK
    def strobe(self, switch, timer=None):
        state = self.dc_map
        def toggler(timer):
            if self.dc_map == state:
                for key in ch_map:
                    ch_map[key].duty_u16(self.DUTYMAX)
            else:
                for key in ch_map:
                    ch_map[key].duty_u16(state[key])

        if switch:
            self.timer.deinit()
            self.timer.init(freq=1, mode=Timer.PERIODIC, callback=toggler)
        else:
            timer.deinit()
            for key in ch_map: # Restore State
                ch_map[key].duty_u16(state[key])


    def state(self):
        return { "type" : self.type,
                 "channels" : self.channels,
                 "pin_map" : self.pin_map,
                 "ch_map" : self.ch_map,
                 "dc_map" : self.dc_map,
                 "freq" : self.freq,
                 "normalize" : self.normalize,
                 "limits" : self.limits
                }

    def __str__(self): 
        return {"V": self.v_map, "duty": dc_map}
