from rich import print
import fnmatch  # AI Generated -- data-pattern matching in _disposition()
import os
import logging as log
import platform
import subprocess  # AI Generated -- used by sync_file()'s destination-directory pre-creation
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

	def configure(scopeconfig):
		## AI Generated -- classification is read even when no file_server is
		## configured: it describes the experiment's own files, not the transport.
		if TrappyConfig.current is not None:
			ExpSync.manifest = list(TrappyConfig.current.expanded("Experiment", "sync", "manifest") or [])
			## AI Generated -- deliberately the SAME field ExpGit reads for its
			## .gitignore: one list, three consumers (.gitignore generation, git
			## tracking, sync disposition), so they cannot drift apart.
			ExpSync.data_patterns = list(TrappyConfig.current.expanded("Experiment", "git_tracking", "exclude") or [])

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



	def __init__(self, expname, sync_max_threads=1, destination_dir=None):
		"""
		sync_max_threads: maximum number of processes/threads for synching files.
		destination_dir: if not set, a directory is created using the destination
		string in the configuration.
		"""
		self.sync_max_threads = sync_max_threads
		
		## Deduce a mount point for the remote share
		if platform.system() == "Linux":
			log.debug("Plateform is Linux.")
			self.mount_addr = f"/mnt/{ExpSync.share}/"
			# Todo fill for linux.
		elif platform.system() == "Darwin":
			log.debug("Plateform is Darwin (MacOS).")
			self.mount_addr = f"/Volumes/{ExpSync.share}/"
		else:
			log.error("Operating system not implemented.")

		#if not os.path.exists(self.mount_addr):
		self.destination_dir = None
		if ExpSync.active:
			self.mount(ExpSync.server, ExpSync.share,
					   ExpSync.username, ExpSync.password)

			## AI Generated -- the `.sync` marker file and set_sync_logfile()
			## were removed here (docs/notes/sync_rework.md §7): it was written
			## once and only ever appended to on a move, so it never was the log
			## its own docstring claimed. Experiment.set_sync_flag()/
			## unset_sync_flag() -- a second, differently-formatted writer of the
			## same filename -- went with it.

			## AI Generated -- effify() used to be defined inline right
			## here; centralized onto TrappyConfig.template() (Claude,
			## Anthropic) so any config field wanting this same
			## "{date}"-style templating can reuse it instead of a second
			## private copy. See docs/notes/scripts_measurements_plotting.md §G.10.

			## AI Generated -- destination_dir was computed fresh from
			## today's date/time on every single open (Experiment.__init__
			## looks for self.logs["destination_dir"] to reuse, but nothing
			## ever wrote it back here), so a reconnect on a different day
			## silently negotiated a brand new remote directory instead of
			## reusing the one this experiment already has. Fixed: persist
			## it, and log which of the two actually happened -- see
			## docs/notes/experiment_architecture_and_actions.md §C.
			reconnected = bool(destination_dir)
			if not destination_dir:
				templated = TrappyConfig.current.template(ExpSync.destination_fmt)
				self.mkexpdir(templated, expname)
				self.destination_dir = os.path.join(self.mount_addr, templated, expname)
			else:
				self.destination_dir = destination_dir

			if not os.path.exists(self.destination_dir):
				raise FileNotFoundError("exp.destination_dir not found. Check experiment.yaml file.")

			self.logs["destination_dir"] = self.destination_dir
			self.log("sync_reconnected" if reconnected else "sync_destination_negotiated",
					 attribs={"destination_dir": self.destination_dir})

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

	
	def mkexpdir(self, scopeid, experiment):
		"""
		scopeid: Scopeid.
		experiment: experiment name.
		"""
		try:
			os.makedirs(os.path.join(self.mount_addr, scopeid, experiment), mode=0o777, exist_ok=True)
		except:
			os.system(f"sudo mkdir -p {os.path.join(self.mount_addr, scopeid, experiment)}")
		log.info("Created / confirmed remote Experiment directory.")

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

	def mount(self, server, share, username, password):
		"""
		Mount an SMB share. See core.sync.mount -- not experiment-specific,
		so the actual mounting logic lives there.
		"""
		mount_point = sync.mount(server, share, username, password)
		print(f"Mounted //{server}/{share} at {mount_point}.")
		self.server = f"{mount_point}/"

	def _sync_prefix():
		"""AI Generated -- the rsync command prefix (see sync_file()).
		Experiment.file_server.sync_prefix in config, if set, always wins
		-- e.g. a deployment where the capture process writes root-owned
		files could set ["sudo", "ionice", "-c2", "-n4"] explicitly.

		Otherwise, the default: `ionice` (I/O priority throttling, so a
		sync doesn't compete with a live experiment still writing to the
		same disk) on Linux -- it's util-linux, no macOS equivalent, and
		running it there fails every transfer with "sudo: ionice: command
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

		Run rsync for a specific file or directory.
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

		## AI Generated -- mkexpdir() only ever creates the top-level experiment
		## folder remotely, never subdirectories (analysis/, scripts/, converted/,
		## postprocess/). rsync then has to create a missing destination directory
		## itself, and on at least one real deployment (SMB mount) that internal
		## creation failed with "mkpath: Permission denied" -- pre-create it
		## instead, the same way mkexpdir() does. Routed through the SAME
		## configured prefix as the rsync call below (ExpSync._sync_prefix()) --
		## a plain os.makedirs() runs as this process's own user no matter what
		## the config says, so if the destination genuinely needs elevated
		## permission (as confirmed on this deployment), a bare os.makedirs()
		## here would always fail regardless of `sync_prefix`.
		if os.path.isdir(file):
			dest_dir = os.path.join(self.destination_dir, file)
			prefix = ExpSync._sync_prefix()
			if prefix:
				subprocess.run([*prefix, "mkdir", "-p", dest_dir])
			else:
				os.makedirs(dest_dir, mode=0o777, exist_ok=True)

		## -W --inplace: large binary experiment files (video, images) don't
		## benefit from rsync's delta-transfer algorithm -- the whole-file
		## copy is cheaper than the comparison overhead. Compression is
		## already off by default (no -z/--compress passed) -- the old
		## "--no-compress" here was just asserting that explicitly, and it's
		## a GNU-rsync-only flag: macOS ships `openrsync` (BSD, no GPLv3),
		## which doesn't recognize it and fails every transfer outright.
		result = sync.sync(
			os.path.join(os.getcwd(), file),
			os.path.join(self.destination_dir, file),
			flags=["-a", "-W", "--inplace"],
			remove_source=remove_source,
			prefix=ExpSync._sync_prefix(),
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
		log.info(f"Rsync {disposition}: {file}")
		print(f"Rsync {disposition}: {file}")
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



