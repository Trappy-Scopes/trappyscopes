


## Create a  lab class instance

#from hive.lab import Lab
#lab = Lab()
#lab.connect(["m1", "m2", "m3", "m4"])



## Collect values
def get_tandh():
	
	values = [device.scope.tandh.read() for device in lab.devices]
	return values

## Create GUI with graphs
from gui.viewer import Viewer
import pyqtgraph as pg
print("Launching Trappy-Scopes Viewer")
view = Viewer()
view.console_exec("%load_ext rich")
view.console_exec("execfile('main.py')")
view.monitor_updater()
pg.exec()






