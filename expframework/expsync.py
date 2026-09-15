from rich import print
import fnmatch  # AI Generated -- data-pattern matching in _disposition()
import os
import logging as log
import platform
import threading  # AI Generated -- guards the sync.yaml ledger append
from concurrent.futures import ThreadPoolExecutor
import time


## AI Generated -- `uid` and `datetime` imports removed with .sync/set_sync_logfile()
from core.bookkeeping.yamlprotocol import YamlProtocol  # AI Generated -- sync.yaml ledger
from core.permaconfig.config import TrappyConfig  # AI Generated -- Share/User imports removed, no longer used here (see template())
from core.tsevents import TSEvent  # AI Generated -- ledger record shape
import core.sync as sync
from .exppolicy import ExpPolicy  # AI Generated -- per-copy marker scope, see _disposition()

class ExpSync:
	"""
	Synchronises experiment files with a remote server.
	"""
	active = False
	server = None
	share = None
	username = None
	password = None
	destination_fmt = None
	sync_prefix = None  # AI Generated -- None means "use the platform default", see _sync_prefix()

	## AI Generated -- file classification, see _disposition() and
	## docs/notes/sync_rework.md §4. Both are "expand" fields: a lab-wide
	## manifest can extend either without disturbing what a device declares
	## for itself.
	manifest = []       # never moved, only ever copied
	data_patterns = []  # globs -> moved (transferred, then removed locally)
	never_sync = []     # globs -> never transferred at all, in either direction

	## AI Generated -- rclone transport (docs/notes/sync_rework.md §5).
	protocol = "smb"              # any rclone backend: smb, sftp, ftp, webdav, s3...
	remote_name = "trappyserver"  # the rclone remote's name; defined from config, not rclone.conf
	bwlimit = None                # e.g. "20M", or a schedule like "08:00,512k 22:00,off"
	transfers_limit = None        # rclone --transfers; also the main lever on local disk read pressure
	_obscured = None              # cached obscured password, see _remote_env()

	def configure(scopeconfig):
		## AI Generated -- classification is read even when no file_server is
		## configured: it describes the experiment's own files, not the transport.
		if TrappyConfig.current is not None:
			ExpSync.manifest = list(TrappyConfig.current.expanded("Experiment", "sync", "manifest") or [])
			## AI Generated -- deliberately the SAME field ExpGit reads for its
			## .gitignore: one list, three consumers (.gitignore generation, git
			## tracking, sync disposition), so they cannot drift apart.
			ExpSync.data_patterns = list(TrappyConfig.current.expanded("Experiment", "git_tracking", "exclude") or [])
			ExpSync.never_sync = list(TrappyConfig.current.expanded("Experiment", "sync", "never") or [])

		## AI Generated -- moved from config.file_server to Experiment.file_server
		## (docs/notes/restructuring.md §12 #4).
		block = TrappyConfig.optional_block(scopeconfig, "Experiment", "file_server")
		if block is None:
			ExpSync.active = False
			return

		ExpSync.active = True
		ExpSync.server = block["server"]
		ExpSync.share = block["share"]
		ExpSync.username = block["username"]
		ExpSync.password = block["password"]
		ExpSync.destination_fmt = block["destination"]
		ExpSync.sync_prefix = block.get("sync_prefix")  # AI Generated -- explicit override, see _sync_prefix()

		## AI Generated -- rclone transport settings (docs/notes/sync_rework.md §5).
		ExpSync.protocol = block.get("protocol", "smb")
		ExpSync.remote_name = block.get("remote_name", "trappyserver")
		ExpSync.bwlimit = block.get("bwlimit")
		ExpSync.transfers_limit = block.get("transfers")
		ExpSync._obscured = None  # re-obscure on next use, in case the password changed

		if not sync.rclone_available():
			ExpSync.active = False
			log.error("rclone is not installed, so experiment sync is disabled. "
					  "Install it (e.g. `brew install rclone`, `apt install rclone`) "
					  "and restart. ExpSync no longer uses rsync or an OS-level mount "
					  "-- see docs/notes/sync_rework.md §5.")



	def __init__(self, expname, sync_max_threads=1, destination_dir=None):
		"""
		sync_max_threads: maximum number of processes/threads for synching files.
		destination_dir: if not set, a directory is created using the destination
		string in the configuration.
		"""
		self.sync_max_threads = sync_max_threads

		## AI Generated -- the platform mount-point branch (/Volumes vs /mnt),
		## self.mount(), mkexpdir() and its `sudo mkdir -p` fallback are all gone
		## with the rclone migration (docs/notes/sync_rework.md §5). rclone speaks
		## the protocol directly, creates remote directories as part of the
		## transfer, and writes as the authenticated remote user -- which is what
		## removed the whole class of mount-permission failures this used to hit.
		self.destination_dir = None
		if ExpSync.active:
			## AI Generated -- destination_dir was computed fresh from
			## today's date/time on every single open (Experiment.__init__
			## looks for self.logs["destination_dir"] to reuse, but nothing
			## ever wrote it back here), so a reconnect on a different day
			## silently negotiated a brand new remote directory instead of
			## reusing the one this experiment already has. Fixed: persist
			## it, and log which of the two actually happened -- see
			## docs/notes/experiment_architecture_and_actions.md §C.
			##
			## template() centralizes the old inline effify() -- see
			## docs/notes/scripts_measurements_plotting.md §G.10.
			reconnected = bool(destination_dir)
			if not destination_dir:
				templated = TrappyConfig.current.template(ExpSync.destination_fmt)
				self.destination_dir = ExpSync._remote_path(templated, expname)
			else:
				self.destination_dir = destination_dir

			## AI Generated -- the old `os.path.exists(self.destination_dir)` guard
			## is gone: destination_dir is now an rclone remote path
			## ("remote:share/..."), not something the local filesystem can stat.
			## Nothing needs pre-creating either -- rclone makes the path on write.

			self.logs["destination_dir"] = self.destination_dir
			self.log("sync_reconnected" if reconnected else "sync_destination_negotiated",
					 attribs={"destination_dir": self.destination_dir,
							  "protocol": ExpSync.protocol})

		## Background executor
		self.__executor = ThreadPoolExecutor(max_workers=sync_max_threads)
		self.__futures = []


	def __get__state__(self):
		return {"active" : ExpSync.active,
				"destination_dir": self.destination_dir,
				"sync_max_threads" : self.sync_max_threads}

	def __exit__(self):
		log.warning("Waiting for transfers...")
		self.__executor.shutdown(wait=True)
		log.warning("[OK] Transfers complete...")

	
	def _remote_path(*parts):
		"""AI Generated -- an rclone remote path: "<remote>:<share>/<parts...>".
		`share` is the leading path segment (SMB's share name); backends with no
		such concept (sftp, s3) leave it empty in config and it drops out."""
		segments = [p for p in (ExpSync.share, *parts) if p]
		return f"{ExpSync.remote_name}:{'/'.join(segments)}"

	def _remote_env():
		"""AI Generated -- the rclone remote, defined entirely from
		trappyconfig at call time (docs/notes/sync_rework.md §3): no
		rclone.conf, no second credential store to keep in step. rclone reads
		`RCLONE_CONFIG_<REMOTE>_<KEY>` exactly as it would config-file keys,
		which is why the password has to be obscured first."""
		if ExpSync._obscured is None:
			ExpSync._obscured = sync.rclone_obscure(ExpSync.password)

		env = dict(os.environ)
		tag = f"RCLONE_CONFIG_{ExpSync.remote_name.upper()}"
		env[f"{tag}_TYPE"] = ExpSync.protocol
		env[f"{tag}_HOST"] = ExpSync.server
		env[f"{tag}_USER"] = ExpSync.username
		env[f"{tag}_PASS"] = ExpSync._obscured
		return env

	def _rclone_flags(self):
		"""AI Generated -- --bwlimit throttles the *network*; --transfers caps
		concurrency, which is the real lever on local disk read pressure. Neither
		replaces ionice's disk-priority control -- that is what sync_prefix still
		exists for on Linux (docs/notes/sync_rework.md §5)."""
		flags = []
		if ExpSync.bwlimit:
			flags += ["--bwlimit", str(ExpSync.bwlimit)]
		if ExpSync.transfers_limit:
			flags += ["--transfers", str(ExpSync.transfers_limit)]
		## rclone's own transfer log -- raw diagnostics (bytes, retries, errors),
		## distinct from sync.yaml's semantic ledger. Gitignored, disposable.
		flags += ["--log-file", os.path.join(self.exp_dir, "rclone.log")]
		return flags

	def _disposition(file):
		"""AI Generated -- 'move' or 'copy' for one top-level entry of the
		experiment directory. See docs/notes/sync_rework.md §1/§4.

		Two dispositions only. The data patterns decide what *moves*;
		everything else copies, whether or not it is named in the manifest.
		The manifest's job is therefore narrower than its name suggests --
		it states what must never be moved *even if* a data pattern would
		otherwise match it (e.g. a `logs.yaml` that some config's exclude
		list happened to glob), which is why it is checked first.

		Note this classifies top-level entries only, matching how sync_dir()
		has always worked: a directory is copied or moved whole. Data files
		written at the experiment root -- the normal case -- classify
		correctly; data buried inside an otherwise-manifest directory would
		be copied with it rather than moved."""
		## AI Generated -- checked BEFORE the data patterns, and this ordering is
		## load-bearing: `never` entries also appear in git_tracking.exclude (so
		## they are gitignored), and that same field is what decides what *moves*.
		## Without this check first, rclone.log -- purely local diagnostics --
		## would be classified as data and shipped to the server.
		for pattern in ExpSync.never_sync:
			if fnmatch.fnmatch(file, pattern):
				return "skip"

		## AI Generated -- per-copy policy markers never leave this copy. `.policy.stub`
		## describes *this* copy; copying it would make the full server-side copy
		## falsely declare itself a stub (docs/notes/sync_rework.md §2).
		if file.startswith(ExpPolicy.MARKER_PREFIX):
			name = file[len(ExpPolicy.MARKER_PREFIX):]
			return "skip" if ExpPolicy.scope_of(name) == "copy" else "copy"
		if file in ExpSync.manifest:
			return "copy"
		for pattern in ExpSync.data_patterns:
			if fnmatch.fnmatch(file, pattern):
				return "move"
		return "copy"

	## AI Generated -- ExpSync.mount() removed with the rclone migration: there is
	## no OS-level mount any more. core.sync.mount() itself stays, since the
	## launcher's trappyverse/ config sync still uses it.

	def _sync_prefix():
		"""AI Generated -- the transfer command prefix (see sync_file()).
		Experiment.file_server.sync_prefix in config, if set, always wins
		-- e.g. a deployment where the capture process writes root-owned
		files could set ["sudo", "ionice", "-c2", "-n4"] explicitly.

		Otherwise, the default: `ionice` (I/O priority throttling, so a
		sync doesn't compete with a live experiment still writing to the
		same disk) on Linux -- it's util-linux, no macOS equivalent, and
		running it there failed every transfer with "sudo: ionice: command
		not found". No `sudo` by default anywhere: setting the
		best-effort I/O class (-c2) on a process you're launching
		yourself doesn't need root (only the realtime class, or changing
		a process you don't own, needs CAP_SYS_NICE) -- and sudo can hang
		forever waiting on a password prompt that never comes in a
		background sync (sync_file_bg() has no attached terminal at all).
		A source-file permission gap should be fixed with proper group
		read access on the capture side, not a privilege escalation on
		every sync."""
		if ExpSync.sync_prefix is not None:
			return list(ExpSync.sync_prefix)
		if platform.system() == "Linux":
			return ["ionice", "-c2", "-n4"]
		return []

	def sync_dir(self, remove_source=None):
		"""
		Note: Blocking function

		Synchronise the whole experiment directory to the server.

		AI Generated -- each entry's disposition is now decided per file by
		_disposition(): data files move, everything else copies, in one pass.
		That is the two-copy model (docs/notes/sync_rework.md §1) -- the
		server ends up with a complete experiment while the local side keeps
		the full manifest and loses only bulk data.

		remove_source: leave as None to classify per file (the intended
		path). Passing True/False overrides the classification for *every*
		entry, which is what the pre-existing callers in scripts/longterm/
		rely on.

		The old `file.startswith(".")` filter is gone: it was doing
		invisible classification, and was the only reason `.experiment` and
		`.git/` survived a move. They are manifest entries now, so they must
		actually be copied -- keeping the filter would have declared them
		manifest and then silently never synced them (§4).
		"""
		files = [f for f in os.listdir(os.getcwd())]
		## AI Generated -- "skip" entries (per-copy policy markers) never transfer.
		files = [f for f in files if ExpSync._disposition(f) != "skip"]

		from functools import partial
		sync_ = partial(self.sync_file, remove_source=remove_source)
		with ThreadPoolExecutor(max_workers=self.sync_max_threads) as __executor:
			results = __executor.map(sync_, files)

		# Collecting the results (just for demonstration purposes)
		for result in results:
			if result is not None:
				log.debug(result)

		## AI Generated -- once data has moved out, this copy is a stub: it holds
		## the full manifest and no bulk data. Declared here so the fact is
		## detectable later without parsing anything (docs/notes/sync_rework.md
		## §2). Only the depleted side is ever declared -- "more original" is
		## deliberately left undefined.
		moved = [attribs["path"] for attribs in
				 (e.get("attribs", {}) for e in self.transfers())
				 if attribs.get("disposition") == "moved" and attribs.get("ok", True)]
		if moved and not self.has_policy("stub"):
			self.declare_policy("stub", moved_files=len(moved))


	def sync_file_bg(self, file, remove_source=None, delay_sec=0):
		"""
		Same as `sync_file` function, but is non-blocking manner.
		This uses a threadpool. The number of workers can be set,
		while creating the experiment.
		"""
		self.__executor.submit(self.sync_file, file, remove_source=remove_source, \
							 delay_sec=delay_sec)

	def sync_file(self, file, remove_source=None, delay_sec=0):
		"""
		Note: Blocking function

		Run one rclone transfer for a specific file or directory.
		file: filename (relative to exp_dir)
		remove_source: AI Generated -- None (the default) classifies this
		  file via _disposition(): data moves, everything else copies.
		  Pass True/False to override -- acquisition scripts that transmit
		  a capture to free disk space as they go
		  (scripts/longterm/mjpeg_*.py) pass True explicitly.
		delay_sec: delay the transfer by a number of seconds. This is useful in
		case, the transfers need to be staggered because of bandwidth limitations.
		"""

		# To account for file write delays for example.
		if delay_sec:
			time.sleep(delay_sec)

		if remove_source is None:  # AI Generated
			remove_source = ExpSync._disposition(file) == "move"

		## AI Generated -- no destination pre-creation any more. The old code had to
		## mkdir the remote subdirectory itself (mkexpdir() only ever made the
		## top-level folder, and rsync's own creation failed with "mkpath:
		## Permission denied" against the SMB mount) -- rclone creates the path as
		## part of the transfer, as the authenticated remote user, so the whole
		## dance including its sudo fallback is gone.
		##
		## copyto/moveto rather than copy/move: both take a full destination path
		## instead of copying *into* a directory, and both accept either a file or
		## a directory, so one call shape covers every entry sync_dir() walks.
		result = sync.rclone(
			"moveto" if remove_source else "copyto",
			os.path.join(os.getcwd(), file),
			f"{self.destination_dir}/{file}",
			flags=self._rclone_flags(),
			prefix=ExpSync._sync_prefix(),
			env=ExpSync._remote_env(),
		)
		disposition = "moved" if remove_source else "copied"
		if result.returncode != 0:
			log.error(f"Error occurred with {file}: {result.stderr.strip()}")
			## AI Generated -- failures are recorded too. This is the class of fact
			## that leaves no trace in filetree.yaml's snapshot and is the main
			## reason the ledger exists at all (docs/notes/sync_rework.md §6).
			self.log_transfer(file, disposition, ok=False,
							   error=result.stderr.strip()[:500])
			return None

		self.log_transfer(file, disposition, ok=True)
		log.info(f"rclone {disposition}: {file}")
		print(f"rclone {disposition}: {file}")
		return result.stdout

	## AI Generated -- the sync ledger (docs/notes/sync_rework.md §1/§7), the
	## durable replacement for `.sync`. Append-only, TSEvent-shaped, and written
	## with load-modify-dump rather than a logging handler: a held-open
	## RotatingFileHandler is exactly the trap that silently lost logs.yaml
	## records when that file was being moved out from under it.
	LEDGER_FILENAME = "sync.yaml"

	## AI Generated -- sync_dir() runs transfers in a ThreadPoolExecutor, and each
	## one appends via load-modify-dump. At the default sync_max_threads=1 that is
	## serial, but the parameter is caller-settable -- without this lock two
	## workers could read the same list and the second write would drop the
	## first's entry.
	_ledger_lock = threading.Lock()

	def log_transfer(self, file, disposition, ok=True, error=None, **attribs):
		"""One ledger entry per transfer attempt. `disposition` is "moved" or
		"copied"; a failed attempt is recorded with ok=False and the transport's
		own error, so the ledger answers "what happened" and not merely "what
		is where" -- the latter is filetree.yaml's job."""
		record = TSEvent(kind="file_synced",
						  attribs={"path": file,
								   "disposition": disposition,
								   "ok": ok,
								   "destination": os.path.join(self.destination_dir or "", file),
								   **({"error": error} if error else {}),
								   **attribs})

		path = os.path.join(self.exp_dir, ExpSync.LEDGER_FILENAME)
		with ExpSync._ledger_lock:
			existing = YamlProtocol.load(path) if os.path.exists(path) else []
			if not isinstance(existing, list):
				existing = []
			existing.append(dict(record))
			YamlProtocol.dump(path, existing)
		return record

	def transfers(self):
		"""The ledger, as a plain list. Empty if nothing has ever synced."""
		path = os.path.join(self.exp_dir, ExpSync.LEDGER_FILENAME)
		if not os.path.exists(path):
			return []
		return YamlProtocol.load(path) or []

	def locations(self):
		"""AI Generated -- {relpath: "local" | "remote" | "both"} derived from the
		ledger: the latest successful entry for each path decides. A move means
		the bytes are only on the server now; a copy means both sides hold it.
		This is what feeds filetree.yaml's `location` field -- current state
		lives in the snapshot, the ledger stays a pure event log (§6)."""
		latest = {}
		for entry in self.transfers():
			attribs = entry.get("attribs", {})
			if not attribs.get("ok", True):
				continue
			if attribs.get("path"):
				latest[attribs["path"]] = attribs.get("disposition")
		return {path: ("remote" if disposition == "moved" else "both")
				for path, disposition in latest.items()}



# Example usage
if __name__ == '__main__':
	print("This program will not execute. It is an example.")
	source_directory = '/path/to/source/directory'
	destination_directory = '/path/to/destination/directory'
	
	# Set the maximum number of parallel workers
	#max_parallel_workers = 4
	
	# Start the rsync process
	#rsync_directory(source_directory, destination_directory, max_parallel_workers)



