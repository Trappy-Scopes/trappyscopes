import logging as log
import os
import importlib.util


def Selector(name, submodulepath, objtype, *args, **kwargs):
	"""
	Generic submodule selector function. Creates objects by selecting it from specific
	submodules.
	name             : name of submodule (specific camera).
	submodulepath    : absolute path of the submodule import
	objtype          : Type of object name in submodule (e.g. "Camera")
	*args, **kwargs  : arguments to be passed to the created object. 
	"""
	from rich.console import Console
	console = Console()
	try:
		if ".py" not in name:
			name = name + ".py"
		spec = importlib.util.spec_from_file_location(name, \
				 os.path.join(submodulepath, name))
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		
		#cam_module = __import__("."+name)
		return getattr(module, objtype)(*args, **kwargs)
	except Exception:
		console.print_exception(show_locals=True)
		log.error(f"{objtype} not found!")