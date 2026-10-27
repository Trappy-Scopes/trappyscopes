# scripts/debug

Diagnostics you run **on the scope**, after something went wrong.

The problems this lab actually hits — a run that stopped mid-split, an
experiment that would not sync, a camera that would not open — leave their
evidence in the kernel ring buffer and the systemd journal, not in
`experiment.yaml`. That evidence is gone on the next reboot, or when the
journal rotates. This collects it while it still exists.

## Quick start

```bash
python3 scripts/debug/collect_diagnostics.py
```

With the two arguments that matter when an offload failed:

```bash
python3 scripts/debug/collect_diagnostics.py \
    --exp-dir ~/data/M1__YB__2026_10_27__..._a1b2c3 \
    --server  slurmnas.igc.gulbenkian.pt
```

| Flag | Effect |
|---|---|
| `--exp-dir PATH` | adds the directory listing, sizes, `.policy.*` markers, and the tails of `rclone.log` and `sync.yaml` |
| `--server HOST` | adds DNS, ping and route to the offload target. Discovered from config if omitted |
| `--no-server` | skip every network reachability test |
| `--out DIR` | bundle parent directory (default `~/diagnostics`) |
| `--no-tar` | leave the directory, skip the tarball |
| `--timeout N` | per-command timeout, seconds (default 30) |

## Output

```
~/diagnostics/diag_<scopeid-or-host>__<stamp>/
    REPORT.md          triage first, then every command with its output
    index.json         same data, machine-readable
    raw/<slug>.txt     one file per command, untruncated
    config/            the scope's config, secrets redacted
~/diagnostics/diag_<scopeid-or-host>__<stamp>.tar.gz
```

Copy the tarball off the scope and attach it wherever the analysis is
happening. It is self-contained.

The bundle is named for the **scopeid** (`M1`, `M2`, ...) read from the config's
top-level `name:`, falling back to the hostname, and timestamped in the usual
house format — so bundles from eight scopes collate and sort without renaming.

`--out` is **absolute on purpose.** `Experiment.__init__` does
`os.chdir(self.exp_dir)`, so any shell with an experiment open is already
sitting inside it, and a relative default would quietly drop the bundle — full
`dmesg` and two journals included — into the experiment directory, where ExpSync
would then ship it to the file server as data. Pass `--out .` when attaching it
to an experiment is what you actually want.

## Reading it

**Start at the Triage section of `REPORT.md`.** It is a short list, most severe
first, and every line names the raw file it came from — so nothing has to be
taken on trust.

**If you are an LLM or a script:** read `REPORT.md` top to bottom. It is sized
for that: each command inlines a bounded number of lines, and the two large
captures (full `dmesg`, and the journal for this boot and the previous one) are
referenced by path rather than inlined, so the report stays readable without
swallowing a megabyte of kernel log. Open `raw/<slug>.txt` only when a finding
points you there. `index.json` carries the return code, duration and line count
for every check if you would rather navigate programmatically.

**An empty Triage section is not a clean bill of health.** It usually means the
diagnostic commands themselves did not run. Check `index.json` for non-zero
return codes first.

## What it looks for

Decoded rather than grepped, where decoding is possible — `vcgencmd
get_throttled` is reported bit by bit, because `0x50005` tells you nothing at a
glance.

- **Power** — under-voltage now and since boot, frequency capping, throttling,
  soft temperature limit, kernel voltage messages
- **Camera** — libcamera frontend timeouts and dequeue-timer expiries, CMA
  allocation pressure, enumeration failures, a missing `imx477_scientific.json`
- **Storage** — disks past 85%, filesystem errors, USB resets under load,
  drives whose `DISC-GRAN` is zero so every `fstrim` since deployment has been
  a no-op
- **Network** — repeated ethernet link-downs (one is the normal boot
  transition), interfaces with no carrier, NetworkManager devices not connected
- **System** — OOM kills, failed units, a clock that is not NTP-synchronised

Plus, uninterpreted: full `dmesg`, the journal for this boot and the previous
one, boot history, the reboot record, `config.txt`, the libcamera pipeline
config, process and memory snapshots.

## Design constraints

**No framework imports.** Nothing from `expframework/`, `hive/` or `core/`. This
has to run when the framework is exactly what is broken, and on a scope whose
repo state is unknown. Standard library only.

**Nothing is fatal.** A missing binary, a denied permission or a command that
hangs is recorded as such and collection continues. Every command is timed out.
A partial bundle is worth far more than a traceback.

**Configs are copied; secrets are not.** The scope's configuration lands in
`config/`, because almost every sync or device fault is explained by it and a
bundle is useless weeks later if the config has since been edited. Every
`password` / `token` / `*_key` / `secret` **value** is replaced by whether it was
set — `<redacted: set>`, `<redacted: EMPTY>`, `<redacted: PLACEHOLDER, never
configured>`. Whether a credential is configured at all is the diagnostic fact,
and it survives redaction; the value does not. Matching is on the key name, so
`username`, `server` and `protocol` are preserved. `rclone.conf` is included on
the same terms if present.

This matters because the bundle is built to be attached to tickets and chats. A
verbatim copy would publish the file-server password to everyone it reaches.

## Permissions

Most checks run unprivileged. On images with `kernel.dmesg_restrict=1`, or a
journal the user cannot read, those sections will be empty and the report will
say `needs root; sudo -n unavailable`. Re-run with `sudo` if you need them:

```bash
sudo python3 scripts/debug/collect_diagnostics.py
```

`sudo -n` is attempted automatically, but only when a command's output looks
permission-denied, and only its success is accepted — so an unattended run can
never block on a password prompt, and a failed escalation never overwrites the
real output.

## Extending it

Add a row to `GROUPS` in the script:

```python
("slug", "Title shown in the report", "shell command", 25),
```

The last field is how many lines to inline in `REPORT.md`; `0` means capture to
`raw/` but do not inline. Collection, raw files, `index.json` and the report are
all generic over this table — nothing else needs touching.

To add a finding, add a detector to `triage()`. It receives the collected output
by slug and returns `(level, title, detail, slug)`, where `level` is
`CRITICAL`, `WARN`, `UNKNOWN` or `OK` and `slug` names the raw file the reader
should check. Prefer decoding a field over counting a regex, and make sure a
healthy scope produces no warnings — a check that cries wolf trains people to
skip the section.
