"""
File that configures rich(https://rich.readthedocs.io/en/stable/introduction.html) for use.
"""

from rich import pretty ## Default pretty printing
pretty.install()        ## Install pretty traceback handling
from rich.traceback import install as tracebackinstall 
tracebackinstall(show_locals=False)