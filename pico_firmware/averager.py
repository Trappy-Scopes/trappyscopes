from array import array

class Averager:
    
    def __init__(self, name, size=100, init=0.0):
        
        self.name = name
        self.buff = array('f', [init]*size)
        self.size = size
        self.last = 0
        
        self.it = 0
        
    def update(self, val):
        self.last = val
        self.buff[self.it] = val
        self.__itr__()
        
    def __itr__(self):
        self.it =  self.it+1
        
        if self.it >= self.size:
            self.it = 0
            
    def avg(self):
        mean = sum(self.buff) / self.size
        return mean
    
    def get(self):
        return (self.last, self.avg())
    
    def __repr__(self):
        return f"< Averager - {self.name} >"
        
        
