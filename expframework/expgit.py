"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

Optional per-experiment git tracking -- see the ".git (optional -- git
repository of the experiment)" line already in Experiment's own docstring
(expframework/experiment.py), documented as an intended feature and never
built until now. Mirrors ExpSync's shape: a configure()/active class flag
read once from config, and per-instance setup called explicitly from
Experiment.__init__ (the same non-cooperative mixin-init pattern
ExpSync already uses -- not a super() chain rewrite, see
docs/notes/experiment_architecture_and_actions.md).

Deliberately local-only -- nothing here ever pushes anywhere. A commit
either happens at open (the baseline) or is triggered explicitly:
Experiment.close() logs one tagged with the current session id, or a
script can call exp.git_commit() itself directly. Large binary media
(video, images -- exactly what this codebase's own top-level .gitignore
already excludes) is kept out of the experiment's own repo via a
generated .gitignore, checked on every commit via `git add -A`
(core.gitutil.commit_all()) -- not committed and filtered out after the
fact.

Since that heavy media is deliberately never committed, git history alone
can't show how the experiment's files evolved across sessions. This class
calls self.generate_filetree() (Experiment.generate_filetree(), see
expframework/experiment.py) right before every commit -- so `git log -p`
on filetree.yaml *is* the human-readable history of what files existed
and changed, even for the excluded ones. Generation itself deliberately
lives on Experiment, not here -- ExpGit only knows when to call it.
"""

import os

from core.bookkeeping.session import Session
from core.gitutil import init_repo, commit_all
from core.permaconfig.config import TrappyConfig


class ExpGit:
	active = False
	exclude = []

	def configure(scopeconfig):
		"""AI Generated -- same calling convention as ExpSync.configure():
		called once at boot with the materialised config dict."""
		block = TrappyConfig.optional_block(scopeconfig, "Experiment", "git_tracking")
		if block is None:
			ExpGit.active = False
			return
		ExpGit.active = True
		## AI Generated -- read via expanded(), not block.get(): this same field
		## also drives ExpSync's move-vs-copy classification, and the two must
		## resolve it identically or a layered lab config could have git ignoring
		## a pattern that sync still treats as manifest. Falls back to the block's
		## own value if TrappyConfig.current isn't set (bare/test construction).
		if TrappyConfig.current is not None:
			ExpGit.exclude = list(TrappyConfig.current.expanded("Experiment", "git_tracking", "exclude") or [])
		else:
			ExpGit.exclude = block.get("exclude", [])

	def __init__(self, exp_dir):
		"""AI Generated -- called explicitly from Experiment.__init__ with
		self.exp_dir, same explicit-call pattern ExpSync uses.
		Whether tracking is actually on for THIS experiment is stored as
		an instance attribute (self._git_active), seeded from the global
		ExpGit.active config default but independently switchable per
		experiment afterward via enable_git_tracking()/
		disable_git_tracking() -- e.g. one experiment opted into tracking
		on the spot shouldn't turn it on for every other experiment in
		the process, and vice versa."""
		self._git_dir = exp_dir
		self._git_active = ExpGit.active
		if self._git_active:
			self._git_start()

	def _write_gitignore(self, exclude=None):
		"""AI Generated -- (re)write this experiment's own .gitignore.
		Only overwrites an existing one if `exclude` is explicitly given
		(enable_git_tracking(exclude=...) on an already-tracked
		experiment) -- otherwise leaves whatever's already there alone
		and only creates it if missing."""
		gitignore_path = os.path.join(self._git_dir, ".gitignore")
		if exclude is not None or not os.path.exists(gitignore_path):
			with open(gitignore_path, "w") as f:
				f.write("\n".join(exclude if exclude is not None else ExpGit.exclude) + "\n")
		return gitignore_path

	def _git_start(self, exclude=None):
		"""AI Generated -- the actual init-repo-and-commit work, shared by
		__init__ (config-driven) and enable_git_tracking() (on the spot).

		The commit message matters here, not just whether a commit
		happens: init_repo() only returns True the very first time (a
		real "tracking started" event). On every later call the repo
		already exists, but there's usually still something to commit
		anyway (at minimum, _log_session() -- called just before this in
		__init__ -- already appended a new entry to sessions.yaml) --
		that's a real reopen/on-the-spot-enable, not a second "started",
		so it's tagged with the session id like close()'s commit is, not
		mislabeled as the original baseline."""
		self._write_gitignore(exclude)
		just_created = init_repo(self._git_dir)
		message = "Experiment tracking started" if just_created else f"Session {Session.current.name}: experiment tracking (re)started"
		self.generate_filetree()  # AI Generated -- Experiment.generate_filetree(), see module docstring
		commit_all(self._git_dir, message)

	def enable_git_tracking(self, exclude=None):
		"""AI Generated -- turn on git tracking for THIS experiment right
		now, even if Experiment.git_tracking.active wasn't set in config
		(or was, and this is just an explicit no-op confirmation).
		Per-instance -- doesn't touch the global config default or any
		other experiment. Idempotent: safe to call on an already-tracked
		experiment (e.g. to swap in a different `exclude` list).
		`exclude`, if given, overwrites THIS experiment's own .gitignore
		only -- the shared ExpGit.exclude default used by every other
		experiment is untouched."""
		self._git_active = True
		self._git_start(exclude)

	def disable_git_tracking(self):
		"""AI Generated -- stop auto-committing for THIS experiment (close()
		no longer commits, git_commit() becomes a no-op). Doesn't touch
		the repo or its history, just stops adding to it -- symmetric
		with enable_git_tracking(), same enable/disable pairing
		convention as expframework/protocol.py's
		enable_shortcuts()/disable_shortcuts()."""
		self._git_active = False

	def git_commit(self, message):
		"""AI Generated -- explicit, caller-triggered commit of whatever's
		changed in this experiment's own repo (respecting its
		.gitignore). No-op, returns False, if git tracking isn't active
		for this experiment. Never pushes -- see module docstring."""
		if not getattr(self, "_git_active", False):
			return False
		self.generate_filetree()  # AI Generated -- Experiment.generate_filetree(), see module docstring
		return commit_all(self._git_dir, message)
