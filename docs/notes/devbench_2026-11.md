# dev bench, November 2026

Setting up `dev` from scratch on one instrument, to test it on hardware. The
fleet stays on `main` (see [restructuring §17](restructuring.md)).

| | |
|---|---|
| Pi | `ctrlcmd`, Raspberry Pi 4 Model B Rev 1.5, 8 GB, user `trappyscope` |
| OS | Raspberry Pi OS Bookworm (Debian 12), kernel 6.6.31, Python 3.11.2 |
| Network | `eth0` 192.168.0.198 (bench LAN, NAS at 192.168.0.248), `wlan0` institute |
| Boards | two Picos: pumps (`2ch_peristat_kitroniks_vx_shield`) and the Pimoroni keypad (`pimoroni_rgb_sparkly_rainbows_cntlr`) |
| Firmware | `Trappy-Scopes/pico_firmware`, the only reference |

## Log

Each entry: what failed, why, and the fix (commit on `dev`).

### Step 1: hardware profile and install (2026-11-17)

| # | Found | Cause | Fix |
|---|---|---|---|
| 1 | `pip install -e .` would refuse the Pi | `requires-python >=3.12`; Bookworm has 3.11, and apt's camera stack is built for it | `>=3.11,<3.13` (25572f9). All of `dev` compiles on 3.11; the 9 files that do not are broken on 3.13 too. |
| 2 | the venv could not see the camera | created without `--system-site-packages`; picamera2/libcamera only come from apt | venv `~/trappyvenv` with system packages (2799f68) |
| 3 | `import picamera2` fails on the Pi's system Python (`numpy.dtype size changed`) | numpy 2.4.6 in `~/.local` (pip `--user`) shadows apt's; apt's simplejpeg needs numpy 1.x | numpy locked at 1.26.4 in the venv (25572f9). `~/.local` left as is. |
| 4 | uv not found after installing it into the venv | the installer looked on `PATH`; an unactivated venv is not on it | look next to the running interpreter (25572f9) |
| 5 | `uv pip install` would refuse | no `VIRTUAL_ENV` and no `.venv`; uv did not know which Python | pass `--python` (25572f9) |
| 6 | apt would keep old av (10.0.0), simplejpeg (1.6.6) and libcamera (0.3.0) | picamera2's Depends are unversioned | pin and hold the whole camera stack at the fleet's versions (d153202, 3cce3e8) |
| 7 | pip would try to build PyQt5 ≥ 5.15.11 | pinned in `pyproject.toml`; the fleet runs apt's 5.15.9; only `gui/` uses Qt | Qt dropped from `pyproject.toml` with 18 unused packages (cb9f42d) |
| 8 | `markdown-it-py` undeclared | imported by `expframework/protocol.py`, installed only through rich | declared (cb9f42d) |
| 9 | `main.py --install` failed on a fresh Pi: `TS_ConfigNotFound` | `main.py` built the experiment environment (which loads the config) before handling `--install`; the installer's profile lookup read the config too | handle CLI flags first; profiles without a config (afe7a48) |
| 10 | no way to start the launcher on a fresh machine | `trappyscope` exists only after `pip install -e .` | `python -m launcher --launcher` (6fb5078) |
| 11 | Install / setup menu crashed without a config, so "Create configuration file" could not be reached | the venv check's `status()` raised `TS_ConfigNotFound` while the panel was drawn | returns "create it first"; steps reordered: config, then venv (6fb5078) |
| 12 | venv shown "(not set)" | `config.venv` only understood conda | plain venvs checked by directory; the running venv can be recorded in the config, comments kept (6fb5078) |
| 13 | settings sync would fail to mount | `/mnt/<share>` does not exist on a fresh Pi | `mount()` creates it (dce7260) |
| 14 | second settings sync in a boot crashed (`mount error(16)`, exit 32) | the share stays mounted; the "already mounted" check searched the exception text, but mount's message goes to the terminal | skip when already mounted (06ed9d3) |
| 15 | first push to a new scope folder failed (`rsync: mkdir ... No such file or directory`) | rsync creates only the last path component | create the remote folder first (06ed9d3) |
| 16 | "Nothing to transfer -- both sides already match" printed after a failed rsync | the message ignored the exit codes | only on success (06ed9d3) |
| 17 | NAS username and password printed in a traceback | on the `mount` command line; `CalledProcessError` shows the command | 0600 credentials file, removed after mount (06ed9d3) |
| 18 | `config_server.destination: "{scope}"` became a folder named `{scope}` | the field was used literally (and `{scope}` is not a template name) | templated like `file_server.destination`; scope ID appended unless placed; template default `""` (671faf4) |
| 19 | a pinned `git_dependencies` entry (`{path, branch}`) would crash the protocol resolver and "Check new features" | both treated every entry as a path | both accept the mapping form (9dc05b7) |
| 20 | Repository utility crashed (`expected 5, got 4`) and could not get `pico_firmware` | `_status()`'s missing-path returns not updated with branch pinning; no clone action | 5 values everywhere; declared repos missing from the machine can be cloned on their pinned branch (ca536c5) |
| 21 | CLI crashed: `KeyError: 'set_wallpaper'` | `TrappyConfig().get()` does not fill a section's missing keys from the template; the compact bench config left keys out | config rebuilt as the full template with the bench values (open: make the template's defaults apply) |
| 22 | Pico replies mangled (`None` -> `''`, `"done"` -> `"d"`) | `.strip("\r\nNone")` strips characters, not a word | strip newlines, drop one trailing `None` line (361fd16) |
| 23 | `main.py` had 10 s to start a circuit | it runs as one raw-REPL command with pyboard's default timeout | 30 s for `exec_main()` only (361fd16) |
| 24 | CLI crashed listing experiments; creating one would fail too | `~/experiments` does not exist on a fresh scope | `list_all()` returns `[]`; `Experiment.new()` creates the directory (96bb2cd, 8ef0d1d) |
| 25 | the keypad Pico would be flashed with stock MicroPython | one global firmware image | `config.micropython.boards.<board.name>` overrides (655a19e); `pico_kp` uses Pimoroni's picow v1.24.0-beta2 |
| 26 | `flash()` gave up on the UF2 drive and asked to check again | it looked once, right after the reset, before the drive was mounted | polls up to 15 s (45d41df) |
| 27 | `./trappyscope` did not start | the repo-root script ran the removed `startup.py`, then `python -i main.py` with the system Python | runs `python -m launcher` with `~/trappyvenv` (f9e3eac) |
| 28 | wallpaper failed: `docs/assets/white_logo.png` missing | `.gitignore` ignored every `*.png`, so the logos were never committed | `docs/assets/*.png` allowed, logos committed (ba15e52) |
| 29 | wallpaper "set" but unchanged | `set_wallpaper()` used gsettings first; Raspberry Pi OS ships it but draws the desktop with pcmanfm | pcmanfm unless GNOME; reaches the desktop session from SSH (ba15e52) |
| 30 | every launch asked about conda-forge (graphviz) and "Proceed?" | Launch normally re-ran the profile install each time; graphviz had no users | runs only until installed; graphviz dropped from the Pi profile (ba15e52) |

Open:

- **Template defaults are not applied.** `TrappyConfig().get()` returns a
  section as the file has it, without the template's missing keys, so a config
  must be a full copy of the template (finding 21). Fix in `TrappyConfig`.
- `main` still has the `strip("None")` reply bug (fixed on `dev`, 361fd16).
- The template's `ScopeAssembly:` section is never read: the assembly builds
  from a top-level `devices:` block.
- `pumpstate.txt` sits at the Pico's root; it belongs in `vault/`. Pumps 1 and
  2 restore from it on every boot (they come back pulsing).
- The firmware cache is `~/trappyverse/state/firmware_cache/`, inside the folder
  the settings sync mirrors: the .uf2 images were uploaded to the config share.
- Flashing without picotool (not in Bookworm's apt) copies the .uf2 to the
  `RPI-RP2` drive, so it needs the drive mounted. Works on the bench because a
  desktop session automounts it; a headless scope would need a manual mount.
- The settings sync never deletes (latest copy wins, both ways): a file
  removed on one side comes back from the other.
- `scripts/chambertests/keypad_pump_control.py` tells the user to run the
  keypad circuit `pimoroni_rgb_keypad_pumpctrl`; the file is
  `pimoroni_rgb_sparkly_rainbows_cntlr.py`.
- `pico_firmware/controllers/pimoroni_rgb_sparkly_rainbows.py` imports
  `picokeypad` and is imported by nothing (the 2024 keypad circuit used it).
- `ScriptEngine` imports a startup script as a module and then executes it, so
  its top level runs twice (keypad_pump_control prints its banner twice).
  Harmless for that script; wrong for one with side effects at load.
- At exit: `ImportError: sys.meta_path is None` from `ScopeAssembly.__del__`,
  and `ScopeAssembly.close()` crashes when no scope was built. Harmless.
- `opencv-python` 5.0 and numpy 2.4.6 in `~/.local` (an old
  `pip3 install --break-system-packages`): pip warns; only the webcam driver
  imports cv2. The venv's numpy 1.26.4 wins inside the venv.
- Not bugs: "Couldn't chdir to /mnt/config_server" came from a launcher started
  before the Pi pulled dce7260; mount's "fstab has been modified" hint is noise
  (`/etc/fstab` unchanged since 2024).

## Todo (2026-11-17)

- [ ] **Install without the menus.** Everything is manual (launcher menus and
  prompts). Add a scripted path, e.g. `trappyscope --install --yes` or flags
  for each prompt, so a scope can be set up by one command.
- [ ] Install / setup step 3 through the launcher, by hand (Yatharth, next time).
- [ ] **Step 5: the link-break diagnosis.** Leads: the over-full flash (fixed
  in step 4) and the reply parsing (fixed on `dev`).
- [ ] Bring the `strip("None")` fix to `main` once the bench has run on it.
- [ ] Make the template's defaults apply in `TrappyConfig` (then a minimal
  config becomes safe; "Create configuration file" could offer one).
- [ ] Move the firmware cache out of `~/trappyverse/` (or exclude it from the
  settings sync); move `pumpstate.txt` into `vault/`.
- [x] Finish one `main.py --install` run end to end (Claude, 17 Nov).
- [x] Per-board MicroPython image (`config.micropython.boards`), documented in
  [Hardware profiles](hardware_profiles.md).
- [x] Fix the template's `config_server.destination: "{date}"`.
- [x] Start the launcher on a fresh machine (`python -m launcher`, `./trappyscope`).
- [x] Install / setup works without a config.

### Step 2–3: configuration (2026-11-17)

`~/trappyverse/trappyconfig.yaml` on the Pi: the full template with the bench
values from MDev's config (main), synced to `config_server/ctrlcmd/`. A compact
file was tried first and failed (finding 21). Bench values: the two Picos
(`pico_pumps`, `pico_kp`), `branch: dev`, the venv, `git_dependencies`
(pico_firmware pinned to `main`, protocols), keyboard shortcuts,
`micropython` (1.20.0 default; `boards.pico_kp` = Pimoroni build),
`set_wallpaper: true`, `Experiment.file_server` on (rclone to the NAS),
and `startup_scripts: [scripts/chambertests/keypad_pump_control.py]`
(the keypad drives the pumps: `create_exp()` -> `connect()` -> `start()`).

### Step 3: the CLI and the scope (2026-11-17)

`trappyscope` runs Launch normally end to end: config check, settings sync,
repository status, then the CLI. Both Picos mount (`pico_pumps`, `pico_kp`)
and `scope.draw_tree()` shows `node`, `pico_pumps` with `pump1`–`pump3` and
`pumpset`, and `pico_kp` with `kp`. `scope.pumpset.state()` and
`scope.kp.health()` answer (keypad: 0 errors, 0 dropped).

Pico firmware as found: `pico_pumps` MicroPython v1.19.1-992 (preview, 2023),
Pico W; `pico_kp` Pimoroni picow v1.24.0-beta2, Pico W. Board names and
circuit ids were already right.

### Step 4: Pico firmware (2026-11-17)

- Both boards backed up to `~/pico_backups/<board>_2026-11-17_1715/`, old
  `/pico_firmware` removed (nested copy included), current firmware synced:
  free flash −116/−132 KB → 228/212 KB.
- MicroPython: `pico_pumps` flashed 1.19.1 (2023 preview) → **1.20.0** (stock
  Pico W, the default); `pico_kp` reflashed with its board entry, **Pimoroni
  picow v1.24.0-beta2**. File systems kept (`board.py`, `pumpstate.txt`,
  `vault/`); the whole `pico_firmware` tree then rewritten again. Registry
  versions refreshed; registration itself is by USB serial (chip ID), unchanged.
- Perfusion defaults (pumps 1, 2): 5 s on / 55 s off, slow speed **0.083**, in
  the 2ch circuit (pico_firmware 270968b) and the host envelope and rehearsal
  script (dev 6abdfaa, main 22823e3). The bench pumps were set and saved
  (`pumpstate.txt`). Aeration (pump 3) unchanged.
- CLI after all of it: both Picos mount; pumps pulse at 0.083; keypad 0 errors.
