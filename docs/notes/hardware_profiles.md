# Hardware profiles

A hardware profile is a folder, `hardware-profiles/<name>/`, that lists what
one kind of machine needs beyond `pyproject.toml`. The installer
(`main.py --install`, see [Detailed installation instructions](installation.md))
applies every profile whose `detect` command succeeds.

## Files

| File | Content |
|---|---|
| `profile.yaml` | `name`, and `detect`: a shell command. Exit 0 means the profile applies. |
| `system.yaml` | Non-Python packages, in three lists (below). |
| `requirements.txt` | Python packages for this machine, installed with `uv pip install`. |
| `setup.sh` (optional) | Replaces all of the above. It is run as-is and nothing else is read. |

Profiles are looked up in three places. A later one replaces an earlier one
with the same name:

1. `hardware-profiles/` in the repository
2. each folder in `config.hardware_profile_dirs`
3. `~/trappyverse/hardware-profiles/`

Versions come from the fleet: the package list each scope records in
`sessions.yaml` (`pypkglist`), compared across all 8 scopes.

## Natives (`system.yaml`)

| List | Installed with | Use for |
|---|---|---|
| `native` | apt on Linux, brew on macOS | tools any OS can have |
| `apt_only` | apt, Linux only | packages tied to the board |
| `conda_forge` | conda-forge; only when asked (always on Windows) | what apt/brew cannot provide |

An entry written `name=version` is a lock: it is installed at that version and
then held (`apt-mark hold`), so `apt upgrade` cannot move it.

### raspberrypi

`detect`: `grep -q 'Raspberry Pi' /proc/device-tree/model`

| Package | List | Used by |
|---|---|---|
| `fim` | native | `core/utilities/fim.py`: terminal image viewer |
| `rsync` | native | config sync: `launcher/utilities/sync_config.py`, through `core/sync.py` `sync()` |
| `rclone` | native | experiment sync: `expframework/expsync.py`, through `core/sync.py` `rclone()`. SMB needs ≥ 1.60 (Bookworm: 1.60.1). |
| `python3-picamera2=0.3.31-1` | apt_only, locked | the camera (`detectors/cameras/rpi_hq_picam2.py`) |
| `python3-av=12.3.0-2+rpt1`, `python3-simplejpeg=1.8.1-1` | apt_only, locked | picamera2's encoders. Named because picamera2's Depends are unversioned, so apt would keep an older copy. |
| `python3-libcamera=0.5.2+rpt20250903-1~bpo12+1` | apt_only, locked | libcamera's Python bindings, at the archive's version alongside picamera2 0.3.31. Not recorded on the fleet. |
| `graphviz` | conda_forge | the `dot` binary. No user now: the `diagrams`/`graphviz` packages were dropped. Only installed when conda-forge is asked for. |

`requirements.txt`:

| Package | Note |
|---|---|
| `numpy==1.26.4` | locked with picamera2 |
| `gpiozero`, `rpi-lgpio`, `smbus2` | for Pi GPIO and I2C. Kept for later use: nothing in the code imports them today, because GPIO and I2C run on the Picos. |

### jetson

`detect`: `test -f /etc/nv_tegra_release`. Natives: `fim`. conda_forge:
`pandoc`, `graphviz`. Python: `Jetson.GPIO`.

## Hardware-specific code in use

| Code | Hardware | Needs |
|---|---|---|
| `detectors/cameras/rpi_hq_picam2.py` | Raspberry Pi HQ camera, through picamera2 and libcamera | the locked apt camera stack; a venv that sees system packages |
| `core/external/pyboard.py` | MicroPython boards over USB serial (`/dev/ttyACM*`) | user in the `dialout` group |
| `hive/processorgroups/micropython.py`: `SerialMPDevice` | the Picos: connect, handshake, `set_time()`, `device_config()`, file sync | same |
| `hive/processorgroups/serialdevice.py`: `SerialDevice`, `FixedVocabSerialDevice` | serial boards that are not MicroPython (e.g. Arduino) | same |
| `core/idioms/devicetree.py` | lists attached serial/USB devices (launcher "Device tree") | `pyserial` |
| `core/installer/mpyfirmware.py` | flashes MicroPython (per-board images, below) and syncs `pico_firmware` (reads its `sync_what.yaml`) | the `RPI-RP2` drive mounted, or picotool |

## Installer functions (`core/installer/environment.py`)

| Function | Does |
|---|---|
| `ensure_python_environment()` | When PEP 668 blocks system pip: offers `~/trappyvenv`, created with `--system-site-packages` |
| `discover_profiles()` | finds profile folders in the three places above |
| `select_profiles()` | keeps the ones whose `detect` exits 0 |
| `plan_profile()` | reads `system.yaml` and `requirements.txt` into a plan |
| `apply_plan()` | runs the plan: `requirements.txt` with `uv pip install --python <venv>`, then `native`, then `apt_only` (Linux), then `conda_forge` if asked |
| `install_native()` | `apt-get install` or `brew install`; holds `name=version` entries |
| `ensure()` | all of the above, in order |

## MicroPython firmware

Which MicroPython build a Pico gets is set in the scope config, not in a
profile:

```yaml
config:
  micropython:
    version: "1.20.0"
    firmware_image: https://micropython.org/resources/firmware/RPI_PICO_W-20230426-v1.20.0.uf2
    firmware_dir: ~/code/Trappy-Scopes/pico_firmware
    boards:                        # per board, by board.name in its board.py
      pico_kp:
        version: "1.24.0"
        firmware_image: https://github.com/pimoroni/pimoroni-pico/releases/download/v1.24.0-beta2/picow-v1.24.0-beta2-pimoroni-micropython.uf2
```

- **Default:** stock MicroPython 1.20.0 for the Pico W, from micropython.org
  (the fleet's version). Used by every board without a `boards` entry.
- **Per board:** a board that needs another build names it under `boards`. The
  keypad Pico runs Pimoroni's build (`picow v1.24.0-beta2`), so it has an entry;
  flashing it with the default would replace that.
- **Flashing** (launcher: MicroPython > Flash): reads the board's version,
  `board.name` and circuit; picks the board's entry or the default; skips a
  board already at that version unless told to reflash; downloads the image
  once (asks first) into `~/trappyverse/state/firmware_cache/`; resets the
  board into BOOTSEL; then uses picotool if it is on PATH, otherwise copies the
  `.uf2` to the `RPI-RP2` drive. Bookworm's apt has no picotool, so on a Pi the
  drive must be mounted: a desktop session automounts it, a headless one does not.
- **Files survive a MicroPython flash** (`board.py`, `vault/`, `pumpstate.txt`).
  Sync `pico_firmware` afterwards (MicroPython > Sync), which follows the
  firmware repo's `sync_what.yaml`.
- **Identity:** the device registry (`~/trappyverse/state/device_registry.yaml`)
  keys a board by its USB serial number, which is the chip ID. Flashing does not
  change it; re-register only to refresh the cached version or the role.
