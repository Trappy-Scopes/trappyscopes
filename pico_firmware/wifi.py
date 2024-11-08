"""
Wireless connection code.
"""

import time
import network
from machine import Pin
import ubinascii
import urequests
import gc

import pico_firmware.secrets as secrets

class Wifi:
    def __init__(self, connect=True):
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.connected = False
        
        # Device Info
        self.mac = ubinascii.hexlify(self.wlan.config('mac'),':').decode()
        self.time_on_connected = None
        self.ip = None
        self.ssid = None
        
        # Connect if secrets are passed.
        if connect:
            self.connect(secrets)


    def connect(self, ssid=None, password=None):
        pass
    def disconnect(self):
        pass
    def reconnect(self, delay=0):
        pass
    
    
    def info(self):
        return {"ssid": self.ssid, "ip":self.ip, "mac": self.mac, 
                "connected": self.connected, 
                "elapsed_ms": time.ticks_ms() - self.connected_ms_tick
               }

    def list_nets(self):
        """
        Lists all wifi networks that can be detected by the pico board.
        """
        nets = self.wlan.scan()
        return nets
        
    def ifconfig(self):
        return self.wlan.ifconfig()