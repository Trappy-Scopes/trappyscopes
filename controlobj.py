
class Sensor:



class DataStream:
    """
    Creates an instance for data aggregation and processing.
    """

    def __init__(self, name, pen="w", maxlen=100, timetag=False):
        self.buffx = Deque(maxlen=maxlen)
        self.buffy = Deque(maxlen=maxlen)
        self.name = name
        self.pen = pen
        self.curve = None # Save copy of the curve instance
        
        self.t0 = time.perf_counter() # Zero time

    def update(self, x, y):
        self.buffx.append(x)
        self.buffy.append(y)

    def timetag(self, data):
        t = time.perf_counter() - self.t0
        self.buffx.append(t)
        self.buffy.append(data)

    def update_curve(self):
        self.curve.setData(self.buffx, self.buffy)

    def get(self):
        return (self.buffx, self.buffy)