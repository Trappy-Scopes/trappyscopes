# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : November 2026                                                  |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+


"""
AI Generated -- new file, Claude (Anthropic), 2026-11.

Space on the OS card and on the drive holding the experiments folder, as two
bars in one small rich panel.

    from core.utilities.diskspace import disk_panel
    print(disk_panel())                  # experiments folder from the config
    print(disk_panel("/mnt/ssd"))        # or any other path

Each bar is the whole drive in grey with the used part over it, red once it
is more than 90% full. When the experiments folder sits on the OS card, its
bar says so: the experiment drive is then either absent or not mounted.
"""

import os
import shutil

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

GB = 1e9


def experiments_dir():
    """Where Experiment saves runs, from the config: Experiment.exp_dir on
    dev, config.expdir on main. None if the config cannot be read."""
    try:
        from core.permaconfig.config import TrappyConfig
        cfg = TrappyConfig.current
    except Exception:
        return None
    for read in (lambda: cfg.leaf("Experiment", "exp_dir"),
                 lambda: cfg["config"]["expdir"].get()):
        try:
            path = read()
            if path:
                return os.path.expanduser(str(path))
        except Exception:
            pass
    return None


def _existing(path):
    """The path itself, or its nearest parent that exists (a fresh scope may
    not have made the experiments folder yet)."""
    path = os.path.abspath(os.path.expanduser(path))
    while not os.path.exists(path) and path != os.path.dirname(path):
        path = os.path.dirname(path)
    return path


def _bar(frac, colour, width):
    """The whole drive as a grey track, the used part over it in colour."""
    n = max(0, min(width, round(frac * width)))
    return Text.assemble(("█" * n, colour), ("█" * (width - n), "grey30"))


def _gb(x):
    return f"{x / GB:,.0f}" if x >= 10 * GB else f"{x / GB:.1f}"


def _row(label, path, width):
    u = shutil.disk_usage(path)
    frac = u.used / u.total if u.total else 1.0
    colour = "red" if frac > 0.90 else "cyan"
    return (Text(label, style="bold"), _bar(frac, colour, width),
            Text(f"{_gb(u.free)} / {_gb(u.total)} GB free",
                 style="bold red" if frac > 0.90 else ""))


def disk_panel(path=None, title="storage stats", width=24):
    """Two bars: the OS card (/) and the drive holding path (default: the
    experiments folder from the config)."""
    path = path or experiments_dir() or os.getcwd()
    probe = _existing(path)
    on_card = os.stat(probe).st_dev == os.stat("/").st_dev
    grid = Table.grid(padding=(0, 1))
    grid.add_column()
    grid.add_column()
    grid.add_column(justify="right")
    grid.add_row(*_row("OS card", "/", width))
    grid.add_row(*_row("experiments (OS card)" if on_card else "experiments", probe, width))
    return Panel(grid, title=title, subtitle=Text(path, style="dim"), expand=False)
