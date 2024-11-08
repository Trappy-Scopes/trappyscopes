import machine
import rtc





class Exchange:

    in_buffer = []    # Stuff received
    out_buffer = []   # Stuff to be sent out

    transponder = None

    def __init__(self):
        pass

    def transmit(string):
        """
        Transmit a message out of the device over usb.
        """
        #global out_buffer
        
        if string[-1] != '\n':
            string = string + '\n'
        
        Exchange.out_buffer.append(string)



    def loop(poll_period):
        if len(Exchange.out_buffer) > 0:
            Excahnge.transponder.send(Exchange.out_buffer[0])
            Excahnge.out_buffer = Excahnge.out_buffer[1:]

        time.sleep(0.1)

        if len(in_buffer) > 0:
            for i in range(len(in_buffer)):
                check_and_exec(in_buffer.popleft())



    
    
def handshake_str():
    """
    Transmits important information about the machine. TODO: Maybe handshake should get equal access to the USB trnasmission API to prevent timing lags.
    """
    string = f'epoch:{time.time_ns()}, time:{rtc.datetime()}, job:{device_job}, id: {machine.unique_id()}'
    return string


def check_and_exec(string):
    """
    Checks if a given string contains an executable code and forwards it to in_buffer.
    """
    global in_buffer
    
    possible_code = string[:3]
    
    if possible_code is any([">>>", "CMD"]):
        in_buffer.append(string[3:])
    



 

def send_ack_code(pr_id):
    """
    Send an acknowledgement code for a given process id.
    """
    global usb
    pr_id = "ACK" + pr_id
    
    transmit(pr_id)
    
def exchange():
    
    global usb, in_buffer, out_buffer
    
    # If there is anything in the out buffer, transmit it.
    if not len(out_buffer) == 0:
        for i in range(len(out_buffer)):
            usb.send(out_buffer.popleft())
            usb.flush()
    
    # Try and read input buffer of USB
    # TODO
    
    # Transfer buffer
    if not len(in_buffer) == 0:
        for i in range(len(in_buffer)):
            check_and_exec(in_buffer.popleft())
        

def process_cmd(string):
    if string.split()[0] in fn_registry:
        
        
    
    