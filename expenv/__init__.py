"""
Experiment environments (EXPENV).

An experiment environment is the namespace the Trappy-Scopes CLI drops you
into: what hardware has been constructed, what tools are exposed, and what
has already been printed by the time you get a prompt. Which one you get is
declared in the scope configuration:

	config:
	  startup_recipie: freestyle

A recipe is a module exposing `build(config, namespace=None) -> dict`. The
dict it returns is the namespace. Callers pass the console's own globals
(`vars(__main__)`) as `namespace`, and the recipe fills that dict in place, so
`scope`, `exp` and the user tools become genuinely top-level names in the
interactive session -- and startup scripts run against that same dict. A
script function that later rebinds a global (`global exp; exp = ...` in a
create_exp()) therefore rebinds the console's name too, not a copy of it.

Recipes are functions, not scripts, on purpose. The previous design
`exec()`-ed a file into `main.py`'s globals, which meant the environment
could not be selected, parameterised or tested, and any ordinary `import`
that touched it re-ran the whole thing in a fresh namespace.

Shipped recipes:

	freestyle  full assembly + experiment environment + tools (the default)
	raw        constructs the ScopeAssembly and nothing else, near-silently
"""

import logging as log
from importlib import import_module


DEFAULT_RECIPE = "freestyle"

## Recipes that predate this package, mapped to their replacement so existing
## trappyconfig.yaml files on the scopes keep working untouched.
LEGACY_RECIPES = {
	"core.startup": "freestyle",
}


def resolve(name):
	"""
	Turn a `startup_recipie` config value into an importable module path.

	Accepts a short name ("raw"), a legacy value ("core.startup"), or a full
	dotted path to any module exposing `build(config)`.
	"""
	name = (name or DEFAULT_RECIPE).strip()
	name = LEGACY_RECIPES.get(name, name)

	if "." not in name:
		return f"expenv.recipes.{name}"
	return name


def build(config=None, recipe=None, namespace=None):
	"""
	Build and return the experiment environment namespace.

	config:    the scope configuration. Loaded from TrappyConfig if not given.
	recipe:    override the recipe named in the configuration.
	namespace: the dict to fill in place, normally vars(__main__). A fresh
	           dict if not given.
	"""
	if config is None:
		from core.permaconfig.config import TrappyConfig
		config = TrappyConfig().get()

	if recipe is None:
		try:
			recipe = config["config"]["startup_recipie"]
		except (KeyError, TypeError):
			recipe = DEFAULT_RECIPE

	path = resolve(recipe)
	log.info(f"Building experiment environment: {recipe} ({path})")

	try:
		module = import_module(path)
	except ImportError as e:
		log.error(f"Experiment environment not found: {recipe} ({path}) :: {e}")
		raise

	if not hasattr(module, "build"):
		raise AttributeError(
			f"Experiment environment `{path}` does not define build(config)."
		)

	## AI Generated -- recipes outside this package may predate `namespace`;
	## their returned dict is merged in afterwards, as before.
	import inspect
	if "namespace" in inspect.signature(module.build).parameters:
		return module.build(config, namespace=namespace)
	built = module.build(config)
	if namespace is None:
		return built
	namespace.update(built)
	return namespace
