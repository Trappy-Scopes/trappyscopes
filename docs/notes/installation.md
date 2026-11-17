# Detailed installation instructions

Target: Raspberry Pi 4B, Raspberry Pi OS Bookworm (64-bit), branch `dev`.
This is the sequence used on the `dev` bench Pi (`ctrlcmd`, November 2026).
When the bench finds a step that fails, fix the step here.

## Locked versions

| What | Version | Why |
|---|---|---|
| Python | 3.11 (the system Python) | apt's picamera2 and libcamera are built for it |
| picamera2 | 0.3.31, from apt (`python3-picamera2=0.3.31-1`) | the camera stack |
| numpy | 1.26.4, in the venv | apt's `simplejpeg` (used by picamera2) needs numpy 1.x |

The locks live in `pyproject.toml` and `hardware-profiles/raspberrypi/`.
Change them in both places together.

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

# 5. Install trappyscopes and the hardware profile
cd ~/trappyscopes
~/trappyvenv/bin/python main.py --install
```

Step 5, in order:

1. `pip install -e .`: trappyscopes as an editable package, with the
   dependencies in `pyproject.toml`.
2. `uv` is installed into the venv if missing.
3. Hardware profiles are selected (`raspberrypi` matches through
   `/proc/device-tree/model`).
4. `uv pip install --python ~/trappyvenv/bin/python -r hardware-profiles/raspberrypi/requirements.txt`
5. `sudo apt-get install -y fim tree rsync rclone`
6. `sudo apt-get install -y python3-picamera2=0.3.31-1`, then
   `sudo apt-mark hold python3-picamera2`.

See [Hardware profiles](hardware_profiles.md) for what each package is for.

## Check

```bash
~/trappyvenv/bin/python -c "import numpy, picamera2; print(numpy.__version__)"   # 1.26.4
apt-mark showhold                                                                # python3-picamera2
rclone version | head -1                                                         # >= 1.60 (SMB backend)
groups | grep -c dialout                                                         # 1: needed for the Picos
```

## Notes

- System `pip` refuses to install (PEP 668). Always use `~/trappyvenv/bin/pip`
  or `~/trappyvenv/bin/python -m pip`.
- `source ~/trappyvenv/bin/activate` is optional; the installer passes the
  interpreter to `uv` explicitly.
- `pip install --user` packages (in `~/.local`) come after the venv and before
  apt's packages in the search path. A `~/.local` numpy 2.x breaks picamera2
  on the system Python; inside the venv, the venv's numpy 1.26.4 wins.
- To move a lock: `sudo apt-mark unhold python3-picamera2`, then change
  `pyproject.toml` and `hardware-profiles/raspberrypi/` together.
- macOS (development only): the same steps without apt. `native` packages
  come from brew, and `apt_only` is skipped. Use Python 3.11 or 3.12, because
  numpy 1.26.4 has no 3.13 wheels.
