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

Open:

- The template's `ScopeAssembly:` section is never read: the assembly builds
  from a top-level `devices:` block. The bench config uses `devices:`.
- `scripts/chambertests/keypad_pump_control.py` tells the user to run the
  keypad circuit `pimoroni_rgb_keypad_pumpctrl`; the file is
  `pimoroni_rgb_sparkly_rainbows_cntlr.py`.
- The settings sync never deletes (latest copy wins, both ways): a file
  removed on one side comes back from the other.
- Not bugs: "Couldn't chdir to /mnt/config_server" came from a launcher started
  before the Pi pulled dce7260; mount's "fstab has been modified" hint is noise
  (`/etc/fstab` unchanged since 2024).

- `picotool` is not in Bookworm's apt. Flashing falls back to copying the UF2
  onto the `RPI-RP2` drive, which must be mounted. Check at step 4.
- `hive/assembly.py`: `ScopeAssembly.close()` at exit crashes when no scope was
  built (old bug).

## Todo (2026-11-17)

- [ ] **Install without the menus.** Everything above is manual (launcher
  menus and prompts). Add a scripted path, e.g. `trappyscope --install --yes`
  or flags for each prompt, so a scope can be set up by one command.
- [ ] Minimal config option: "Create configuration file" copies the full
  204-line template; bench step 2 needs one with only `config_server`.
- [x] Fix the template's `config_server.destination: "{date}"`.
- [ ] Finish one `main.py --install` run end to end (running, Claude).
- [ ] Install / setup step 3 through the launcher, by hand (Yatharth, next time).
- [ ] Keypad Pico firmware: a per-board firmware image in `config.micropython`,
  documented, in case a board needs a non-default build (Pimoroni).
- [x] Start the launcher on a fresh machine (`python -m launcher`).
- [x] Install / setup works without a config.

### Step 2–3: configuration (2026-11-17)

`~/trappyverse/trappyconfig.yaml` on the Pi, built from MDev's config (main)
and synced to `config_server/ctrlcmd/`. It sets only what differs from the
defaults: the two Picos (`pico_pumps`, `pico_kp`), `branch: dev`, the venv,
`git_dependencies` (pico_firmware pinned to `main`, protocols), keyboard
shortcuts and `micropython` (1.20.0; firmware image to choose at step 4).
`Experiment.file_server` is left inactive with placeholders.
