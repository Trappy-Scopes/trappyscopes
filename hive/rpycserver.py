import rpyc
import threading
from rpyc.utils.server import ThreadedServer
from rpyc.cli.rpyc_classic import ClassicServer


class RpycServer:
	"""
	Interface to launch and manage RPyC Server within the assembly scope.

	Uses the RPyc classic mode.
	"""
	def __init__(self):
		self.rpycserver = None
		self.rpycserver_thread = None

	def __start_server__(self):
		self.rpycserver = ClassicServer.run()
		

	def start_rpycserver(self):
		self.rpycserver_thread = threading.Thread(target=self.__start_server__)
		self.rpycserver_thread.daemon = True  # Daemonize thread
		self.rpycserver_thread.start()

	def close_rpycserver(self):
		pass