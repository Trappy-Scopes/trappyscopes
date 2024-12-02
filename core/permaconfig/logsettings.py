import os

import logging
from rich.logging import RichHandler

from experiment import Experiment
from sharing import Share



if isinstance(Experiment.current, Experiment):
    filename = Experiment.current.exp_dir
else:
    filename = Share.logdir
FORMAT = "%(message)s"
logging.basicConfig(
                     #filename=os.path.join(filename, "logfile.txt"),
                     level="NOTSET", 
                     format=FORMAT, 
                     datefmt="[%X]", 
                     handlers=[#logging.FileHandler('/test.log', mode='a'),
                               RichHandler(rich_tracebacks=True)]
)