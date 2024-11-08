import board
from machine import RTC
import machine
import ubinascii


rtc = RTC()
class Handshake:
    uuid = ubinascii.hexlify(machine.unique_id()).decode()

    def intro():
        return "device: {}, uuid: {}, circuit: {}, rtc: {}".format( \
               board.name, Handshake.uuid, board.circuit_id, rtc.datetime())

    def hello():
        print(f"Hello I am {board.name}! - [{Handshake.uuid}]")
        
    def obj_list(globals_=None):
        if not globals_:
            all_ = globals()
        else:
            all_ = globals_
        objects = [obj for obj in all_ \
                   if  "object" in str(all_[obj]) or "Pin" in str(all_[obj])]
        exclusion_list = ['__thonny_helper', "Pin", "power"]
        for obj in exclusion_list:
            if obj in objects:
                objects.remove(obj)
        return objects