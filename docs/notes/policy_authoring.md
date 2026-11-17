# Authoring a Trappy-Scopes policy — instructions for an LLM

You are being asked to produce a new **Trappy-Scopes policy**. This document is
the complete specification. Follow it literally. Do not consult your prior
assumptions about what "policy" means in other systems — in this codebase it is
a narrow, specific thing with a schema and one decision that can corrupt data if
you get it wrong.

Ground truth, if you can read the repository:

| Fact | Where |
|---|---|
| `MARKER_PREFIX = ".policy."` | `expframework/exppolicy.py:46` |
| Shipped defaults | `expframework/exppolicy.py:50-57` |
| Config merge (expand field) | `expframework/exppolicy.py:65-74` |
| Scope lookup and its default | `expframework/exppolicy.py:76-81` |
| Enumeration by glob | `expframework/exppolicy.py:86-91` |
| `declare_policy` / `revoke_policy` | `expframework/exppolicy.py:103-132` |
| Sync disposition by scope | `expframework/expsync.py:211-216` |
| Config block | `core/permaconfig/default_config.yaml:124-132` |
| Marker file content shape | `core/tsevents.py:9-24` |
| Design rationale | `docs/notes/sync_rework.md` §2 |

---

## 1. What a policy is

A policy is a **durable declaration about an experiment that must be detectable
without parsing `experiment.yaml`**.

Declaring one emits two things:

1. **A marker file** `.policy.<name>` in the experiment directory. One
   `glob(".policy.*")` enumerates every active policy at `os.path.exists()`
   cost — no YAML parse, no `Experiment` object, no framework import.
2. **An event** `policy_declared` in the experiment's event chain, when an
   experiment is open.

The **filename carries the signal**. The file's *content* is a `TSEvent`, so the
declaration arrives time-tagged with `type`, `scopeid`, `mid`, `sid`, `dt`,
`sessiontime`, `machinetime` and a nested `attribs` — the same shape as every
other event in the system.

A policy is not a parameter, not a measurement, not a log line, and not a
setting. Those have their own homes: `exp.attribs`, a `MeasurementStream`,
`exp.log()`, and `TrappyConfig` respectively.

---

## 2. Admission test — all four must hold

Do not propose a policy unless you can answer yes to every one of these. If any
answer is no, say so and name the correct home instead.

1. **Durable.** It stays true indefinitely once declared, not for the duration
   of an operation. *Transient → an event, not a policy.*
2. **Boolean.** Its mere existence is the whole signal. Values may ride along in
   `attribs`, but the fact must stand without reading them. *Needs a number to
   mean anything → a measurement stream.*
3. **Consequential to a reader who has parsed nothing.** Someone doing a bare
   directory scan must do something *different* because of it. *Nothing changes
   → a note.*
4. **Not already cheap to determine.** If `os.listdir()` on the directory
   already answers the question, the policy is redundant.

---

## 3. Scope — the only decision that can corrupt data

Every policy declares exactly one scope. **The set is binary. There is no third
case.**

```
scope: copy         # a property of THIS physical copy  -> NEVER synced
scope: experiment   # true of the experiment everywhere -> ALWAYS synced
```

### The decision procedure

Ask one question, and write your answer into the justification:

> If this directory were copied verbatim to the file server, would the statement
> still be true **of the copy**?

- **Yes** → `scope: experiment`
- **No** → `scope: copy`

### Why this is the dangerous field

`ExpSync._disposition()` honours scope generically (`expsync.py:214-216`): a
marker whose scope is `copy` is classified `skip` and never transfers; anything
else is copied. Both directions of error are silent and both destroy meaning:

| Error | Consequence |
|---|---|
| Per-copy fact marked `experiment` | The server copy inherits a declaration that is false about it. This is the `stub` disaster: a complete copy on the server declaring itself a stub, so the data looks lost. |
| Per-experiment fact marked `copy` | The declaration never reaches the other copy. The server copy looks clean. Someone analyses contaminated data believing it is sound. |

### The default hazard — write `scope:` explicitly, always

`ExpPolicy.scope_of()` returns `"experiment"` for any name not in the registry
(`exppolicy.py:76-81`). That default is deliberate and conservative — the
alternative would silently withhold a declaration from the other copy — but it
means **a typo in a policy name, or a policy declared without being registered
in config, is silently treated as per-experiment and will be synced.**

Therefore: register the policy in config *before* anything calls
`declare_policy()` with its name, and never omit `scope:`.

---

## 4. Naming

The name becomes the filename suffix after `.policy.`, and `ExpPolicy.of()`
recovers it by stripping that prefix from the basename. So:

- Lowercase ASCII, `[a-z0-9_]+` only.
- No dots (reads as a second extension), no spaces, no slashes, no glob
  metacharacters (`*`, `?`, `[`) — they break the enumeration round-trip.
- An **adjective or past participle** describing the state of the experiment or
  the copy: `stub`, `contaminated`, `aborted`. Not a verb phrase, not a command,
  not a sentence.
- Singular.
- **No negations.** `not_synced` is wrong; invert the policy and name the
  positive condition.
- Must not collide with a reserved name (§7).

---

## 5. Writing the description

The description is copied verbatim into the emitted `TSEvent`'s attribs
(`exppolicy.py:110-114`). It is **data, not a code comment**. Write it for
someone who finds `.policy.<name>` in a directory in three years with no
repository, no framework and no context.

- One or two sentences. Full stops. No markdown, no line breaks.
- **Sentence 1: what is true.** Present tense, declarative. Do not write "this
  flag indicates that…" — state the fact itself.
- **Sentence 2: what the reader must do about it.** This is what earns the
  policy its admission under test 3.

The shipped `contaminated` description is the model:

> "The experiment's course or data structure changed materially. Take into
> account before any further operation."

Fact, then obligation.

---

## 6. What to emit

Produce exactly these four blocks, in this order, and nothing else.

### A — the config block

YAML for `Experiment.policies` in `core/permaconfig/default_config.yaml`, in
house style: comments to the right, aligned, explaining the *why* rather than
restating the key.

```yaml
  policies:
    <name>:
      scope: <copy|experiment>        # <one clause: why this scope>
      description: "<the description from §5>"
```

### B — the scope justification

Three to five sentences. **Apply the §3 copy test explicitly and show your
answer.** State which failure mode the opposite choice would cause. This is
prose for a human reviewer, not a comment in the file.

### C — the documentation row

A row for the scope table in `docs/notes/sync_rework.md` §2:

```
| `<name>` | **Per-copy** / **Per-experiment** — <short gloss> | **Never copied.** / **Always copied.** <one clause of consequence> |
```

### D — the declaration call site

How and where the policy actually gets declared, as a code snippet:

```python
exp.declare_policy("<name>", <attribs that carry useful detail>)
```

State plainly **who declares it and when** — automatically from a specific code
path, or by the operator at the terminal. If automatic, name the function. For
reference, `stub` is declared automatically at `expsync.py:298-299` after a move
that produced at least one relocated file.

---

## 7. Reserved names and the expand hazard

`Experiment.policies` is an **expand** field: `configure()` starts from
`DEFAULT_POLICIES` and applies `dict.update()` per name from the merged config
(`exppolicy.py:71-74`). Layered config files therefore *add* policies without
replacing a device's own — but a downstream layer that reuses an existing name
**overrides it completely**, scope included.

- `stub` and `contaminated` are **reserved**. Never redeclare them in a
  downstream config. A lab manifest that sets `stub: {scope: experiment}` would
  break the two-copy model everywhere it is loaded.
- Do not add your policy to `DEFAULT_POLICIES` in `exppolicy.py`. That dict is
  the floor the sync model itself depends on, which is why it exists in code at
  all. Everything else is config.

---

## 8. Validation checklist

Run every item before emitting. State any you cannot satisfy rather than
emitting anyway.

1. All four admission tests (§2) pass, and you can say why for each.
2. `scope:` is present and is exactly `copy` or `experiment`.
3. You applied the copy test (§3) and wrote the answer into block B.
4. The name matches `[a-z0-9_]+`, is not negated, and is not reserved (§7).
5. The description is one or two plain sentences, states a fact, then an
   obligation, and is comprehensible without the repository.
6. No key in your proposed `attribs` collides with a `TSEvent` field: `type`,
   `scopeid`, `mid`, `sid`, `dt`, `sessiontime`, `machinetime`, `attribs`.
7. You changed **no Python**. If your policy appears to need a code change, your
   scope is wrong — re-derive it. Scope is honoured generically at
   `expsync.py:214-216`; a correct policy needs no new code.
8. You proposed no third scope value.

---

## 9. Worked examples

### Accepted — `aborted` (new)

```yaml
    aborted:
      scope: experiment               # the run ended early wherever it is read
      description: "The acquisition was stopped before its scheduled end. The series is shorter than the experiment parameters declare; do not treat a missing tail as data loss in transfer."
```

Copy test: copied to the server, the run is still one that ended early. Yes →
`experiment`. Marking it `copy` would leave the server copy silently claiming a
complete run, and the shortfall would be misread as a failed transfer.

### Accepted — `stub` (shipped)

Per-copy. Copied to the server, "the data has been moved out of here" becomes
false — the server copy is where the data went. No → `copy`, never synced.

### Rejected — `syncing`

Fails admission test 1. It is true for the duration of an operation, not
indefinitely. Belongs in the transfer ledger `sync.yaml`, which already records
one entry per attempt including failures.

### Rejected — `cell_density_low`

Fails tests 2 and 3. It needs a number and a threshold to mean anything, and a
directory scan cannot act on it. The number belongs in a `MeasurementStream`;
the threshold is an analysis decision, not a property of the experiment.

---

## 10. Do not

- Modify `exppolicy.py`. Policies are declared in config, not in code.
- Modify `_disposition()` in `expsync.py`. It already handles any scope.
- Introduce a scope beyond `copy` and `experiment`.
- Omit `scope:` and rely on the `"experiment"` default.
- Write a description that explains the implementation rather than the fact.
- Emit more than the four blocks of §6.

---

## Appendix — YAML structures

Two distinct documents. You *write* the first; the framework *emits* the second.
Do not hand-write a marker file.

### A. The declaration — `Experiment.policies` in config

Skeleton:

```yaml
Experiment:
  policies:                           # expand field: layers merge per name (§7)
    <name>:                           # [a-z0-9_]+ -- becomes `.policy.<name>`
      scope: copy|experiment          # REQUIRED. Binary. Never omit (§3).
      description: "<fact. obligation.>"   # REQUIRED. Copied verbatim into the event.
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `<name>` | mapping key, `[a-z0-9_]+` | yes | Becomes the marker filename suffix. Reserved: `stub`, `contaminated`. |
| `scope` | `copy` \| `experiment` | yes in practice | Absent falls back to `experiment` (`exppolicy.py:81`) — silently syncable. Always state it. |
| `description` | string | yes | One or two sentences. Read years later without the repo. |

Nothing else is read. `ExpPolicy.configure()` takes the whole mapping per name
(`exppolicy.py:73`), so extra keys survive into the registry but no code
consults them. Do not invent fields expecting behaviour.

As shipped:

```yaml
Experiment:
  policies:
    stub:
      scope: copy                     # per-copy -> never synced; copying it would
                                      # make the full server copy declare itself empty
      description: "Data files have been moved to the file server; this copy retains only the manifest."
    contaminated:
      scope: experiment               # per-experiment -> always synced; true of the
                                      # experiment wherever it is read
      description: "The experiment's course or data structure changed materially. Take into account before any further operation."
```

### B. The emitted marker — `.policy.<name>`

Written by `declare_policy()` as `yaml.dump(dict(TSEvent(...)), default_flow_style=False,
sort_keys=False)` (`exppolicy.py:110-118`). `sort_keys=False` means the key
order below is the order on disk.

```yaml
type: policy_declared                 # TSEvent kind, always this value
scopeid: M1                           # Share.scopeid  -- which microscope
mid: <machine id>                     # Share.mid
sid: <session name>                   # Session.current.name
dt: 2026-10-22 13:42:07.918233        # datetime, dumped as a YAML timestamp
sessiontime: 4821.337                 # float seconds since session start
machinetime: 1792567327918233000      # time.time_ns()
attribs:
  policy: stub                        # the name, repeated inside the record
  scope: copy                         # resolved via ExpPolicy.scope_of() at write time
  description: Data files have been moved to the file server; this copy retains only
    the manifest.                     # PyYAML folds long scalars at ~80 cols
  moved_files: 44                     # any **attribs passed to declare_policy()                     # any **attribs passed to declare_policy()
```

The first seven keys come from `TSEvent.__init__` (`core/tsevents.py:14-23`) and
are identical in shape to every other event in the system. Everything specific
to the policy lives under `attribs`.

Two things worth knowing:

- **There is no `eid` field.** `docs/notes/sync_rework.md` §2 says the marker is
  tagged with `eid`/`sid`/`scopeid`/`dt`/`machinetime`; `TSEvent` has no `eid`.
  The directory name carries the eid, so nothing is lost, but do not write code
  that reads `record["eid"]`.
- **The copy in the event chain has a different shape.** `declare_policy()` also
  calls `self.log("policy_declared", ...)`, which builds an `ExpEvent`, and
  `ExpEvent`'s no-arg `super().__init__()` flattens `attribs` onto the top level
  instead of nesting it (known, separately tracked). So the same declaration
  reads nested in the marker and flat in `experiment.yaml`. Parse them
  differently.

Reading it back is `ExpPolicy.read(exp_dir, name)`, which uses
`yaml.load(..., Loader=yaml.Loader)`. Note that the record above *is*
`safe_load`-able on its own: PyYAML dumps `dt` as a plain YAML timestamp, which
`safe_load` parses back into a `datetime` natively. The full loader is needed
only because `**attribs` is caller-supplied — pass a tuple, a numpy scalar or
any other non-standard type to `declare_policy()` and the marker stops being
safe-loadable. Keep `attribs` values to str, int, float, bool and list.
