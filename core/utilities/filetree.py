"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

Pure-Python replacement for the old Experiment.filetree(), which shelled
out to `subprocess.run(["tree", "-a"])` and returned tree's raw stdout as
one opaque string -- `tree` isn't a cross-platform dependency worth
carrying (Linux package managers ship it, macOS/Windows don't by
default), and a raw string is only useful by printing it directly, which
is exactly what made the old filetree() inconvenient to use anywhere else.

build_tree() walks a directory into a plain nested dict -- no external
dependency, no printing, no GitPython either (git awareness is a
separate, optional layer on top, see git_file_statuses()/git_summary()).
".git" is excluded by default: its internals (thousands of loose objects,
hooks, refs) are never useful to show in a directory listing.

render_tree() turns that structure into a rich.tree.Tree for live console
display (print(render_tree(...))). render_tree_yaml_data() turns it into
a plain dict ready for yaml.dump() -- a nested tree (each file tagged
with its git status) plus an explicit top-level git_status summary block
(head/commits/pending, and files grouped by status) -- meant for
Experiment.generate_filetree() to write to filetree.yaml, refreshed
before every commit (see expframework/expgit.py): since heavy files are
deliberately excluded from the repo itself, this is what actually shows
their history.
"""

import os

STATUS_STYLE = {
	"committed": "green",
	"modified": "yellow",
	"staged": "cyan",
	"untracked": "dim white",
	"ignored": "red",
}

STATUS_TAG = {
	"committed": "",
	"modified": "  [modified]",
	"staged": "  [staged]",
	"untracked": "  [untracked]",
	"ignored": "  [ignored]",
}


def build_tree(root, exclude=(".git",)):
	"""Recursively walk `root` into a nested dict:
	{"name", "type": "dir"|"file", "path" (relative to `root`, "" for
	the root itself), "size" (files only, bytes, None if unreadable),
	"children" (dirs only, list, directories before files, both
	alphabetical)}. Entries whose name is in `exclude` are skipped
	entirely (default: just ".git")."""
	def walk(path, relpath):
		name = os.path.basename(path) or path
		if os.path.isdir(path):
			try:
				entries = sorted(os.listdir(path))
			except OSError:
				entries = []
			dirs = [e for e in entries if e not in exclude and os.path.isdir(os.path.join(path, e))]
			files = [e for e in entries if e not in exclude and os.path.isfile(os.path.join(path, e))]
			children = [walk(os.path.join(path, e), os.path.join(relpath, e) if relpath else e)
						for e in dirs + files]
			return {"name": name, "type": "dir", "path": relpath, "children": children}
		else:
			try:
				size = os.path.getsize(path)
			except OSError:
				size = None
			return {"name": name, "type": "file", "path": relpath, "size": size}

	return walk(root, "")


def _iter_files(node):
	"""Every file path (as build_tree() set them) under `node`."""
	if node["type"] == "file":
		yield node["path"]
	else:
		for child in node.get("children", []):
			yield from _iter_files(child)


def git_file_statuses(repo_root, tree):
	"""{relpath: status} for every file in `tree` (see build_tree()),
	status one of "committed"/"modified"/"staged"/"untracked"/"ignored".
	Returns {} if `repo_root` isn't actually a git repository."""
	import git
	try:
		repo = git.Repo(repo_root)
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		return {}

	paths = list(_iter_files(tree))
	ignored = set(repo.ignored(paths)) if paths else set()
	untracked = set(repo.untracked_files)
	unstaged = {d.a_path for d in repo.index.diff(None)}
	staged = {d.a_path for d in repo.index.diff("HEAD")} if repo.head.is_valid() else set()

	statuses = {}
	for p in paths:
		if p in ignored:
			statuses[p] = "ignored"
		elif p in untracked:
			statuses[p] = "untracked"
		elif p in unstaged:
			statuses[p] = "modified"
		elif p in staged:
			statuses[p] = "staged"
		else:
			statuses[p] = "committed"
	return statuses


def git_summary(repo_root):
	"""{"head": short hash or None, "commits": int, "pending": int
	(untracked + unstaged + staged, not counting ignored)} for the repo
	at `repo_root`, or None if it isn't one."""
	import git
	try:
		repo = git.Repo(repo_root)
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		return None

	head_valid = repo.head.is_valid()
	head = repo.head.commit.hexsha[:10] if head_valid else None
	commits = sum(1 for _ in repo.iter_commits()) if head_valid else 0
	pending = len(repo.untracked_files) + len(repo.index.diff(None))
	pending += len(repo.index.diff("HEAD")) if head_valid else 0
	return {"head": head, "commits": commits, "pending": pending}


def _summary_suffix(summary):
	if not summary:
		return ""
	pending = f", {summary['pending']} pending" if summary["pending"] else ""
	return f"  ({summary['commits']} commits, HEAD {summary['head']}{pending})"


def render_tree(tree, statuses=None, summary=None):
	"""A rich.tree.Tree for live console display (print(render_tree(...))).
	`statuses` (see git_file_statuses()), if given, color- and
	tag-annotates each file by its git state. `summary` (see
	git_summary()), if given, is appended to the root label."""
	from rich.markup import escape
	from rich.tree import Tree

	statuses = statuses or {}
	## AI Generated -- escape() is essential here, not decorative: a bare tag
	## like "  [untracked]" looks like rich markup syntax to Tree.add()'s
	## parser (an unrecognized style name), which silently swallows it and
	## the text disappears instead of erroring -- verified directly.
	root = Tree(f"[bold]{escape(tree['name'] or '.')}[/bold][dim]{escape(_summary_suffix(summary))}[/dim]")

	def add(parent, node):
		is_dot = node["name"].startswith(".")  # AI Generated -- dotfiles/folders always render red
		if node["type"] == "dir":
			style = "bold red" if is_dot else "bold blue"
			branch = parent.add(f"[{style}]{escape(node['name'])}/[/{style}]")
			for child in node["children"]:
				add(branch, child)
		else:
			status = statuses.get(node["path"])
			style = "red" if is_dot else STATUS_STYLE.get(status, "white")
			tag = STATUS_TAG.get(status, "")
			parent.add(f"[{style}]{escape(node['name'] + tag)}[/{style}]")

	for child in tree.get("children", []):
		add(root, child)
	return root


def render_tree_yaml_data(tree, statuses=None, summary=None, locations=None):
	"""Plain dict, ready for yaml.dump(): {"tree": <nested>, "git_status":
	<summary block, or None if `summary` wasn't given>}. Each file entry
	in the nested tree carries a "status" key when `statuses` has one for
	it. The git_status block is explicit and separate from the per-file
	tags -- head/commits/pending, plus every file grouped by status --
	so the overall repo state is visible at a glance, not just scattered
	across individual file entries.

	`locations` (AI Generated -- {relpath: "local"|"remote"|"both"}, from
	ExpSync.locations()) adds a `location` field per file. This is the one
	field that genuinely overlaps with the sync ledger, and it lives here
	on purpose: current state belongs in the snapshot, which git already
	versions, while the ledger stays a pure event log
	(docs/notes/sync_rework.md §6). A file the ledger has never mentioned
	is "local" -- it has not been anywhere else."""
	statuses = statuses or {}
	locations = locations or {}

	def convert(node):
		if node["type"] == "dir":
			return {"name": node["name"], "type": "dir",
					"children": [convert(c) for c in node["children"]]}
		entry = {"name": node["name"], "type": "file", "size": node["size"]}
		status = statuses.get(node["path"])
		if status:
			entry["status"] = status
		entry["location"] = locations.get(node["path"], "local")
		return entry

	git_status = None
	if summary is not None:
		by_status = {"modified": [], "staged": [], "untracked": [], "ignored": []}
		for path, status in statuses.items():
			if status in by_status:
				by_status[status].append(path)
		git_status = {"head": summary["head"], "commits": summary["commits"],
					  "pending": summary["pending"],
					  **{k: sorted(v) for k, v in by_status.items()}}

	return {"tree": convert(tree), "git_status": git_status}
