


class CodeExchange:

	def __init__(self, device):
		self.device = device

	def read(self):
		x = self.device.readline(timeout=15)
		print(x)

		if x.startswith(">>>"):
			x = x.replace(">>>>", "")
			exec(x.replace(">>>", ""))
