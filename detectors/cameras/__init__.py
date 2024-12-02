import logging as log
import os
import importlib.util
from rich.console import Console
console = Console()

def Selector(name, *args, **kwargs):
	try:
		if ".py" not in name:
			name = name + ".py"
		spec = importlib.util.spec_from_file_location(name, \
				 os.path.join("detectors/cameras", name))
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		#cam_module = __import__("."+name)
		return module.Camera(*args, **kwargs)
	except Exception:
		console.print_exception(show_locals=True)
		log.error("Camera not found!")