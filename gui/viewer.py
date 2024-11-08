"""
This example demonstrates the use of pyqtgraph's dock widget system.

The dockarea system allows the design of user interfaces which can be rearranged by
the user at runtime. Docks can be moved, resized, stacked, and torn out of the main
window. This is similar in principle to the docking system built into Qt, but 
offers a more deterministic dock placement API (in Qt it is very difficult to 
programatically generate complex dock arrangements). Additionally, Qt's docks are 
designed to be used as small panels around the outer edge of a window. Pyqtgraph's 
docks were created with the notion that the entire window (or any portion of it) 
would consist of dockable components.
"""

import os
import numpy as np
import sys

import pyqtgraph as pg
from pyqtgraph.console import ConsoleWidget
from pyqtgraph.dockarea.Dock import Dock
from pyqtgraph.dockarea.DockArea import DockArea
from pyqtgraph.Qt import QtWidgets, QtGui

try:
    from qtconsole import inprocess
except (ImportError, NameError):
    print(
        "The example in `jupyter_console_example.py` requires `qtconsole` to run. Install with `pip install qtconsole` or equivalent."
    )
    sys.exit(1)

class Viewer(QtWidgets.QMainWindow):

    def __init__(self, **kwargs):
        """
        Initalization function (constructor):
        kwargs:
        ------
        * resolution : list of two values [x_resolution, y_resolution].
        * icon : adds window icon if the passed string path is a png, ignores it otherwise.
        * title : sets the window title


        Trappy-Scopes Viewer:

        Attributes:
        -----------

        + app : QT Application Instances
        + window : Main window instance
        + docks : Map of Dock Objects
        + widgets : Map of Widget objects

        Each Widget corresponds to one Dock Instance.

        ### TODO
        Fix the prompts issue: https://stackoverflow.com/questions/42108005/unable-to-set-ipython-prompt
        """
       
        # Set Application
        self.app = pg.mkQApp("Trappy-Scopes Viewer")
        self.resolution = [1920, 1080]
        #self.app = QtWidgets.QMainWindow()
        
        # Set Window
        self.wintitle = "Trappy-Scopes Viewer"
        if 'title' in kwargs:
            self.wintitle = kwargs['title']

        self.window = QtWidgets.QMainWindow()
        self.dock_area = DockArea()
        self.window.setCentralWidget(self.dock_area)
        self.window.resize(*self.resolution)
        self.window.setWindowTitle(self.wintitle)

        if 'icon' in kwargs:
            if kwargs['icon'].endswith('.png'):
                # Set icon
                icon = QtGui.QIcon(kwargs['icon'])
                self.window.setWindowIcon(icon)

        # Enable antialiasing and OpenGL use
        #pg.setConfigOptions(antialias=True, useOpenGL=True)


        self.canvaslist = {} # Dictionary of canvases.
        self.curvelist = {}  # Dictionary of curve handles -> accessed via `curvelist['canvas_name']['curve_name']`.


        # Create 3 Docking areas --------------------------------
        d1 = Dock("Camera", size=(400, 400), closable=False)
        d2 = Dock("Monitor 1", size=(400,300), closable=False)
        d3 = Dock("Monitor 2", size=(400,300), closable=False)
        d4 = Dock("Console", size=(1000,400), closable=False)
        self.docks = {"cam": d1, "mon1": d2, "mon2": d3, "console": d4}
        
        self.dock_area.addDock(d1, 'left')      
        self.dock_area.addDock(d2, 'right')
        self.dock_area.addDock(d3, 'below', d2)
        self.dock_area.addDock(d4, 'bottom')
        #---------------------------------------------------------
        


        ## Add widgets into each dock ----------------------------
        self.widgets = {}
        self.update = 0

        ## Dock 1 - Camera view
        self.widgets["cam"] = pg.ImageView()
        import matplotlib.pyplot as plt
        self.widgets["cam"].setImage(np.rot90(np.fliplr(plt.imread("./utilities/trappyscopes.png"))))
        self.docks["cam"].addWidget(self.widgets["cam"])

        ## Dock 2 - Monitor 1
        self.widgets["mon1"] = pg.PlotWidget(title="Monitor 1")
        self.widgets["mon1"].addLegend(offset=(0,0))
        self.widgets["mon1"].plot(np.random.normal(size=100), pen="w", name="white")
        self.widgets["mon1"].plot(np.random.normal(size=100), pen="y", name="yellow")
        self.docks["mon1"].addWidget(self.widgets["mon1"])

        ## Dock 3 - Monitor 2
        self.widgets["mon2"] = pg.PlotWidget(title="Monitor 2")
        self.widgets["mon2"].plot(np.random.normal(size=500))
        self.docks["mon2"].addWidget(self.widgets["mon2"])


        ## Dock 4 - Ipythion Console
        self.widgets["console"] = JupyterConsoleWidget()
        self.docks["console"].addWidget(self.widgets["console"])

        #app = QtWidgets.QApplication.instance()
        # Add proper Kernal Shutdown
        self.app.aboutToQuit.connect(self.abort)

        self.kernel = self.widgets["console"].kernel_manager.kernel
        self.kernel.shell.push(dict(np=np))

        # Set Dark Mode
        #self.widgets["console"].set_default_style("linux")

        self.data = {"mon1": [], "mon2": []}
        self.timer = None
        self.monitor_updater()  # Start the update function

        self.kernel.shell.push(dict(monitor=self.data, add_mon=self.add_datastream))
        ## -------------------------------------------------------

        self.window.show()

    def abort(self):
        self.widgets["console"].shutdown_kernel
        self.timer.stop()
        print("Ended GUI.")
        

    def add_datastream(self, monitor, name, **kwargs):
        datastream = DataStream(name, **kwargs)
        self.data[monitor].append(datastream)
        curve = self.widgets[monitor].plot(*datastream.get(), pen=datastream.pen, \
                                   name=datastream.name)
        # Add reference to the curve.
        datastream.curve = curve
        return datastream

    def launch(self):
        pg.exec()

    def console_exec(self, string):
        """
        Execute something in the present kernal state.
        """
        self.widgets["console"].execute(string)

    def monitor_updater(self):
        """
        Check this 50 value. What is it?
        """
        def all_curve_updates():
            self.update += 1
            for mon in ["mon1", "mon2"]:
                for data in self.data[mon]:
                    data.update_curve()
            print(f"Update : {self.update}", end='\r')

        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(all_curve_updates)
        self.timer.start(100)

class JupyterConsoleWidget(inprocess.QtInProcessRichJupyterWidget):
    """
    Code from pygtgraph.examples.
    """
    def __init__(self):
        super().__init__()

        self.kernel_manager = inprocess.QtInProcessKernelManager()
        self.kernel_manager.start_kernel()
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()

    def shutdown_kernel(self):
        self.kernel_client.stop_channels()
        self.kernel_manager.shutdown_kernel()




if __name__ == '__main__':
    print("At:", os.getcwd())
    print("Launching Trappy-Scopes Viewer")
    view = Viewer()
    view.console_exec("%load_ext rich")
    view.console_exec("import os; print(os.getcwd())")
    view.console_exec("execfile('main.py')")
    view.monitor_updater()
    pg.exec()
