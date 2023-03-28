import time
import picamera
import numpy as np


"""

It is also important to note that when outputting to unencoded formats, the camera rounds the requested resolution. The horizontal resolution is rounded up to the nearest multiple of 32 pixels, while the vertical resolution is rounded up to the nearest multiple of 16 pixels. For example, if the requested resolution is 100x100, the capture will actually contain 128x112 pixels worth of data, but pixels beyond 100x100 will be uninitialized.

So, to capture a 100x100 image we first need to provide a 128x112 array, then strip off the uninitialized pixels afterward. The following example demonstrates this along with the re-shaping necessary under Python 2.x:
"""

with picamera.PiCamera() as camera:
    camera.resolution = (100, 100)
    camera.framerate = 30
    time.sleep(2)
    output = np.empty((112 * 128 * 3,), dtype=np.uint8)
    camera.capture(output, 'rgb')
    output = output.reshape((112, 128, 3))
    output = output[:100, :100, :]

"""
Demonstrates very basic use of ImageItem to display image data inside a ViewBox.
"""

from time import perf_counter

import numpy as np

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

app = pg.mkQApp("ImageItem Example")

## Create window with GraphicsView widget
win = pg.GraphicsLayoutWidget()
win.show()  ## show widget alone in its own window
win.setWindowTitle('pyqtgraph example: ImageItem')
view = win.addViewBox()

## lock the aspect ratio so pixels are always square
view.setAspectLocked(True)

## Create image item
img = pg.ImageItem(border='w')
view.addItem(img)

## Set initial view bounds
view.setRange(QtCore.QRectF(0, 0, 600, 600))

## Create random image
data = np.random.normal(size=(15, 600, 600), loc=1024, scale=64).astype(np.uint16)
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
