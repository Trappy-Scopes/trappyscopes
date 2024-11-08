import board


#cid 0: Needs no assignments
    
# cid 1:
if board.circuit_id == "4ch_pwm_sc1":
    light = {
        "red_pin"   : 9,
        "green_pin" : 10,
        "blue_pin"  : 12,
        "white_pin" : 16,
    }
    
    beacon = 14

    sensors = {
        "tandh"  : 15
    }
    
# cid: 2
if board.circuit_id == "4_clustcontrol_v1_proto":
    rpictrl = {
                1: {"RUN": 3 , "GLOBAL_EN": 2},
                2: {"RUN": 5,  "GLOBAL_EN": 4},
                3: {"RUN": 7, "GLOBAL_EN" : 6},
                4: {"RUN": 9, "GLOBAL_EN" : 8}
        }
    buzzer = 16 ## Unassigned
    sensors = {
        "tandh"  : 15
    }
    

if board.circuit_id == "2ch_peristat_kitroniks_vx_shield":
    ## Assignmnets for Kirktronics Pico Shield
    ## https://resources.kitronik.co.uk/pdf/5331-compact-motor-driver-raspberry-pi-pico-datasheet.pdf
    m1_fwdpin         = 2  ## Shield specific
    m1_revpin         = 3  ## Shield specific
    m2_fwdpin         = 6  ## Shield specific
    m2_revpin         = 7  ## Shield specific
    potentiometer  = 26 ## ADC0