"""
Demonstrates very basic use of ImageItem to display image data inside a ViewBox.
"""

from time import perf_counter
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore


app = pg.mkQApp("Trappy Scope")

## Create window with GraphicsView widget
win = pg.GraphicsLayoutWidget()
win.show()  ## show widget alone in its own window
win.setWindowTitle('Trappy Systems')
view = win.addViewBox()


view.setAspectLocked(True)

## lock the aspect ratio so pixels are always square
## Create image item
img = pg.ImageItem(border='w')
view.addItem(img)

## Set initial view bounds
view.setRange(QtCore.QRectF(0, 0, 1920, 1080))

## Create random image
data = np.random.normal(size=(15, 1920, 1080), loc=1024, scale=64).astype(np.uint16)
i = 0

updateTime = perf_counter()
elapsed = 0

timer = QtCore.QTimer()
timer.setSingleShot(True)
# not using QTimer.singleShot() because of persistence on PyQt. see PR #1605

def updateData():
    global img, data, i, updateTime, elapsed

    ## Display the data
    img.setImage(data[i])
    i = (i+1) % data.shape[0]

    timer.start(1)
    now = perf_counter()
    elapsed_now = now - updateTime
    updateTime = now
    elapsed = elapsed * 0.9 + elapsed_now * 0.1

    # print(f"{1 / elapsed:.1f} fps")
    
timer.timeout.connect(updateData)
updateData()

if __name__ == '__main__':
    pg.exec()




class PhotometerLivePlot:


    def __init__(self):
        self.app = pg.mkQApp("Trappy Systems Photometer")

        ## Create window with GraphicsView widget
        self.win = pg.GraphicsLayoutWidget()
        self.win.show()  ## show widget alone in its own window
        self.win.setWindowTitle("Trappy Systems Photometer")
        self.view = win.addViewBox()


        self.view.setAspectLocked(True)


        self.color_map = { 415      : (143, 0, 255), # Violet
                      445      : (75, 0, 130),  # Indigo
                      480      : "b",
                      515      : "c",
                      555      : "g",
                      590      : "y",
                      630      : (255, 165, 0),
                      680      : "r",
                      #"near-ir": (255, 0, 0, 128),
                      #"clear"  : (255, 255, 255)
                    }

        # Create BarObjects
        self.bars = {}
        for color in self.color_map:
            self.bars[color] = pg.BarGraphItem(x=color, height=newdata[color],  \
                                          width=0.3, brush=color_map[color])
            self.win.addItem(self.bars[color])


    def start(self):
        self. updatetime = perf_counter()
        self.elapsed = 0

        self.timer = QtCore.QTimer()
        self.timer.setPeriodic(True)




    def update_fn(self, newdata):
        for color in newdata:
            self.bars[color] = pg.BarGraphItem(x=color, height=newdata[color], \
                               width=0.3, brush=self.color_map[color])






            

            
           


if __name__ == '__main__':
    pg.exec()

