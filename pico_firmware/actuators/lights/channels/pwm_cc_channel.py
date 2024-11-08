from machine import Pin, PWM


class PwmCCchannel:

    def __init__(self, pin_no):
        self.type = "pwm_common_anode_channel"

        self.pin_no = pin_no
        self.freq = int(30*1e5)
        self.pin = PWM(Pin(pin_no), freq=self.freq)
        self.duty = int(2**16 - 1)

        self.llimit = 0
        self.ulimit = 3.3

        self.setV(0)


    def setV(self, V):
        dutycycle_u16 = int(float(V)/self.ulimit*65535)
        self.duty = dutycycle_u16
        self.pin.duty_u16(int(dutycycle_u16))   
