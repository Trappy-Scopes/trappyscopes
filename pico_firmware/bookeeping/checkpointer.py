import pickle

from pico_firmware.core import logging as log

class Checkpointer:
	"""
	The function of this class is to save and restore function arguments
	to restore functions upon powercycles, or other similar cases.

	Will fail for nested object. Assumes a singleton instance.
	"""

	def gen_name(fn):
		"""
		Generate the generic name for a function/class.
		"""
		if hasattr(fn, '__class__'):
			name = f"{fn.__class__}_{fn.__name__}"
		else:
			name = f"{fn.__name__}" 
		return f"~/vault/checkpoint_{name}"

	def write(fn, *args, **kwargs):
		"""
		Write a checkpoint file. 
		Intended to be used as a decorator.
		"""
		def wrapper(*args, **kwargs):

			## Execute command
			ret = fn(*args, **kwargs)
			
			## checkpoint
			filename = Checkpointer.gen_name()
			with open(filename) as f:
				pickle.dump(f, (args, kwargs))
			log.debug(f"Checkpointed: {filename}")
			return ret

		return wrapper


	def read(fn, *args, **kwargs):
		"""
		Read the last checkpoint and return the args, and kwargs.
		If the read fails, than the passed arguemnts are used by default.
		"""
		filename = Checkpointer.gen_name(fn)
		if not os.isfile(filename):
			log.error(f"Checkpointer failed: {filename}")
			return args, kwargs

		with open(filename) as f:
			cp_args, cp_kwargs = *pickle.load(f)
			log.debug(f"Checkpoint read successfully: {filename}")
		return cp_args, cp_kwargs




	







