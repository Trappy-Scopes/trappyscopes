


class Cluster:

	def __init__(self, iplist):
		self.cluster = ParallelSSHClient(iplist, user='trappyscope', password='chlamy')	