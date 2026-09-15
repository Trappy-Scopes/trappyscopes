# ExpSync rework — two legible copies, policies, rclone

**AI Generated** — design note, Claude (Anthropic), 2026-09-15. **All three
chunks are now built** — see *Build order* at the end for status and for
what landed differently than designed.

Revised twice during review. The organising principle is the **two-copy
model** (§1), not a per-call `remove_source` flag.

Grounded in a real deployment run (`MDev__YB__2026_09_04__23hh_19mm__
test_experimentscripted_run_coin_toss__603ed0bb24`) after this session's
fixes got `exp.sync_dir()` working end-to-end for the first time. Findings
from that run are cited inline rather than assumed.

---

## 0. What the current system actually does

Verified against the live experiment, not from reading intent:

- `.sync` is written **once** by `set_sync_logfile()` (only if absent):
  `syncid:7f7e189bec, 2026-09-15 14:59:19.339047`.
- It is appended to **only when `remove_source=True`**, one bare line per
  moved item: `logs.yaml, 2026-09-15 15:09:37.847495`.
- Its docstring claims it is "used for logging" and "to maintain the
  filetree". Neither is true in the default (copy) path.
- `sync_dir()` filters dotfiles (`file.startswith(".")`), which is the
  *only* reason `.experiment`, `.git/`, `.gitignore` and `.sync` itself
  survive a move.
- In move mode it excludes exactly three names: `expstate.pickle`,
  `experiment.yaml`, `sessions.yaml` — one blunt mode applied to
  everything, with a hardcoded exception list.

---

## 1. The two-copy model

**Goal: two copies of the experiment, both legible.** Neither side should
ever be a pile of orphaned bytes that needs the other side to make sense.

This replaces `remove_source` as a per-call argument with a per-file
**disposition**, determined by what the file *is*. One `sync_dir()` call
does both things at once:

| Class | Disposition | Why |
|---|---|---|
| **Manifest** | **Copy** (re-copy on every change) | The experiment's identity and record. Both sides need it to be legible. Small, so repeated copying is cheap. |
| **Data** | **Move** (transfer, then delete locally) | Big and bulky. Moving is the point — it frees space on the acquisition machine. |

**This matches the real acquisition workflow**: acquire a data file,
transmit it to free space, repeat — data flies out continuously during the
experiment, not once at the end. Meanwhile `experiment.yaml` is synced at
the start and re-synced whenever fields update. Because manifests are
*copied*, this needs no special handling: **rsync/rclone versioning takes
care of it — the more recent copy overtakes the previous one.** That is
the whole resolution to "the same manifest file gets synced repeatedly".

**Consequence — the local side becomes a stub.** Once data has moved out,
local holds the complete manifest and no (or fewer) data files. It stays
fully functional: you can keep acquiring into it, and the next sync moves
the new data out too.

**Only the stub is declared** (§2). The server-side copy needs no
declaration — "more original" is deliberately left undefined. One
declaration, on the depleted side, is enough.

---

## 2. Policies — `ExpPolicy`

A **policy** is a durable declaration about an experiment that must be
detectable **without parsing `experiment.yaml`**. Two emissions per
declaration:

1. **An event in the experiment's event chain** — the full record, in the
   normal log, with session/timestamp provenance.
2. **A marker file in the file structure** — so reading an experiment
   surfaces it immediately, at `os.path.exists()` cost.

Convention: `.policy.<name>`, so one cheap `glob(".policy.*")` enumerates
every active policy with **zero parsing**. The *filename* carries the
signal; the file *content* is a **`TSEvent`** — so the declaration is
automatically time-tagged with `eid`/`sid`/`scopeid`/`dt`/`machinetime`,
the same shape as every other event in the system.

**Declarable at any time**, not only during a sync. When a policy is
declared while an experiment is open, a copy of the same event is also
appended to the experiment's event chain; the marker file stands on its own
otherwise.

```
.policy.stub            # this copy's data has been moved out
.policy.contaminated    # the experiment's course/data changed materially
```

**`stub`** — declared on the local copy once its data has been moved to the
server. Answers "why does this experiment have no data files?" instantly.

**`contamination`** — a worked second example, as raised: a contamination
declaration means the experiment's course changed completely, or a major
structural change was imposed on the nature of the data. Anything doing
minor operations on the experiment must take that into account first —
which is exactly why it needs to be visible without a full parse.

### Policy scope — a subtlety that affects sync classification

**Policies are not all the same kind of thing**, and this determines
whether they get copied:

| Policy | Scope | Synced? |
|---|---|---|
| `stub` | **Per-copy** — a property of *this* copy, not of the experiment | **Never copied.** Copying `.policy.stub` to the server would make the full copy falsely declare itself a stub. |
| `contaminated` | **Per-experiment** — true of the experiment everywhere | **Always copied.** Both copies must carry it. |

Scope is **binary** — per-copy or per-experiment, no third case. The sync
classifier (§4) must honour it; getting this wrong silently corrupts the
meaning of both copies.

### Policies are declared in config, not in code

**Decided:** the set of known policies — name, scope, and a human
description written into the emitted `TSEvent` — lives in `TrappyConfig`,
as an **expand** field (`TrappyConfig.expanded(...)`, **not** `leaf()`), so
a lab-wide manifest can add policies without disturbing whatever a device
declares for itself:

```yaml
Experiment:
  policies:
    stub:
      scope: copy          # per-copy -> never synced
      description: "Data files have been moved to the file server; this copy retains only the manifest."
    contaminated:
      scope: experiment    # per-experiment -> always synced
      description: "The experiment's course or data structure changed materially. Take into account before any further operation."
```

Adding a policy is then a config change, not a code change. **This needs a
row in the README's "Expanded config fields" table when built** — that
table is the authoritative record of which fields expand, and its own text
requires new expand fields to be registered there.

---

## 3. Auth — decided

**Credentials stay in `trappyconfig.yaml`**, passed to rclone as backend
flags / environment variables at call time (`RCLONE_CONFIG_<REMOTE>_*`).
One source of truth, still plaintext, no second credential store to keep
in step. No `rclone config` file, no SSH-key migration.

---

## 4. File classification

The three-name exception list is replaced by explicit classification.

### Where the manifest is defined

**Decided:** in `TrappyConfig`, as an **expand** field — same reasoning as
policies (§2). Not hardcoded in `ExpSync`, not hardcoded on `Experiment`:

```yaml
Experiment:
  sync:
    manifest:              # copied, never moved
      - .experiment
      - experiment.yaml
      - sessions.yaml
      - expstate.pickle
      - logs.yaml
      - event_edits.yaml
      - filetree.yaml
      - sync.yaml
      - .gitignore
      - .git/
      - scripts/
```

Expanded, so a lab manifest can add entries without disturbing a device's
own list — which directly answers the planned **config folder**: when that
lands it is one config line, in whichever layer owns it, with no code
change. Also needs a README expand-table row when built.

**Data** is *not* a second list — it is driven by the **same patterns as
`Experiment.git_tracking.exclude`** (confirmed). One list, two consumers:
if it is too big for git, it is data, and it moves. `ExpGit` already
generates each experiment's `.gitignore` from that same field
(`_write_gitignore()`), so the three stay in step by construction rather
than by discipline.

### Manifest — always copied, never moved

| File | Written by | Note |
|---|---|---|
| `.experiment` | `Experiment.new()` | **Identity marker.** `list_all()`/`list_all_eids()` qualify a directory as an experiment by its presence. Currently protected only *incidentally*, by the dotfile filter. |
| `experiment.yaml` | `new()`, rewritten at `close()` | Re-copied whenever it updates |
| `sessions.yaml` | `new()`, `_log_session()` | |
| `expstate.pickle` | `close()` | |
| `logs.yaml` | `create_yaml_logger()` | **Held open by a `RotatingFileHandler`** for the life of the experiment — see the bug below |
| `event_edits.yaml` | lazily, `_log_edit()` | Same open-handler property |
| `filetree.yaml` | `generate_filetree()` | git-tracked; regenerated before every commit |
| `sync.yaml` | ExpSync (§6) | git-tracked ledger |
| `scripts/` | `copy_payload()` | Script *provenance* — the record of what code ran |
| `.gitignore` | ExpGit | Generated from `git_tracking.exclude` |
| `.git/` | ExpGit | **Copied** — decided, so the remote copy keeps version state. Carries a real hazard, below. |
| `.policy.contaminated` | ExpPolicy | Per-experiment scope (§2) |

### Data — moved

Bulk acquisitions (video, images) — driven by
`Experiment.git_tracking.exclude`, as above.

### Explicitly never synced

| File | Why |
|---|---|
| `.policy.stub` | Per-copy scope (§2) — copying it would make the full server copy falsely declare itself a stub |
| rclone `--log-file` output | Raw transport diagnostics (§7); gitignored, disposable |

That is the complete list. Everything else is either manifest or data.

### `.git/` — copying is not merging

Decided to copy, to maintain state on both sides. The hazard, stated
plainly: **a file-level copy of `.git/` is not a merge.** If anything ever
commits on the server copy, the next stub → server sync overwrites those
commits with no conflict, no warning, no trace. Divergence is silently
resolved in favour of whoever synced last.

Two ways to live with it:

- **(a) Declare local authoritative.** The server copy's `.git/` is a
  read-only mirror; nothing ever commits there. Requires no new
  infrastructure, only the invariant — and it matches reality, since the
  acquisition machine is where work happens.
- **(b) `git push` to a bare repo on the NAS** instead of copying `.git/`.
  Technically the correct primitive — git already solves repository syncing
  and *detects* divergence instead of overwriting it. **But it requires
  additional infrastructure**, assessed below.

**Decided: (a)**, with the invariant written down. **(b) is shelved** — not
rejected on merit, but deferred until the server copy genuinely needs to be
committed to. Its costs are recorded below so the decision can be revisited
without re-deriving them.

#### What (b) would actually cost

Assessed because it is not obvious from the outside:

- **Git must exist on the NAS.** `git push` over SSH runs
  `git-receive-pack` *on the remote machine*, so SSH transport needs
  Synology's **Git Server** package installed and SSH enabled. A `file://`
  remote avoids NAS-side software entirely — but needs a filesystem mount,
  which is precisely what §5 removes, so it undoes the rclone win.
- **Per-experiment provisioning.** Each new experiment needs its own bare
  repo created remotely and its own git remote configured. Copying `.git/`
  has no equivalent step.
- **A second transport.** rclone copies files; it does not speak the git
  wire protocol. Git traffic would travel over a different channel than
  data traffic — two transports to configure and keep working, rather than
  one.

The per-experiment provisioning and the split transport are the real costs
here, more than the package install.

### The dotfile filter must be replaced, not kept

Today `sync_dir()` filters `file.startswith(".")`, which is doing invisible
classification work — it is the only reason `.experiment` and `.git/`
survive a move today. Under explicit classification that filter must be
**removed**, not layered on top: leaving it in place would mean
`.experiment`, `.git/` and `.gitignore` are declared manifest and then
silently never synced, so the server copy would never be a legible
experiment at all.

### Unclassified files — copied and tracked, no warning

**Decided:** anything matching neither the manifest list nor the data
patterns is **copied and recorded in the ledger** like any other transfer.
No warning is emitted — an unclassified file is a normal case, not a
problem to flag.

In effect there are only two dispositions, not three: the data patterns
decide what **moves**, and everything else — listed manifest or not —
**copies**. The manifest list's real job is therefore to state what must
*never* be moved even if a data pattern would otherwise match it, rather
than to enumerate everything that syncs.

### Three live bugs this classification fixes

All confirmed in the real run, all caused by the current move-everything
default:

1. **`logs.yaml` was moved.** It is held open by a `RotatingFileHandler`.
   `--remove-source-files` unlinks it while that descriptor is still open,
   so every subsequent log record writes into an orphaned inode and is
   **silently lost**. `event_edits.yaml` has the identical problem.
2. **`filetree.yaml` was moved** — git-tracked, so the repo now shows
   `D filetree.yaml`; and it is regenerated before every commit, so a moved
   copy goes stale immediately.
3. **`scripts/cointoss.py` was moved** — git-tracked (`D scripts/
   cointoss.py`), and it is the provenance record of what code ran. Moving
   it off the experiment defeats its purpose.

Under the two-copy model all three are manifest → copied → bugs gone,
rather than being patched by lengthening an exception list.

---

## 5. rclone — what it removes, and `ionice`

Every painful thing debugged this session was a symptom of one root cause:
**the OS-level mount**.

| Problem today | With rclone |
|---|---|
| `platform.system()` branch for `mount_addr` | gone — no mount point exists |
| `sudo mount` / share must be mounted first | gone — rclone connects per-command |
| `mkexpdir()` + `sudo mkdir -p` fallback | gone — rclone creates remote dirs during transfer |
| `sudo` anywhere in the transfer path | gone — writes happen as the authenticated remote user |
| `openrsync` vs GNU rsync flag drift | gone — one binary, same flags everywhere |
| "Permission denied" as a local mount puzzle | becomes a NAS-side ACL question, where it belongs |

`ExpSync.mount()`, `mkexpdir()`, `mount_addr` and `_sync_prefix()`'s `sudo`
handling all become dead code.

### `ionice` — different axes, do not conflate

`ionice` throttles **local disk I/O priority** so a sync does not compete
with an experiment still writing to the same disk. rclone's `--bwlimit`
throttles **network bandwidth**. Not substitutes. Proposed combination:

- `--bwlimit` — caps network throughput, cross-platform, and supports
  schedules (`--bwlimit "08:00,512k 22:00,off"`), which is strictly more
  than `ionice` gave us.
- `--transfers` / `--checkers` — caps concurrency, the main lever on local
  disk read pressure.
- **Keep the `sync_prefix` config mechanism** (built this session) so Linux
  can still wrap rclone in `ionice -c2 -n4`. rclone is just a command; the
  prefix applies to it exactly as it did to rsync. **This is the only thing
  that genuinely replaces `ionice`** — which is why that work survives the
  migration unchanged.

### Protocols — closed, informational only

Synology exposes SMB, NFS, SFTP, FTP/FTPS, WebDAV, an rsync daemon, and
S3 via MinIO. rclone has native backends for `smb`, `sftp`, `ftp`,
`webdav`, `s3` — **not** NFS or the rsync daemon (NFS would mean mounting
it and using the `local` backend, reintroducing the mount we are removing).
No operations proposed here; the protocol should simply be a config field
so it can change without a design change.

---

## 6. `sync.yaml` vs `filetree.yaml` — the overlap audit

Asked for directly. There **is** real overlap, and it is worth being
precise about where.

| | `filetree.yaml` | `sync.yaml` |
|---|---|---|
| Kind | **Snapshot** — regenerated wholesale | **Ledger** — append-only |
| Answers | "What is here now, and where else does it exist?" | "What happened during transfers?" |
| History | Free, via git (`git log -p filetree.yaml`) | Intrinsic — it *is* history |
| Updated | Before every git commit | On every transfer |

**The overlapping field is `location`.** Both could carry "where does this
file live". The resolution: **`location` belongs to `filetree.yaml` only**
— it is current *state*, which is exactly what a snapshot is for, and git
already versions it.

**What justifies `sync.yaml` existing at all** is the set of facts that
leave *no trace in any snapshot*:

- A manifest file copied five times because it kept updating looks
  identical in every `filetree.yaml` snapshot — but it is five ledger
  entries.
- Failures, retries, partial transfers.
- Transfer-specific facts: bytes moved, destination URL, remote name,
  `syncid`, duration.
- Transfers that happen **between** commits — `filetree.yaml` only updates
  at commit points, so anything in between is invisible to it until the
  next commit.

So they are complementary, not redundant — **provided `location` is not
duplicated into the ledger as a "current location index"**. The ledger
records *events*; current location is derived state and lives in the
snapshot.

**Decided: keep both**, with `location` living only in `filetree.yaml`.
The alternative considered and rejected was collapsing into
`filetree.yaml` + git history alone, which would have cost failure/retry
history and sub-commit granularity.

---

## 7. What replaces `.sync`

Four candidate styles:

| Option | Fits? |
|---|---|
| **(a)** `self.log("file_synced", ...)` into `experiment.yaml`'s events | `experiment.yaml` is only flushed at `close()` — a crash loses the record of a sync that already physically happened. Disqualifying. |
| **(b)** `create_yaml_logger` stream | Durable per record, but it is a **held-open handler** — exactly the trap §4's bug #1 identified. Ironic and disqualifying. |
| **(c)** `YamlProtocol` append list (`sync.yaml`) | Matches the **fixed** `sessions.yaml`: load-modify-dump, no open fd, durable immediately, git-diff-friendly, YAML as requested. |
| **(d)** rclone `--log-file` | Raw transport log — bytes, retries, errors. |

**Recommendation: (c) as the ledger, plus (d) alongside**, answering
different questions:

- `sync.yaml` — *semantic*: what moved/copied, when, by which session, with
  what disposition. Git-tracked, manifest class.
- rclone `--log-file` — *diagnostic*: raw transfer detail for debugging a
  failure. Gitignored, disposable.

**Record shape:** `TSEvent`-derived, so entries carry
`scopeid`/`mid`/`sid`/`dt`/`sessiontime`/`machinetime`/`attribs` for free
and stay schema-compatible with every other event in the system. Note
`TSEvent.__init__` nests `attribs` correctly, while `ExpEvent.__init__`'s
no-arg `super().__init__()` flattens it (the known bug under your separate
review) — the ledger should construct `TSEvent` directly to avoid
inheriting that.

```yaml
- type: file_synced
  scopeid: MDev
  sid: 7f7e189bec
  dt: 2026-09-15 15:09:37.847495
  attribs:
    path: data/acq_0001.mp4
    disposition: moved        # moved | copied
    destination: eyespot:2026_09_15/MDev__.../data/acq_0001.mp4
    bytes: 1048576
    md5: 9f2c4e...            # harvested from rclone, not recomputed -- see §8
    syncid: 7f7e189bec
```

**`.sync` itself: removed entirely** (decided). It never was a log, and the
"marked for sync" flag it really provided is not needed — `sync.yaml`'s
presence carries that meaning. `set_sync_logfile()` and both `.sync`
write sites go with it.

---

## 8. Git bridge, and the DVC seam

The move-sync currently fights `ExpGit` — confirmed live:

```
 M .sync
 D filetree.yaml
 D logs.yaml
 D scripts/cointoss.py
```

`close()`'s auto-commit would record those as **deletions**, when they were
relocations. Under the two-copy model this largely dissolves: those three
are manifest → copied, never deleted → no `D` entries. What remains is data
files, which are already gitignored, so they never appear in git status at
all.

Remaining bridge work:

1. `filetree.yaml` gains `location` (§6) — so each commit snapshots what
   existed and where it lived.
2. `sync.yaml` is manifest-class and git-tracked, so `git log -p sync.yaml`
   is the readable history of data movement.
3. Stub declaration is a policy event **and** a commit — the moment an
   experiment becomes a stub is visible in its own git history.

### The DVC seam — what is actually missing

A `.dvc` pointer is conceptually hash + size + remote. Taking those in
turn:

- **Remote — already have it.** DVC's remote is configured once, not per
  file, and ours is well-defined (the rclone remote + destination). Nothing
  missing here.
- **Size — already have it.** Recorded per ledger entry.
- **Hash — the only real gap.** Two notes: DVC uses **md5**, so md5 is the
  pragmatic choice over sha256; and the hash should be **harvested from the
  transport, not computed separately**. rclone already reads every byte and
  tracks checksums natively (`rclone lsjson --hash`, `--checksum`), so the
  marginal cost is ≈ 0. Only where a backend cannot supply one does it
  become a genuine extra read — and that case should be config-gated rather
  than paid by default.

**This is an rclone-only benefit, and therefore gated on chunk B.** rsync
reports no content hash at all — its rolling checksums are internal to the
delta algorithm and never surfaced; `--checksum` is the only way to get
one and costs a full extra read on both sides. Note also that compression
and hashing are **orthogonal**: `--no-compress` affects bytes in transit
only and has no bearing on hash availability. (Compression is off by
default either way — rsync does not compress without `-z`, and rclone does
not compress unless the remote is explicitly wrapped. The `--no-compress`
flag removed on 2026-09-15 was both redundant and unsupported by macOS's
`openrsync`.)

**One honest caveat against over-claiming this seam:** DVC stores content
**content-addressed** (`files/md5/<2>/<rest>`), while this design writes a
**human-legible mirror** at the experiment's own path structure — which is
the entire point of "two legible copies" (§1). So recording a hash keeps
the door open for *identification and verification*, but a later DVC
adoption would still face a layout difference; it is not purely additive.
Worth knowing now rather than discovering later.

---

## Decisions taken (2026-09-15 review)

| # | Decision |
|---|---|
| §1 | Two-copy model: manifests **copied**, data **moved**. No `remove_source` argument. |
| §2 | `.policy.<name>` marker files, content is a `TSEvent`. Declarable at any time; event also appended to the chain when an experiment is open. |
| §2 | Scope is **binary** — per-copy (`stub`, never synced) or per-experiment (`contaminated`, always synced). |
| §2 | Policies declared in `TrappyConfig` as an **expand** field, with descriptions. |
| §3 | Credentials stay in `trappyconfig.yaml`, passed to rclone at call time. |
| §4 | Manifest list lives in `TrappyConfig` as an **expand** field — so the future config folder is a config line, not a code change. |
| §4 | Data patterns driven by the **same** field as `git_tracking.exclude`. One list, three consumers (`.gitignore`, git, sync). |
| §4 | `.git/` is **copied**, with local declared authoritative. |
| §5 | Protocol selection: informational only, no work. |
| §6 | Keep **both** `sync.yaml` and `filetree.yaml`; `location` lives only in `filetree.yaml`. |
| §7 | `.sync` **removed entirely**. |
| §8 | **DVC integration deferred.** Hash recording is not built now. If added later it must be **md5 harvested from rclone at ≈0 cost** — never a separate read, and never at the cost of transfer speed. Since rsync surfaces no hash at all, this cannot predate chunk B regardless. |
| §4 | Dotfile filter **removed** when classification lands, not kept alongside it. |
| §4 | Unclassified files are **copied and tracked, no warning**. Two dispositions only: data patterns move, everything else copies. |
| §4 | `.git/` copied under a local-authoritative invariant; bare-repo push rejected for now on infra cost. |

**No open design questions remain.**

---

## Build order

Three independently shippable chunks. **A is the one to do first** — it
fixes three live bugs, needs no rclone, and both other chunks build on its
classification.

| | Chunk | Contents | Status |
|---|---|---|---|
| **A** | **Classification** | Manifest/data lists in config (expand fields); copy-vs-move disposition replacing `remove_source`; remove the dotfile filter; delete `.sync` and `set_sync_logfile()` | **Done** 2026-09-15 |
| **B** | **rclone migration** | Replace mount+rsync; delete `mount()`, `mkexpdir()`, `mount_addr`, the `sudo` path; `--bwlimit`/`--transfers` | **Done** 2026-09-15 |
| **C** | **Ledger + policies** | `sync.yaml` ledger; `ExpPolicy` + `.policy.*` markers; `location` in `filetree.yaml` | **Done** 2026-09-15 |

### Landed differently than designed, or learned while building

- **A third disposition, `skip`, was necessary.** The design had two
  (copy/move). But `rclone.log` must be gitignored *and* never synced, and
  git_tracking.exclude is the same field that decides what **moves** -- so
  listing it there would have shipped the local diagnostics log to the
  server as data. `Experiment.sync.never` is checked *before* the data
  patterns; per-copy `.policy.*` markers resolve to `skip` by scope. This
  is the first real cost of "one list, three consumers", and it is
  ordering, not a second list.
- **The ledger append is lock-guarded.** `sync_dir()` transfers inside a
  ThreadPoolExecutor; the default `sync_max_threads=1` is serial, but the
  parameter is caller-settable and two workers would otherwise drop each
  other's entries via load-modify-dump.
- **md5 harvesting was not built** -- deferred with DVC, per the decision
  table. rclone can supply it at ≈0 cost when wanted.
- **rclone must be installed on every scope.** `ExpSync.configure()`
  deactivates sync with an actionable error if it is missing, rather than
  failing per transfer. This is a real deployment step: the rsync path is
  gone.
