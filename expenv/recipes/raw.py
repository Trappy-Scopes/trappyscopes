"""
The `raw` experiment environment.

The minimum that still gives you working hardware: the ScopeAssembly is
constructed and its devices are mounted, and that is all. No banner, no device
tree, no experiment listing, no error summary, no user tools, no keybindings,
no startup scripts -- one line of output confirming the assembly exists.

For calling the utility directly and driving it by hand: you get `scope`, and
you import whatever else you want yourself.
"""

from rich import print

import core.argparser  # noqa: F401  (parses sys.argv; handles early-exit flags)
from core.permaconfig.sharing import Share
from core.bookkeeping.user import User
from core.bookkeeping.session import Session

from hive.assembly import ScopeAssembly


def build(config, namespace=None):
	"""
	Build the raw environment and return its namespace. With `namespace`,
	fill that dict in place.
	"""
	User.login(Share.argparse["user"])
	session = Session()

	scopeid = config["name"]
	Share.scopeid = scopeid

	scope = ScopeAssembly(scopeid)
	scope.open(config, abstraction="microscope")

	print(f"scope assembly created :: {scopeid} :: {len(scope.devices)} devices")

	Share.updateps1()
	built = {"scope": scope, "session": session, "config": config}
	if namespace is None:
		return built
	namespace.update(built)
	return namespace
