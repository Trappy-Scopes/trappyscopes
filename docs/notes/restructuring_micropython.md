# Restructuring: the MicroPython machinery

!!! note "Provenance"
    Written by **Claude** (Anthropic) with Yatharth on 2026-11-17, on the `dev`
    bench (ctrlcmd, see [dev bench](devbench_2026-11.md)). It covers both the
    host side (`hive/processorgroups/micropython.py`, `core/installer/mpyfirmware.py`,
    `core/idioms/devicetree.py`) and the device side (the `Trappy-Scopes/pico_firmware`
    repository).

!!! warning "Status — collecting, no code yet"
    This is the one place for planned MicroPython work. It works in three steps:

    1. collect every item here;
    2. look for conflicts between the items (§5);
    3. only then write code, in the order agreed in §6.

    Items from other notes are copied here with a pointer back. The other note
    stays where it is.

Status marks: ✅ done · ⏳ not started · ✗ decided against.

---

## 0. How it works today

A short reference, so the items below can be read on their own.

- **Boot chain on the Pico:**
  1. `boot.py` writes the root `main.py` if it is missing. That file holds one
     line: `execfile('pico_firmware/main.py')`.
  2. `pico_firmware/main.py` writes `board.py`, `webrepl_cfg.py` and `vault/`
     if they are missing, then imports `board`.
  3. It `execfile`s `pico_firmware/circuits/<board.circuit_id>.py`.
  4. The circuit file imports drivers from the rest of `pico_firmware/`.
- **`board.py`** lives only on the device: `name`, `circuit_id`, and per-board
  settings such as `pump_reverse`.
- **Host side:** `SerialMPDevice` connects, runs `main.py` (`exec_main`, 30 s
  timeout) and handshakes. Every Pico object becomes a scope proxy. Commands
  go over the raw REPL as `print(<command>)`, and the reply is parsed with
  `ast.literal_eval`.
- **Flash and sync:** `mpyfirmware.flash()` installs the MicroPython image (per
  board: `config.micropython.boards`). `mpyfirmware.sync()` copies the firmware
  tree as `sync_what.yaml` says. The sync is incremental (it compares sizes)
  and **never deletes** anything on the device.
- **Storage:** both bench boards are Pico W on littlefs, with 4 KB blocks.
  - Free after the step 4 resync: `pico_pumps` 228 KB, `pico_kp` 212 KB.
  - Stock Pico W builds reserve 848 KB for files. Not checked for Pimoroni's
    build.
  - Firmware that writes logs runs into this limit.

---

## 1. Copy only the files a board uses ⏳ not started

*Research done 2026-11-17. Nothing built.*

### 1.1 The problem

`sync_what.yaml` copies the whole `pico_firmware/` tree to every board: 59
files, 235 KB of source, 16 folders. Each board runs one circuit, which needs
8–13 of those files. The rest takes space the device needs for logs and state.

### 1.2 Is it already solved?

Not in the MicroPython world: every tool there uses a list written by hand.
On the Python side the problem is solved, but none of the tools fit as they are.

| Tool | Finds dependencies from imports? | Fits? |
|---|---|---|
| `mip`, manifest files, Belay | No: dependencies are listed by hand | No |
| `modulefinder` (Python's standard library) | Yes | **Crashed on this repo.** `pico_firmware/` has no `__init__.py` (a namespace package), and modulefinder cannot handle that. |
| modulegraph, pydeps | Yes | Same method as `modulefinder` (scans bytecode) |
| grimp | Yes | Its docs say it expects regular packages |
| importlab | Yes | Tied to pytype and typeshed, built for CPython |
| findimports | Yes | Would work, but the rules below would still have to be added |

**Decision:** write a small walker with `ast` from the standard library (about
150 lines). It only parses the files, so MicroPython modules (`machine`, `rp2`,
`network`) never need to exist on the host. It runs on the Pi or a Mac.

### 1.3 How the walker works

A prototype was run against the repo on 2026-11-17. It was not committed;
this section is enough to rewrite it.

- **Roots:**
  - `boot.py`
  - `pico_firmware/main.py`
  - `pico_firmware/circuits/<circuit_id>.py`

  `circuit_id` is read from the board. `flash()` already reads it, and so does
  the device registry.
- **Edges it follows:**
  - `import a.b.c`, which loads `a`, `a.b` and `a.b.c`;
  - `from pkg import name`, where `name` may be a submodule;
  - relative imports;
  - imports inside functions and inside `try`/`if` blocks (kept on purpose);
  - `execfile("literal")` and `exec(open("literal").read())`.
- **Module search** follows the device's `sys.path` (`''`, `.frozen`, `/lib`). Here
  `''` is the device root, which mirrors the repo root.
- **Anything that does not resolve to a repo file** is taken to be built into the
  firmware (`machine`, `_thread`, `rp2`, `dht`, `ubinascii`, ...).
  - Optional check: compare these names against the board's own
    `help('modules')`.
  - A name that is neither a repo file nor in that list would fail on the
    device. It can be caught before syncing.
- **What it cannot follow:**
  - `execfile` with a computed path;
  - `__import__`;
  - imports the host sends over the REPL.

  It lists all of these. Today the only one is `main.py`'s
  `execfile(f".../{board.circuit_id}.py")`, which is why the circuit file is
  given as a root.
- **A file that fails to parse stops the sync.** A guessed list could leave
  out a file the board needs.

### 1.4 What the repo looks like to it today

- Paths built at runtime: only the circuit `execfile`.
- `__import__` or `importlib`: none.
- Host-sent imports of firmware modules: none. A search of trappyscopes found
  only comments and docstrings.
- Data files shipped in the firmware tree: none. Every `open()` targets files
  that live only on the device (`vault/`, `board.py`, logs, `pumpstate.txt`).

### 1.5 Numbers

Measured with the prototype. Flash is an estimate: whole 4 KB blocks per file
and 2 blocks per folder. It is an upper bound, because littlefs can store small
files inside the folder's own blocks. The real check is `os.statvfs` before
and after.

| What gets copied | Files | Source | Folders | Flash (est.) |
|---|---|---|---|---|
| today (`sync_what.yaml`) | 59 | 235 KB | 16 | ≈512 KB |
| `2ch_peristat_kitroniks_vx_shield` (`pico_pumps`) | 11 | 46 KB | 5 | ≈108 KB |
| `pimoroni_rgb_sparkly_rainbows_cntlr` (`pico_kp`) | 8 | 38 KB | 4 | ≈88 KB |
| largest other circuit (`4ch_drv8833_cleanpump_perfusion`) | 12 | 60 KB | 5 | ≈128 KB |
| smallest (`shelf_beeper_on_power`) | 8 | 11 KB | 4 | ≈64 KB |

So each bench board would get back about 400 KB.

- 23 files (50 KB) are imported by no circuit at all.
- Some of those are REPL or development tools, used by hand rather than by a
  circuit: `dev/firmware-dev.py`, `processor2.py`, `wifi.py`, `dtsync.py`.

### 1.6 Pieces to build

1. The walker, in `core/installer/mpyfirmware.py`.
2. Read `circuit_id` from the board before syncing.
3. An `always:` list in `sync_what.yaml`, for files copied to every board
   whether imported or not. This covers REPL tools and future host-sent
   imports.
4. **Prune:** delete everything under `/pico_firmware` on the device that is not
   on the list.
   - Without this, existing boards keep all 59 files and no space comes back.
   - It must never touch the device's own files (see §5.2).
5. A dry run that prints what would be sent and what would be deleted, then
   asks.
6. A `--full` option that copies the whole tree as today (see §5.4).

---

## 2. Fewer folders on the device ⏳ todo

*Added by Yatharth, 2026-11-17.*

Each littlefs folder takes at least one metadata pair: 2 blocks, 8 KB. The
16 folders synced today take about 128 KB before any file is stored.

| Folder | Files synced | Note |
|---|---|---|
| `pico_firmware/` | 17 | top level (`boot.py` sits at the device root, outside) |
| `actuators/` | 6 | |
| `actuators/lights/` | 2 | |
| `actuators/lights/channels/` | 2 | |
| `bookeeping/` | 1 | one file |
| `circuits/` | 12 | |
| `controllers/` | 4 | |
| `dev/` | 1 | dev tool |
| `dev/tests/` | 1 | dev tool |
| `hive/` | 2 | |
| `idioms/` | 1 | one file |
| `peripherals/` | 2 | |
| `sensors/` | 3 | |
| `sensors/spectrometer/` | 1 | one file |
| `sensors/tandh/` | 1 | one file |
| `sensors/tsl2591/` | 2 | |

The counts were taken from the repo on 2026-11-17. Recount before acting.

Not decided yet:

- Fold the one-file folders into their parent.
- Merge `actuators/lights/channels/` into `actuators/lights/`.
- Move `dev/` out of the synced tree.

Every move changes import paths (`pico_firmware.sensors.tandh.ahtx0`, ...). See §5.1.

---

## 3. Ship `.mpy` instead of `.py` ✗ decided against

*Decided 2026-11-17.*

- **Measured:** `mpy-cross` 1.20 turns the `pico_pumps` file set from 46 KB into
  16 KB.
- **On flash** that saves only about 16 KB, because most files already fit in a
  block or two.
- `boot.py`, `main.py` and circuit files must stay `.py` in any case, because
  they are `execfile`d.
- **Rejected (Yatharth):** we would lose most of the programmability. Files on
  the device could no longer be read or edited in place, from Thonny or the
  REPL.

The device keeps `.py`.

---

## 4. Items already flagged elsewhere

Copied here so that §5 can check them against each other. The source is in
brackets.

### 4.1 Host side (trappyscopes)

- ⏳ **Reply parsing.** The `strip("None")` fix is on `dev` (361fd16) but not on
  `main`. Bring it to `main` once the bench has run on it. [bench log 22,
  todo]
- ⏳ **`device_config()`** (Pico objects report their own config at handshake)
  is on `main` (e48c980) but not in `dev`. [restructuring.md §16.1]
- ⏳ **`main`'s sync does not read `sync_what.yaml`.** A sync from `main` copies
  the stale nested `pico_firmware/pico_firmware/` again. Fleet boards may
  still carry it; check with `mpremote df`. [restructuring.md §16.2]
- ⏳ **The firmware sync never deletes.** See §1.6 item 4.
- ⏳ **The firmware cache sits inside the synced folder.**
  `~/trappyverse/state/firmware_cache/` is under the folder the settings sync
  mirrors, so the `.uf2` images were uploaded to the config share. Move it out
  or exclude it. [bench open items, todo]
- ⏳ **Flashing a headless scope.** Without picotool (not in Bookworm's apt),
  flashing copies the `.uf2` to the `RPI-RP2` drive. That needs the drive
  mounted, which only a desktop session does automatically. [bench open items]
- ⏳ **Step 5:** the keypad↔pump link-break diagnosis is not started. [bench
  todo]
- ⏳ **The light Picos should report their PWM frequency and level count**
  through `get_config()`. This needs a firmware patch on the scopes.
  [restructuring.md §16.1]
- ⏳ **Related items shelved in restructuring.md §15.4:**
  - an Arduino category in `devicetree`;
  - a Pico-based poseidon controller on `SerialMPDevice`.

### 4.2 Device side (pico_firmware)

- ⏳ **`pumpstate.txt` sits at the Pico's root.** It belongs in `vault/`.
  [bench open items]
- ⏳ **`main.py` still has a hard-coded branch for `4_clustcontrol_v1_proto`.**
  Because of it, `beacon.py`, `controllers/rpicontroller.py` and
  `sensors/tandhsensor.py` count as dependencies of every board. That is 3
  files and 2 folders, about 28 KB. Move the branch into its own circuit file.
  [found 2026-11-17]
- ⏳ **Five files fail to parse in any Python version.** All of them would raise
  `SyntaxError` on import:
  - `wifi_.py`
  - `hive/detector.py`
  - `sensors/tsl2591/__init__.py` (Python 2 `print`)
  - `sensors/_remote_sensor_protocol.py` (tabs mixed with spaces)
  - `dev/firmware-dev.py`

  `hive/detector.py` is imported by the spectrometer circuit, so that circuit
  is broken as it stands. [found 2026-11-17]
- ⏳ **`peripherals/lcd.py` reuses the same quote inside an f-string.** CPython
  accepts that only from 3.12 (PEP 701); the Pi's venv runs 3.11. Whether
  MicroPython accepts it is not checked. [found 2026-11-17]
- ⏳ **WiFi is off, but `secrets.py` is copied to every board.** `processor2` and
  `wifi` are commented out in `main.py`, so no board connects. The
  `flag_wifi_connect` and `flag_dt_sync` flags in the default `board.py` do
  nothing. [found 2026-11-17]
- ⏳ **`main.py` writes `webrepl_cfg.py` with a fixed password**, from a public
  repo. WebREPL itself is commented out in `boot.py`. [found 2026-11-17]
- ⏳ **Three logging modules:** `_logger.py` (used by `incubator_proto` and
  the circadian controller), `logger.py` and `logging.py` (used by no circuit).
  Logs are what run out of space, so pick one and give it a size limit or
  rotation. [found 2026-11-17; open question]
- ⏳ **Dead code:** `controllers/pimoroni_rgb_sparkly_rainbows.py` imports
  `picokeypad` and is imported by nothing. [bench open items]
- ⏳ **Stale references:**
  - `scripts/chambertests/keypad_pump_control.py` names the keypad circuit
    `pimoroni_rgb_keypad_pumpctrl`; the file is
    `pimoroni_rgb_sparkly_rainbows_cntlr.py`.
  - The firmware repo's tests point to `host/` files that are not in the repo.

  [bench open items]

---

## 5. Conflicts to resolve before code

First pass, 2026-11-17. Add to it as items are added.

### 5.1 Selective sync and the folder restructure (§1 and §2)

- Selective sync on its own already cuts the folders per board from 16 to 4–5.
  Flattening mostly helps boards that still get the whole tree.
- **Every folder move changes import paths** in the firmware and in any
  board-side copies. The `pico_firmware` repo's `main` is shared by the bench
  and the fleet, so a fleet board picks up the new paths at its next sync.
- **Decide first:** do fleet boards get selective sync too? `main`'s
  `sync_files()` does not read `sync_what.yaml` at all (§4.1).

### 5.2 Prune and the device's own files (§1.6 and `pumpstate.txt`)

- Prune must never delete:
  - root files: `board.py`, `main.py`, `boot.py`, `webrepl_cfg.py`;
  - `vault/`;
  - `pumpstate.txt`;
  - logs.
- If `pumpstate.txt` moves into `vault/` first, and logs go there too, the rule
  becomes simple: prune only under `/pico_firmware`.
- Moving `pumpstate.txt` needs a one-time migration: read the old file if the
  new one is missing.

### 5.3 Selective sync and the files that fail to parse (§1.3 and §4.2)

- Because a parse failure stops the sync, the spectrometer board cannot be
  synced until `hive/detector.py` is fixed. That is intended, but fix the five
  broken files (or delete them) before turning the walker on.
- Run the walker under Python 3.11, the Pi's version. A file that only 3.12
  parses would also stop it.

### 5.4 Selective sync and programmability (§1 and §3)

- `.mpy` was rejected to keep the device editable. In the same spirit, a file
  that was not copied cannot be imported from the REPL to try out, e.g. a
  sensor driver.
- The `always:` list and `--full` keep that possible. Decide which of them is
  the default.

### 5.5 `main.py`'s legacy branch and the walker (§4.2)

- Until the `4_clustcontrol_v1_proto` branch moves into its own circuit file, the
  walker keeps copying its three files to every board.
- Moving it is a firmware change that `4_clustcontrol` boards will pick up.
  Check whether any are still in use.
- The host knows about it too: `launcher/utilities/configure_board.py` lists
  `4_clustcontrol_v1_proto` in `_INLINE_CIRCUIT_IDS` (circuits that live in
  `main.py`, not in `circuits/`). It has to change in the same step.

### 5.6 `dev` and `main` (restructuring.md §17)

- The firmware repo has one `main`, used by both the bench and the fleet.
- Firmware changes made for the bench reach the fleet at the fleet's next
  sync, not at the `dev` → `main` merge of trappyscopes.
- Decide whether `pico_firmware` needs its own `dev` branch while this work
  runs. The bench config already pins `git_dependencies` per branch.

---

## 6. Order of work

*Draft, to be confirmed after §5.*

1. **Firmware clean-up, with no path changes:**
   - fix or delete the five broken files;
   - delete the dead keypad controller;
   - move the `4_clustcontrol` branch into its own circuit;
   - move `pumpstate.txt` into `vault/`, with the migration.
2. **Host:**
   - the walker;
   - the `always:` list;
   - dry run and prune (prune only under `/pico_firmware`);
   - `--full`.

   Measure `os.statvfs` on both bench boards before and after.
3. **Folder restructure (§2),** once §5.1 is decided.
4. **Logging:** one module, with a size limit or rotation, writing under `vault/`.
5. **Carry to the fleet:** the reply-parsing fix, `device_config()`, and selective
   sync if §5.1 says so.
