from pssh.clients import ParallelSSHClient


class Cluster:

	def __init__(self, hostnames):
		self.cluster = ParallelSSHClient(iplist, user='trappyscope', password='chlamy')

	def exec(self, command):
		