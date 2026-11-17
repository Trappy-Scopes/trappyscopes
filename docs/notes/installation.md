# Detailed installation instructions

Target: Raspberry Pi 4B, Raspberry Pi OS Bookworm (64-bit), branch `dev`.
This is the sequence used on the `dev` bench Pi (`ctrlcmd`, November 2026).
When the bench finds a step that fails, fix the step here.

## Locked versions

| What | Version | Why |
|---|---|---|
| Python | 3.11 (the system Python) | apt's picamera2 and libcamera are built for it |
| picamera2 | 0.3.31, from apt (`python3-picamera2=0.3.31-1`) | the camera stack |
| av, simplejpeg | 12.3.0, 1.8.1, from apt | what picamera2 0.3.31 runs with on the fleet |
| libcamera | 0.5.2 (`python3-libcamera=0.5.2+rpt20250903-1~bpo12+1`) | released with picamera2 0.3.31; not recorded on the fleet |
| numpy | 1.26.4, in the venv | apt's `simplejpeg` (used by picamera2) needs numpy 1.x |

The locks live in `pyproject.toml` and `hardware-profiles/raspberrypi/`.
Change them in both places together. The versions are the ones recorded on all
8 scopes (`sessions.yaml` → `pypkglist`, fleet_clock_sync runs, 2026-11-16);
M1 and M3 are behind on numpy, and M1 on picamera2.

## Sequence

Run as the scope user (not root).

```bash
# 1. System tools (both ship with Pi OS; listed for minimal images)
sudo apt update
sudo apt install -y git python3-venv

# 2. Code
git clone -b dev https://github.com/Trappy-Scopes/trappyscopes.git ~/trappyscopes

# 3. Python environment; it must see apt's camera packages
python3 -m venv --system-site-packages ~/trappyvenv

# 4. Bootstrap: just enough to start the CLI
~/trappyvenv/bin/pip install -r ~/trappyscopes/bootstrap-requirements.txt

# 5. Start the launcher (the `trappyscope` command does not exist yet)
cd ~/trappyscopes
~/trappyvenv/bin/python -m launcher --launcher
```

In the launcher, open **Install / setup >** and run, in order:

1. **Create configuration file**: copies the default template to
   `~/trappyverse/trappyconfig.yaml`. Then set `name` (the scope ID) and the
   blocks you need, e.g. `config_server` (see below).
2. **Check virtual environment**: offers to record the running venv as
   `config.venv` (`source ~/trappyvenv/bin/activate`).
3. **Install packages + hardware profiles**: answer *n* to conda-forge and
   *y* to "Proceed". The `sudo apt` steps need no password on the scopes.

Afterwards the command exists in the venv: `~/trappyvenv/bin/trappyscope --launcher`
(or `trappyscope --launcher` after `source ~/trappyvenv/bin/activate`).

Without menus: `~/trappyvenv/bin/python main.py --install` runs step 3 directly.

Step 3, in order:

1. `pip install -e .`: trappyscopes as an editable package, with the
   dependencies in `pyproject.toml`.
2. `uv` is installed into the venv if missing.
3. Hardware profiles are selected (`raspberrypi` matches through
   `/proc/device-tree/model`).
4. `uv pip install --python ~/trappyvenv/bin/python -r hardware-profiles/raspberrypi/requirements.txt`
5. `sudo apt-get install -y fim rsync rclone`
6. `sudo apt-get install -y python3-picamera2=0.3.31-1 python3-av=12.3.0-2+rpt1 python3-simplejpeg=1.8.1-1 python3-libcamera=0.5.2+rpt20250903-1~bpo12+1`,
   then `sudo apt-mark hold python3-picamera2 python3-av python3-simplejpeg python3-libcamera`.

See [Hardware profiles](hardware_profiles.md) for what each package is for.

## Config server (settings sync)

```yaml
name: <scope ID>                 # the folder on the server is <destination>/<name>
config:
  config_server:
    active: true
    server: 192.168.0.248        # the NAS on the scope LAN; check the route (see below)
    share: <share>
    destination: <folder>        # used literally: no {date} templating here
    username: <username>
    password: <password>
```

Launcher → **Configuration > Sync configuration file**. It mounts
`//<server>/<share>` at `/mnt/<share>` (`sudo mount -t cifs`), then rsyncs
`~/trappyverse/` with `<destination>/<name>/`. On the bench Pi the default
route is `eth0`, so the NAS's institute address (172.22.50.240) is not
reachable from it; 192.168.0.248 is.

## Check

```bash
~/trappyvenv/bin/python -c "import numpy, picamera2; print(numpy.__version__)"   # 1.26.4
apt-mark showhold                                                                # python3-av, -libcamera, -picamera2, -simplejpeg
rclone version | head -1                                                         # >= 1.60 (SMB backend)
groups | grep -c dialout                                                         # 1: needed for the Picos
```

## Left out of the install

| What | Why | Later |
|---|---|---|
| `trappy-explorer` (analysis and reports, the old `ExpReport`) | optional | separate install |
| Qt: `pyqt5`, `pyqt5-qt5`, `pyqt5-sip`, `pyqtgraph`, `qtconsole`, `qtpy` | used only by `gui/`, which is stale. picamera2 does not need Qt: apt only *recommends* `python3-pyqt5`, apt installs it anyway, and the venv sees it, so `Preview.QT`/`QTGL` still work. Our default preview is `Preview.DRM`. | an optional `gui` extra, if `gui/` is revived |
| `trackpy`, `pims` | used only by `scripts/celltracking/livetrack.py` | install with that script |
| docs-site and unused packages (`markdown`, `pymdown-extensions`, `paginate`, `pathspec`, `mermaid-py`, `diagrams`, `graphviz`, `beepy`, `icalendar`, `imageio-ffmpeg`, `mpremote`, `textual-dev`, `ipython`, `ipywidgets`, `jupyterlab-widgets`, `joblib`, `json-tricks`, `scikit-learn`) | imported nowhere in the code, and on no scope (one or two only on M1) | none |

## Notes

- System `pip` refuses to install (PEP 668). Always use `~/trappyvenv/bin/pip`
  or `~/trappyvenv/bin/python -m pip`.
- `source ~/trappyvenv/bin/activate` is optional; the installer passes the
  interpreter to `uv` explicitly.
- `pip install --user` packages (in `~/.local`) come after the venv and before
  apt's packages in the search path. A `~/.local` numpy 2.x breaks picamera2
  on the system Python; inside the venv, the venv's numpy 1.26.4 wins.
- To move a lock: `sudo apt-mark unhold python3-picamera2` (and the others), then change
  `pyproject.toml` and `hardware-profiles/raspberrypi/` together.
- macOS (development only): the same steps without apt. `native` packages
  come from brew, and `apt_only` is skipped. Use Python 3.11 or 3.12, because
  numpy 1.26.4 has no 3.13 wheels.
