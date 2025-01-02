import os

import logging
from rich.logging import RichHandler

from experiment import Experiment
from .sharing import Share



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


## Set Logging
class ErrorCollectingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.errors = []

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.errors.append(self.format(record))

    def summarize_errors(self):
        if not self.errors:
            return "No errors logged."
        return "\n".join(self.errors)

# Setup the custom handler
error_collector = ErrorCollectingHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
error_collector.setFormatter(formatter)
