"""
pyVISA
https://instrumentkit.readthedocs.io/en/latest/intro.html#
pymeasure
https://pypi.org/project/easy-scpi/
"""

from rich import print

class pyVISA:

	def __init__():
		self.pyvisa_rm = pyvisa.ResourceManager()
		print(self.pyvisa_rm.list_resources())

	def open(self, name='GPIB0::14::INSTR')
		self.devide = self.pyvisa_rm.open_resource()
		print(my_instrument.query('*IDN?'))