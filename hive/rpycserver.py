import rpyc
import threading
from rpyc.utils.server import ThreadedServer
from rpyc.cli.rpyc_classic import ClassicServer
import time
from rpyc.core.service import SlaveService

from core.permaconfig.sharing import Share
from rpyc.core.service import ClassicService
from rpyc.utils.server import ThreadedServer

class Service_(ClassicService):
	...

class RpycServer(ClassicService):
	

	## ------------------------ Singleton template ---------------------------
	## All objects
	roll = {}

	### Server utils
	server = \
	ThreadedServer(Service_, port=18812, hostname="0.0.0.0", 
				   protocol_config={
				   "allow_public_attrs": True,  # Expose all public attributes
				   "allow_all_attrs": True,    # Allow access to all attributes
				   'import_custom_exceptions': True,
				   "allow_pickle" : True
				   })

	rpycserver_thread = None
	__stop_server_flag__ = False
	## ----------------------------------------------------------------------

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


	#def __run_server__():
	#	RpycServer.start()

	#	while not RpycServer.__stop_server_flag__:
	#	close()

	def start_rpycserver():
		RpycServer.__stop_server_flag__ = False
		RpycServer.rpycserver_thread = threading.Thread(target=RpycServer.__start_server__)
		RpycServer.rpycserver_thread.daemon = True  # Daemonize thread
		RpycServer.rpycserver_thread.start()

	def stop_rpycserver():
		paRpycServerss


	#def _rpyc_getattr(self, name):
	#	# allow all other attributes
	#	return getattr(self, name)