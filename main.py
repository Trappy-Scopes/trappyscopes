#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Trappy-Scopes CLI entry point.

The experiment environment is built by the recipe named in the scope
configuration (`config.startup_recipie`) and returned as a namespace, which is
merged into this module's globals. Since `python -i main.py` runs this file as
`__main__`, those names -- `scope`, `exp`, and the user tools -- become the
top-level names of the interactive session.

See expenv/__init__.py for the available environments.
"""

## Parsed first: core.argparser handles the flags that must work before any
## configuration exists (--install on a fresh machine, --intro, --loc, ...)
## and exits for them. build() below needs trappyconfig.yaml.
import core.argparser  # noqa: F401

from expenv import build

globals().update(build())
