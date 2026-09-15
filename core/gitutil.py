"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

Small, generic GitPython-based helpers for local git provenance and
clone-if-missing -- kept separate from any one feature that needs them
(protocols, the launcher's repository-status utility, ...), per this
codebase's dependency direction: `core` has no dependents inside it, so
anything above it (expframework, launcher) can import from here without
creating a layering cycle (expframework importing launcher directly would
invert the intended direction -- launcher/utilities/repo_sync.py already
uses GitPython the same way, see docs/notes/restructuring.md).
"""

import os

import git


def ensure_cloned(url, path):
	"""Clone `url` into `path` if it isn't already a git repository there.
	Returns True if a clone just happened, False if `path` was already a
	repo. config.git_dependencies already states this url <-> path mapping
	explicitly (see README's "Expanded config fields" table) -- this is
	the one place that actually acts on it, so a dependency that hasn't
	been cloned yet doesn't need a second, separate resolution path (see
	docs/notes/protocols.md §6)."""
	path = os.path.expanduser(path)
	try:
		git.Repo(path)
		return False
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		parent = os.path.dirname(path.rstrip(os.sep)) or "."
		os.makedirs(parent, exist_ok=True)
		git.Repo.clone_from(url, path)
		return True


def permalink_base(remote_url):
	"""https://github.com/<org>/<repo> from either an https or git@ remote
	URL -- so a permalink can be built by string substitution alone, with
	no API call."""
	url = remote_url.strip()
	if url.endswith(".git"):
		url = url[:-4]
	if url.startswith("git@"):
		host, _, path = url[4:].partition(":")
		url = f"https://{host}/{path}"
	return url


def init_repo(path):
	"""AI Generated -- git init `path` if it isn't already a repository.
	Idempotent -- returns True if a repo was actually created, False if
	one already existed, so it's safe to call on every experiment open,
	not just the first. Deliberately does not commit anything itself --
	see commit_all() for that, called separately so a caller can write
	files (e.g. a generated .gitignore) into `path` first."""
	try:
		git.Repo(path)
		return False
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		git.Repo.init(path)
		return True


def commit_all(repo_root, message):
	"""AI Generated -- stage everything changed/new in the repo at
	`repo_root`, respecting its .gitignore, and commit if there's
	anything actually staged. Returns True if a commit happened, False
	if there was nothing to commit -- not an error.

	Uses `git add -A` (repo.git.add(A=True)) rather than
	repo.index.add([repo_root]) -- verified directly that GitPython's
	index.add() does NOT filter a directory path through .gitignore at
	all, and happily walks into .git/ itself. `git add -A` is the actual
	CLI-equivalent operation and correctly skips both."""
	repo = git.Repo(repo_root)
	repo.git.add(A=True)

	if repo.head.is_valid():
		if not repo.index.diff("HEAD"):
			return False
	elif not repo.index.entries:
		return False

	repo.index.commit(message)
	return True


def commit(repo_root, paths, message):
	"""AI Generated -- stage specific `paths` (files inside the repo at
	`repo_root`, relative or absolute) -- not the whole repo, see
	commit_all() for that -- and commit them with `message` if anything
	actually changed. Returns True if a commit happened, False if there
	was nothing to commit (already up to date -- not an error)."""
	repo = git.Repo(repo_root)
	repo.index.add([os.path.abspath(p) for p in paths])
	if not repo.index.diff("HEAD"):
		return False
	repo.index.commit(message)
	return True


def push(repo_root):
	"""AI Generated -- pull --rebase from the tracking branch, then push.
	Raises on any git failure -- a failed rebase is left aborted, not
	half-applied -- reporting that to the user is the caller's job, same
	as ensure_cloned()/provenance() above (this module stays UI-free, see
	the module docstring)."""
	repo = git.Repo(repo_root)
	branch = repo.active_branch.name
	repo.remotes.origin.fetch()
	try:
		repo.git.rebase(f"origin/{branch}")
	except git.GitCommandError:
		repo.git.rebase("--abort")
		raise
	repo.remotes.origin.push()


def commit_and_push(repo_root, paths, message):
	"""AI Generated -- commit(), then push() if the commit actually
	happened. Returns True if a commit+push happened, False if there was
	nothing to commit."""
	if not commit(repo_root, paths, message):
		return False
	push(repo_root)
	return True


def provenance(repo_root, relpath):
	"""(commit, uncommitted_changes, permalink) for `relpath` inside the
	git repository at `repo_root` -- derived entirely from local git
	metadata (HEAD, working-tree status, the `origin` remote), no network
	call. Returns (None, None, None) if `repo_root` isn't actually a git
	repository (e.g. a plain, non-cloned protocols_dirs entry)."""
	try:
		repo = git.Repo(repo_root)
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		return None, None, None
	try:
		commit = repo.head.commit.hexsha
	except Exception:
		return None, None, None

	uncommitted_changes = repo.is_dirty(path=relpath)

	permalink = None
	try:
		remote_url = repo.remotes.origin.url
		permalink = f"{permalink_base(remote_url)}/blob/{commit}/{relpath}"
	except Exception:
		pass  # no `origin` remote, or it isn't GitHub-shaped -- permalink stays None

	return commit, uncommitted_changes, permalink
