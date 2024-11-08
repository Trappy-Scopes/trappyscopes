## Obsolete
import time
import network
from machine import Pin
import secrets
import ubinascii
import urequests
import gc

# TODO
#1. Understand sockets
#2. Create basic browse functionality
#3. Serve webpage functionality


"""
Format for secrets for wifi:

wifi = [{dict of credentials1}, {dict of credentials2},
                          ..., {dict of credentialsn}]

{dict of credentials} == {SSID:<ssid>, PASSWORD:<password>}
"""

######### NOTES #########
## Return value of cyw43_wifi_link_status
#define CYW43_LINK_DOWN (0)
#define CYW43_LINK_JOIN (1)
#define CYW43_LINK_NOIP (2)
#define CYW43_LINK_UP (3)
#define CYW43_LINK_FAIL (-1)
#define CYW43_LINK_NONET (-2)
#define CYW43_LINK_BADAUTH (-3)

class Wifi:

    #1
    def __init__(self, secrets=None):
        """
        Create a Wifi object and establish connection if the secrets are shared.
        """
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.connected = False
        
        # Device Info
        self.mac = ubinascii.hexlify(self.wlan.config('mac'),':').decode()
        self.time_on_connected = None
        self.ip = None
        self.ssid = None
        
        # Connect if secrets are passed.
        if secrets != None:
            self.connect(secrets)


        # Sockets
        self.ssocket = None # Server socket
        self.std_response = "ACK" # Standard response of the sever on a request.
            

    #2   
    def connect(self, secrets):

        for credentials in secrets:
            self.wlan.connect(credentials["SSID"], credentials.["PASSWORD"])
            print("Wifi: Attempting to connect to: %s"%credentials["SSID"])
            
            # Wait for connect or fail
            max_wait = 10
            while max_wait > 0:
                if self.wlan.status() < 0 or self.wlan.status() >= 3:
                    break
                max_wait -= 1
                print('Wifi: waiting for connection...')
                time.sleep(1)

            # Handle Connection Status
            if self.wlan.status() != 3:
                self.connected = False
                print('Wifi: Wifi network connection failed!')
                print(f"Wifi: {self.wlan.status()}")
            else:
                self.connected = True
                led = Pin("LED", Pin.OUT)
                for _ in range(6):
                    led.toggle()
                    time.sleep(0.5)

                self.ssid = credentials.SSID
                self.status = self.wlan.ifconfig()
                self.connected_ms_tick = time.ticks_ms()
                self.ip = status[0]
                gc.collect()
                return {"ssid": self.ssid, "ip":self.ip, "mac": self.mac}
            gc.collect()
            return None

    #3
    def disconnect(self):
        """
        Disconnect from the current network
        """
        self.wlan.active(False)
        self.connected = False
        self.ssid = None
        self.ip = None
        print("Wifi: Wifi is disconnected!")

    def info(self):
        return {"ssid": self.ssid, "ip":self.ip, "mac": self.mac, 
               "connected": self.connected, 
               "elapsed_ms": time.ticks_ms() - self.connected_ms_tick
               }

    
    def list_networks(self):
        """
        Lists all wifi networks in that can be detected by the pico board.
        """
        nets = self.wlan.scan()
        return nets
        
    def ifconfig(self):
        return self.wlan.ifconfig()


    def server_socket(self):
        """
        Create and launch a sockets web server.
        Assumes that wifi is already connected.
        """
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        
        self.ssocket = socket.socket()
        self.ssocket.bind(addr)
        self.ssocket.listen(1)
        print('Wifi: server listening on: ', addr)
        gc.collect()
        return self.ssocket

    def check_clients(self, response="", no_requests=1):
        """
        Funtion receives connection on open socket and dumps the
        content to the connecting client.
        """
        # Listen for connections
        for req_id in range(no_requests):
            try:
                cl, addr = self.ssocket.accept()
                print('Server socket: client connected from: ', addr)
                request = cl.recv(1024)
                print(request)


                cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
                cl.send(self.std_response)
                cl.close()

            except OSError as e:
                cl.close()
                print('Server socket: [ERROR] connection closed without due process.')
            gc.collect()

    #6
    def post(self, url, data=None):
        if data:
            response = urequests.post(url, headers=our_headers, data=data)
        else:
            response = urequests.post(url)
        return response


if __name__ == "__main__":
    wifi = Wifi(secrets)
    time.sleep(5)
    wifi.disconnect()
