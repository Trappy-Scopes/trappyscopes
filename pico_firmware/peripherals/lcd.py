from machine import Pin, SPI, PWM
import framebuf
import time

#bl has to be a PWM channel
#pins__ = {"din":11,"clk":10,"cs":9,"dc":8,"rst":12, "bl:13	"

#color is BGR
RED = 0x00F8
YELLOW = 0x00F8
GREEN = 0xE007
BLUE = 0x1F00
WHITE = 0xFFFF
BLACK = 0x0000

class LCD_0inch96(framebuf.FrameBuffer):
    
    RED = 0x00F8
    YELLOW = 0x00F8
    GREEN = 0xE007
    BLUE = 0x1F00
    WHITE = 0xFFFF
    BLACK = 0x0000
    
    def __init__(self, pin_dict):
    
        self.width = 160
        self.height = 80
        self.char_w =  int(self.width/20)
        self.char_h = self.char_w
        
        self.cs = Pin(pin_dict["cs"],Pin.OUT)
        self.rst = Pin(pin_dict["rst"],Pin.OUT)
#       self.bl = Pin(13,Pin.OUT)
        self.cs(1)
        # pwm = PWM(Pin(13))#BL
        # pwm.freq(1000)        
        self.spi = SPI(1)
        self.spi = SPI(1,1000_000)
        self.spi = SPI(1,10000_000,polarity=0, phase=0,sck=Pin(pin_dict["clk"]),mosi=Pin(pin_dict["din"]),miso=None)
        self.dc = Pin(pin_dict["dc"],Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self.Init()
        self.SetWindows(0, 0, self.width-1, self.height-1)
        
        
    def reset(self):
        self.rst(1)
        time.sleep(0.2) 
        self.rst(0)
        time.sleep(0.2)         
        self.rst(1)
        time.sleep(0.2) 
        
    def update(self):
        self.dc(0)
        self.cs(0)
        self.spi.write(self.buffer)

    def write_cmd(self, cmd):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))

    def write_data(self, buf):
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([buf]))
        self.cs(1)

    def backlight(self, value):#value:  min:0  max:1000
        pwm = PWM(Pin(13))#BL
        pwm.freq(1000)
        if value>=1000:
            value=1000
        data=int (value*65536/1000)       
        pwm.duty_u16(data)  
        
    def Init(self):
        self.reset() 
        self.backlight(10000)  
        
        self.write_cmd(0x11)
        time.sleep(0.12)
        self.write_cmd(0x21) 
        self.write_cmd(0x21) 

        self.write_cmd(0xB1) 
        self.write_data(0x05)
        self.write_data(0x3A)
        self.write_data(0x3A)

        self.write_cmd(0xB2)
        self.write_data(0x05)
        self.write_data(0x3A)
        self.write_data(0x3A)

        self.write_cmd(0xB3) 
        self.write_data(0x05)  
        self.write_data(0x3A)
        self.write_data(0x3A)
        self.write_data(0x05)
        self.write_data(0x3A)
        self.write_data(0x3A)

        self.write_cmd(0xB4)
        self.write_data(0x03)

        self.write_cmd(0xC0)
        self.write_data(0x62)
        self.write_data(0x02)
        self.write_data(0x04)

        self.write_cmd(0xC1)
        self.write_data(0xC0)

        self.write_cmd(0xC2)
        self.write_data(0x0D)
        self.write_data(0x00)

        self.write_cmd(0xC3)
        self.write_data(0x8D)
        self.write_data(0x6A)   

        self.write_cmd(0xC4)
        self.write_data(0x8D) 
        self.write_data(0xEE) 

        self.write_cmd(0xC5)
        self.write_data(0x0E)    

        self.write_cmd(0xE0)
        self.write_data(0x10)
        self.write_data(0x0E)
        self.write_data(0x02)
        self.write_data(0x03)
        self.write_data(0x0E)
        self.write_data(0x07)
        self.write_data(0x02)
        self.write_data(0x07)
        self.write_data(0x0A)
        self.write_data(0x12)
        self.write_data(0x27)
        self.write_data(0x37)
        self.write_data(0x00)
        self.write_data(0x0D)
        self.write_data(0x0E)
        self.write_data(0x10)

        self.write_cmd(0xE1)
        self.write_data(0x10)
        self.write_data(0x0E)
        self.write_data(0x03)
        self.write_data(0x03)
        self.write_data(0x0F)
        self.write_data(0x06)
        self.write_data(0x02)
        self.write_data(0x08)
        self.write_data(0x0A)
        self.write_data(0x13)
        self.write_data(0x26)
        self.write_data(0x36)
        self.write_data(0x00)
        self.write_data(0x0D)
        self.write_data(0x0E)
        self.write_data(0x10)

        self.write_cmd(0x3A) 
        self.write_data(0x05)

        self.write_cmd(0x36)
        self.write_data(0xA8)

        self.write_cmd(0x29) 
        
    def SetWindows(self, Xstart, Ystart, Xend, Yend):#example max:0,0,159,79
        Xstart=Xstart+1
        Xend=Xend+1
        Ystart=Ystart+26
        Yend=Yend+26
        self.write_cmd(0x2A)
        self.write_data(0x00)              
        self.write_data(Xstart)      
        self.write_data(0x00)              
        self.write_data(Xend) 

        self.write_cmd(0x2B)
        self.write_data(0x00)
        self.write_data(Ystart)
        self.write_data(0x00)
        self.write_data(Yend)

        self.write_cmd(0x2C) 
        
    def display(self):
    
        self.SetWindows(0,0,self.width-1,self.height-1)       
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buffer)
        self.cs(1)

# New Functions
    def top(self, text, tcolor=GREEN):
        self.text(text,0, 15,tcolor)
        self.display()
       
    def middle(self, text, tcolor=GREEN):
        self.text(text ,0, 35, tcolor)
        self.display()
    
    def bottom(self, text, tcolor=GREEN):
        self.text(text, 0, 55, tcolor)
        self.display()
        
    def bg(self, color):
        self.fill(color)
        self.display()
        
    def whitegrid(self):
        self.fill(WHITE)    
        
        i=0
        while(i<=80):    
            self.hline(0,i,160,BLACK)
            i=i+10  
        i=0
        while(i<=160):
            self.vline(i,0,80,BLACK)
            i=i+10 
        self.display()
            
    def multiline(self, text):
        text = text.rstrip("\n")
        no_lines = text.count("\n") + 1
        each_line = text.split("\n")
        
        for i, line in enumerate(each_line):
            self.text(line, 0, 0+(i*8), GREEN)
        self.display()
        
    def line(self, line, text, tcolor=GREEN):
        self.text(text, 0, int(self.char_h*line), tcolor)
        self.display()
        
    def center(self, text):
        maxchars = 20
        len_ = len(text)
        
        if len_ >= maxchars:
            return text
        else:
            pad = maxchars-len_
            return f"{int(pad/2)*" "}{text}{int(pad/2)*" "}"
        
    def left(self, text):
        return text
        
    def right(self, text):
        maxchars = 20
        len_ = len(text)
        
        if len_ >= maxchars:
            return text
        else:
            return f"{(maxchars-len_)*" "}{text}"
        

    def intro_seq(self):
        
        self.bg(RED)
        time.sleep(1)
        
        self.bg(GREEN)
        time.sleep(1)
        
        self.bg(BLUE)
        time.sleep(1)
        
        self.bg(WHITE)
        time.sleep(1)
        
        self.bg(BLACK)
        time.sleep(1)
    

if __name__=='__main__':
    lcd = LCD_0inch96()
    lcd.fill(BLACK)    
    text = """
\   ^__^
 \ (oo)\_______
   (__)\       )\/\
        ||----w |
        ||     ||"""
    lcd.multiline(text)
    time.sleep(1)
    lcd.display()
    for i in range(1):
        lcd.intro_seq(lcd)
    
    
