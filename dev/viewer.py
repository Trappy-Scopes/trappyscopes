


"""
The Viewer objects provides an interface to visualize the incoming data from the camera
and the sensors.

The Viewer Window has the following docks:
+ Video stream area
+ Plots area
+ Console area
"""


"""
ConsoleWidget is used to allow execution of user-supplied python commands
in an application. It also includes a command history and functionality for trapping
and inspecting stack traces.

"""
import numpy as np

import pyqtgraph as pg
import pyqtgraph.console
from pyqtgraph.Qt import QtCore

from time import perf_counter

### Create App
app = pg.mkQApp("Trappy-Scopes")


### Add a window stream
## Create window with GraphicsView widget
win = pg.GraphicsLayoutWidget()
#win.show()  ## show widget alone in its own window
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


## build an initial namespace for console commands to be executed in (this is optional;
## the user can always import these modules manually)
namespace = {'pg': pg, 'np': np}
c = pyqtgraph.console.ConsoleWidget(namespace=namespace, text="Trappy-Scopes")
c.show()
c.setWindowTitle('pyqtgraph example: ConsoleWidget')


## Execute App
if __name__ == '__main__':
    pg.exec()


