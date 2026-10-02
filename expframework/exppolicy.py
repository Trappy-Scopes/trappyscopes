"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

`ExpPolicy` -- durable declarations about an experiment that must be
detectable **without parsing experiment.yaml**. See
docs/notes/sync_rework.md §2.

Each declaration emits two things:

1. **A marker file**, `.policy.<name>`, so one `glob(".policy.*")`
   enumerates every active policy at `os.path.exists()` cost -- no YAML
   parse, no Experiment object, no framework import. `ExpPolicy.of(path)`
   does exactly that for an experiment directory nobody has opened.
2. **An event in the experiment's chain**, when one is open -- the normal,
   session-tagged record.

The marker file's *content* is a `TSEvent`, so the declaration carries
`scopeid`/`sid`/`dt`/`machinetime` for free and is schema-compatible with
every other event in the system. `TSEvent` is constructed directly rather
than `ExpEvent`: ExpEvent's no-arg `super().__init__()` flattens `attribs`
onto the top level instead of nesting it (a known, separately-tracked bug).

Policies are **declared in config**, not in code -- `Experiment.policies`,
an expand field, so a lab-wide manifest can add policies without
disturbing what a device declares for itself. Two shipped by default:

- `stub` (scope: **copy**) -- this copy's data has been moved to the file
  server; only the manifest remains here. **Never synced**: it describes
  one particular copy, so copying it would make the full server-side copy
  falsely declare itself a stub.
- `contaminated` (scope: **experiment**) -- the experiment's course or data
  structure changed materially. **Always synced**: it is true of the
  experiment everywhere.

Scope is binary; there is no third case.
"""

import glob
import os

import yaml

from core.tsevents import TSEvent
from core.permaconfig.config import TrappyConfig

MARKER_PREFIX = ".policy."

## AI Generated -- used when config declares nothing, so the two policies the
## sync model itself depends on always exist.
DEFAULT_POLICIES = {
	"stub": {"scope": "copy",
			 "description": "Data files have been moved to the file server; "
							 "this copy retains only the manifest."},
	"contaminated": {"scope": "experiment",
					  "description": "The experiment's course or data structure changed "
									  "materially. Take into account before any further operation."},
}


class ExpPolicy:

	MARKER_PREFIX = MARKER_PREFIX
	registry = dict(DEFAULT_POLICIES)

	def configure(scopeconfig=None):
		"""AI Generated -- same calling convention as ExpSync/ExpGit.configure():
		called once at boot. Reads `Experiment.policies` as an expand field so a
		lab manifest can add policies without replacing a device's own."""
		if TrappyConfig.current is None:
			return
		declared = TrappyConfig.current.expanded("Experiment", "policies") or {}
		merged = dict(DEFAULT_POLICIES)
		merged.update({name: dict(spec) for name, spec in declared.items()})
		ExpPolicy.registry = merged

	def scope_of(name):
		"""'copy' (per-copy, never synced) or 'experiment' (per-experiment,
		always synced). Unknown policies default to 'experiment' -- the
		conservative choice, since the alternative silently withholds a
		declaration from the other copy."""
		return ExpPolicy.registry.get(name, {}).get("scope", "experiment")

	def marker_name(name):
		return f"{MARKER_PREFIX}{name}"

	def of(exp_dir):
		"""AI Generated -- active policy names for an experiment directory,
		without opening it or parsing experiment.yaml. This is the whole point
		of the marker-file convention: a directory scan, nothing more."""
		return sorted(os.path.basename(p)[len(MARKER_PREFIX):]
					  for p in glob.glob(os.path.join(exp_dir, f"{MARKER_PREFIX}*")))

	def read(exp_dir, name):
		"""The declaration record (the TSEvent that was written), or None."""
		path = os.path.join(exp_dir, ExpPolicy.marker_name(name))
		if not os.path.exists(path):
			return None
		with open(path) as f:
			return yaml.load(f, Loader=yaml.Loader)

	## ---- instance side: mixed into Experiment ----------------------------

	def declare_policy(self, name, **attribs):
		"""AI Generated -- declare `name` on this experiment, now. Writes the
		marker file and, since an experiment is open by definition here, also
		appends the same event to its chain. Declarable at any time, not only
		during a sync. Idempotent: re-declaring rewrites the marker with a
		fresh timestamp rather than erroring."""
		spec = ExpPolicy.registry.get(name, {})
		record = TSEvent(kind="policy_declared",
						  attribs={"policy": name,
								   "scope": ExpPolicy.scope_of(name),
								   "description": spec.get("description"),
								   **attribs})

		path = os.path.join(self.exp_dir, ExpPolicy.marker_name(name))
		with open(path, "w") as f:
			yaml.dump(dict(record), f, default_flow_style=False, sort_keys=False)

		self.log("policy_declared", attribs={"policy": name,
											 "scope": ExpPolicy.scope_of(name),
											 **attribs})
		return path

	def revoke_policy(self, name):
		"""Remove the marker and log it. Returns True if one was there."""
		path = os.path.join(self.exp_dir, ExpPolicy.marker_name(name))
		existed = os.path.exists(path)
		if existed:
			os.remove(path)
		self.log("policy_revoked", attribs={"policy": name, "was_active": existed})
		return existed

	def policies(self):
		"""Active policy names on this experiment."""
		return ExpPolicy.of(self.exp_dir)

	def has_policy(self, name):
		return os.path.exists(os.path.join(self.exp_dir, ExpPolicy.marker_name(name)))
