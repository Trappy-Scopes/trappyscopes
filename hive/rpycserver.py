import rpyc
import threading
from rpyc.utils.server import ThreadedServer
from rpyc.cli.rpyc_classic import ClassicServer
import time
from rpyc.core.service import SlaveService

from core.permaconfig.sharing import Share

from rpyc.core.service import ClassicService
class RpycServer(ClassicService):
	
	## All objects
	roll = {}

	def __getitem__(key):
		return RpycServer.roll[key]

	def __setitem__(key, value):
		RpycServer.roll[key] = value

	def on_connect(self, conn):
		print(f"Client connected :: {Share.scopeid}.")

	def on_disconnect(self, conn):
		print(f"Client dis-connected :: {Share.scopeid}.")

	# Expose all attributes and methods dynamically for both objects
	def __getattr__(self, name):
		if name in RpycServer.roll:
			return RpycServer.roll[name]
		else:
			raise AttributeError(f"{name} not found!")

	def get_roll():
		return RpycServer.roll


class _RpycServer(SlaveService):
	"""
	Interface to launch and manage RPyC Server within the assembly scope.

	Uses the RPyc classic mode.
	"""
	def classmethod():
		print("Heyo!")
		return "Heyo!"
	def __init__(self):
		self.rpycserver = None
		self.rpycserver_thread = None

	def __start_server__(self):
		# = ClassicServer.run()
		self.rpycserver = ClassicServer(port=18812, hostname="0.0.0.0", 
									protocol_config={
									"allow_public_attrs": True,  # Expose all public attributes
									"allow_all_attrs": True,    # Allow access to all attributes
									'import_custom_exceptions': True,
									"allow_pickle" : True
									})
		self.rpycserver.start

	def start_rpycserver(self):
		self.rpycserver_thread = threading.Thread(target=self.__start_server__)
		self.rpycserver_thread.daemon = True  # Daemonize thread
		self.rpycserver_thread.start()

	def close_rpycserver(self):
		pass


	#def _rpyc_getattr(self, name):
	#	# allow all other attributes
	#	return getattr(self, name)