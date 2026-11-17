"""
`python -m launcher [--launcher]`, run from the repository root.

Starts the launcher on a fresh machine, before `pip install -e .` has created
the `trappyscope` command (Install / setup > 3 does that). Same entry point as
`trappyscope`: bare runs "Launch normally", --launcher opens the menu.

	cd ~/trappyscopes && ~/trappyvenv/bin/python -m launcher --launcher
"""

from launcher import main

main()
