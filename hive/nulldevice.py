from rich import print

from basedevice import BaseDevice


class NullDevice(BaseDevice):

	def __init__(self, exampledevice):
		self.__class__ = type(exampledevice.__class__.__name__,
								  (self.__class__, exampledevice.__class__),
								  {})

	def __getattr__(self, fn, *args, **kwargs):
		print(f"{self.__repr__()} :: {fn} :: faking it!")
		self.emit_proxy(fn)


if __name__ == "__main__":
	from rich.panel import Panel
	from nulldevice import NullDevice

	nl = NullDevice(Panel("xxx"))
	nl.x()