import datetime
import functools
import threading
import time
from copy import deepcopy

from core.permaconfig.sharing import Share
from .experiment import ExpEvent
from .experiment import Experiment as Experiment_
from core.bookkeeping.session import Session
from core.uid import UIDEngine
from core.idioms.formdialog import (Field, form_dialog, grid_dialog,
									  page_size, parse_value)
import logging as log
from .plotter import *
import plotext as plt

from pandas import DataFrame, concat

from pprint import pformat
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print
from rich import pretty
from rich.table import Table

MODALITIES = ("measurement", "monitor", "detection")

## Builtins map to the pandas dtype that survives a missing value. A declared
## dtype has to hold up on a column that is mostly blank -- the normal state,
## since every field is seeded blank and filled only when recorded -- and
## astype(int) raises IntCastingNaNError on one. The capitalised pandas types
## ("Int64", "boolean", "string") hold pd.NA; the lowercase numpy ones do not.
## So callers write dtype=int and get the one that works.
##
## Mapping here is also what makes descriptors serialisable: a bare `int` is a
## type object and would not survive a YAML dump, "Int64" is a string.
## A dtype that is already a string passes straight through, so pandas' own
## names work and nothing here needs maintaining as pandas grows.
DTYPE_ALIASES = {
	int:      "Int64",
	bool:     "boolean",
	str:      "string",
	float:    "float64",          ## float64 already holds NaN
	complex:  "complex128",
	bytes:    "object",
	list:     "object",           ## e.g. cell_counts' `counts`
	tuple:    "object",
	dict:     "object",
	set:      "object",
	datetime.datetime: "datetime64[ns]",
	datetime.date:     "datetime64[ns]",
}


def __record_version_change__(method):
	"""Bump the stream's version counter after any call that changes what
	`.df` would produce -- a new reading, a new field, a new clock.

	The counter is only ever compared for inequality (`.df` rebuilds when it
	differs from the cached build), never read as a quantity, so nested calls
	bumping it more than once are harmless: subscribe_clock -> add_monitor ->
	add_field bumps twice and nothing cares.

	The bump happens AFTER the wrapped call returns, so a call that raises
	leaves the counter -- and therefore a still-correct cache -- alone.

	It exists so the bump cannot be forgotten. Before this, __call__ did
	`self._version += 1` by hand and add_field did not bump at all, so adding
	a field to a stream that already had readings left `.df` serving a cached
	frame with the old columns.
	"""
	@functools.wraps(method)
	def wrapper(self, *args, **kwargs):
		result = method(self, *args, **kwargs)
		self._version += 1
		return result
	return wrapper


class Measurement(ExpEvent):
	"""

	Every time you look at the system, you perturb it.
	--------------------------------------------------

	A measurment is a type of dictionary (Trappy-Scopes Event) that is compatible with the
	dataframe (pandas) data-structure and gives all the necessary in-
	-formation necessary for every entry. Trappy-Scopes allows the user to com-
	-bine arbitrary number of experiments for analysis,

	Measurement
		.
		|- type           (type="Experiment.Measurement")
		|- scopeid        (M1, M2, ...)
		|- mid            (Microscope uid)
		|- scriptid       (Defined for an experiment that is repeated multiple times)
		|- eid            (experiment id)
		|- sid            (session id; for SingleSession experiments, it is the same as eid)
		|- df             (datetime)
		|- sessiontime    (time elapsed in seconds since experiment)
		|- exptime        (total time of the experiment - sum of all sessions)
		|- machinetime    (nanosecond tick - since epoch time)
		|- measureid      (epochtime/ measurement mode id - assigned by a MeasurementStream object)
		|- measureidx     (measurement index - deafults to -1 : arbitrary sequence order)
		|- success        (flag that must be set after measurement to indicate its completion)
		|- <measurand 1>
		|- <measurand 2>
		:       :::
		|- <measurand n>
		+
	"""



	def __init__(self, **kwargs):

		super().__init__()
		self.update({
					"type"         : "measurement",
			  		"measureid"    : Experiment_.current.eid,
			   		"measureidx"   : 0,
			   		"success"      : None,
		   			})

		# Initial keys
		if len(kwargs) != 0:
			for key in kwargs:
				self[key] = kwargs[key]



	def panel(self):
		print(Panel(Pretty(self.copy()), title=f"Measurement: {self['measureidx']}"))
	    
	## AI Generated -- `def get(self): return self` deleted here.
	## Measurement is a dict (ExpEvent -> TSEvent -> dict), and that override
	## shadowed dict.get(key, default): any `reading.get("outcome")` raised
	## `TypeError: get() takes 1 positional argument but 2 were given`. It
	## dated from the 2024-03 commit that was experimenting with __repr__ and
	## was never called with no arguments anywhere in the repo or in
	## trappy-explorer. Use `reading[key]` or the inherited .get().
	


class MeasurementStream:
	"""
	Returns time adjusted copies of a measurement.
	"""
	def __init__(self, measurement={}, name=None):
		self.name = name
		self.datapoint = Measurement(**measurement)
		self.uid = UIDEngine.get("expframework.measurement.MeasurementStream")()
		self.datapoint["measureid"] = self.uid
		self.datapoint["measureidx"] = -1

		self.readings = []
		
		## Data frame utility
		self._version = 0
		self._df_cache = None
		self._df_cache_version = -1


		## {field: {axis_label, unit, unit_latex, description, modality, dtype}}
		## The single declaration of what this stream records. The separate
		## self.measurements / self.monitors / self.detections lists are gone:
		## descriptors already carries each field's modality and dicts keep
		## insertion order, so the lists were a second copy of the same facts
		## with nothing keeping them in step. Use fields() to read them back.
		self.descriptors = {}

		self.clock_subscriptions = []

		## advance() mutates self.datapoint in place and __call__ deepcopies it,
		## so the two are one critical section. __call__ is reachable from more
		## than one thread -- a scheduled job on exp.schedule.loop and the REPL
		## both call streams -- and an interleave there yields two readings with
		## the same measureidx, or a reading holding another call's half-written
		## datapoint. RLock, not Lock: measure() goes through __call__, so a
		## caller already holding it must not deadlock itself.
		self._lock = threading.RLock()

		self.auto_update_tables = False
		self.auto_update_explogs = False
		self.tables = {} ## Printable table.

	@property
	def df(self):
		"""Returns either a cached or fresh generated dataframe of the MeasurementStream.

		Columns with a declared dtype are cast to it. Without that, pandas
		infers each column from whatever happens to be filled in, so a
		column's dtype depends on how many readings exist rather than on what
		the field is -- declare one and the frame's shape becomes a property
		of the stream instead of its history.

		A cast that will not take is logged and skipped, never raised: a
		half-finished run has to stay inspectable, and one mistaken dtype
		declaration should not make `.df` unusable.
		"""
		if self._df_cache_version != self._version:
			frame = DataFrame(self.readings)
			for key, descriptor in self.descriptors.items():
				dtype = descriptor.get("dtype")
				if dtype is None or key not in frame.columns:
					continue
				try:
					frame[key] = frame[key].astype(dtype)
				except (TypeError, ValueError) as e:
					log.warning(f"MeasurementStream {self.name!r}: column {key!r} "
								f"declares dtype {dtype!r} but will not cast "
								f"({e}); leaving it as {frame[key].dtype}.")
			self._df_cache = frame
			self._df_cache_version = self._version
		return self._df_cache

	def __getstate__(self):
		"""Drop the lock when pickling.

		Experiment.close() pickles self.mstreams into expstate.pickle, and a
		threading.RLock cannot be pickled -- `TypeError: cannot pickle
		'_thread.RLock' object`, raised from close() itself, which leaves the
		experiment unclosable. A lock is process-local anyway: it protects
		this process's threads and means nothing to a future one.
		"""
		state = self.__dict__.copy()
		state.pop("_lock", None)
		return state

	def __setstate__(self, state):
		"""Restore, and give the stream a fresh lock -- __getstate__ removed
		the old one, and __call__ needs it on the first measurement."""
		self.__dict__.update(state)
		self._lock = threading.RLock()

	def fields(self, *modalities):
		"""Declared field names, in declaration order.

		Replaces the old self.measurements / self.monitors / self.detections
		lists -- descriptors is now the single declaration and dicts preserve
		insertion order, so the ordering those lists gave is not lost.

			fields()                        every declared field
			fields("measurement")           just the measurements
			fields("measurement", "monitor")
		"""
		if not modalities:
			return list(self.descriptors)
		unknown = set(modalities) - set(MODALITIES)
		if unknown:
			raise ValueError(f"Unknown modality {sorted(unknown)}. "
							 f"One of: {', '.join(MODALITIES)}")
		return [key for key, d in self.descriptors.items()
				if d.get("modality") in modalities]

	@__record_version_change__
	def add_field(self, key, modality, axis_label=None, unit=None,
				  unit_latex=None, description=None, dtype=None):
		"""Declare one field on this stream.

		key         -- the name the value is recorded under in every reading.
		modality    -- what kind of field it is, one of MODALITIES:
		               "measurement" (a quantity the experiment set out to
		               measure), "monitor" (a condition recorded alongside it)
		               or "detection" (a yes/no observation). The three are
		               mechanically identical -- all three put the key in the
		               same row -- so this is a label for the reader, not a
		               different mechanism.
		axis_label  -- how the field should be named on a plot axis or a form
		               row. Defaults to `key`.
		unit        -- plain-text unit, e.g. "s", "cells/mL". Shown next to the
		               field when entering values by hand.
		unit_latex  -- the same unit typeset, for figures.
		description -- one line on what the field actually is.
		dtype       -- optional expected type, applied to this field's column
		               by `.df`. Builtins are mapped through DTYPE_ALIASES to
		               the pandas dtype that survives missing values, so
		               dtype=int becomes "Int64"; a pandas dtype name passes
		               through unchanged. A cast that will not take is logged
		               and skipped rather than raised -- see `.df`.
		"""
		if modality not in MODALITIES:
			raise ValueError(f"Unknown modality {modality!r} for field {key!r}. "
							 f"One of: {', '.join(MODALITIES)}")
		if dtype is not None:
			dtype = DTYPE_ALIASES.get(dtype, dtype)
			if not isinstance(dtype, str):
				## descriptors are written into experiment.yaml now, so a dtype
				## that is still a type object would make every __save__() of
				## the experiment fail -- not just this field. Normalise through
				## pandas (np.float64 -> "float64"), and fall back to str() so
				## the worst case is a dtype .df cannot honour, never an
				## experiment that cannot be saved.
				try:
					from pandas.api.types import pandas_dtype
					dtype = pandas_dtype(dtype).name
				except Exception:
					log.warning(f"MeasurementStream {self.name!r}: field {key!r} "
								f"declares dtype {dtype!r}, which pandas does not "
								f"recognise. Recording it as text; .df will skip "
								f"the cast.")
					dtype = str(dtype)
		## Seeded with None, not numpy NaN. pandas turns None into NaN in a
		## numeric column anyway, so nothing is lost there -- but a NaN left in
		## a string or boolean column is a float sitting where it does not
		## belong, and a stream with one reading recorded infers every column
		## as float64 instead of object. None says "not recorded"; NaN claims
		## the field is a number.
		self.datapoint[key] = None
		self.descriptors[key] = {"axis_label": axis_label or key, "unit": unit,
								 "unit_latex": unit_latex, "description": description,
								 "modality": modality, "dtype": dtype}

	def add_detection(self, key, axis_label=None, description=None, dtype=None):
		self.add_field(key, "detection", axis_label=axis_label,
					   description=description, dtype=dtype)

	def add_measurement(self, key, axis_label=None, unit=None, unit_latex=None,
						description=None, dtype=None):
		self.add_field(key, "measurement", axis_label=axis_label, unit=unit,
					   unit_latex=unit_latex, description=description, dtype=dtype)

	def add_monitor(self, key, axis_label=None, unit=None, unit_latex=None,
					description=None, dtype=None):
		self.add_field(key, "monitor", axis_label=axis_label, unit=unit,
					   unit_latex=unit_latex, description=description, dtype=dtype)

	@__record_version_change__
	def subscribe_clock(self, clock, label=None):
		"""Subscribe a Clock to the stream."""
		from core.idioms.clock import Clock
		if not isinstance(clock, Clock):
			raise TypeError(f"subscribe_clock() needs an existing Clock, got {type(clock)}")
		label = label or f"clock_{len(self.clock_subscriptions)}"
		self.clock_subscriptions.append((label, clock))
		self.add_monitor(f"{label}_clock_elapsed", unit="s", description=f"Elapsed time on the '{label}' clock")

	@__record_version_change__
	def __call__(self, **kwargs):
		with self._lock:
			self.readings.append(deepcopy(self.advance()))
			for k, v in dict(kwargs).items():
				self.readings[-1][k] = v

			## Tables ----------------------------------------
			if self.auto_update_tables:
				for tab in self.tables:
					row = []
					for key in tab:
						row.append(str(self.readings[-1][key]))
					self.tables[tab].add_row(*row)

			reading = self.readings[-1]

		## Exp logs ---------------------------------------
		## Deliberately OUTSIDE the lock: __save__() writes YAML to disk, and
		## holding a stream lock across file I/O would make every other
		## thread's measurement wait on the filesystem.
		##
		## auto_update_explogs ON is the default mode: serialise each reading
		## as it is taken. Turn it OFF to take manual control -- nothing is
		## written until write(), and edit() is only permitted in that mode.
		if self.auto_update_explogs and Experiment_.current != None:
			Experiment_.current.logs["results"].append(dict(reading))
			Experiment_.current.__save__()

		return reading

	def write(self):
		"""Append the whole reading frame to the experiment's results, and save.

		The counterpart to auto_update_explogs. With it ON every reading is
		serialised as it is taken; with it OFF nothing reaches the experiment
		until this is called, and then the whole list goes at once -- one
		serialisation rather than one per reading.

		Appends. It does not check whether this stream has been written
		before, so calling it twice writes the readings twice; that is the
		caller's to manage.

		dict() on the way out is load bearing: Measurement is a dict SUBCLASS,
		so yaml.safe_dump refuses it and yaml.dump tags it
		!!python/object/new: -- which a plain read cannot construct. Only a
		plain dict round-trips.

		Returns the number of rows written.
		"""
		if Experiment_.current is None:
			log.warning(f"MeasurementStream {self.name!r}: no open experiment, "
						f"nothing written.")
			return 0
		with self._lock:
			rows = [dict(reading) for reading in self.readings]
		Experiment_.current.logs["results"].extend(rows)
		Experiment_.current.__save__()
		return len(rows)

	def measure(self, **kwargs):
		""" Advance a measurement. Alias for __call__ operator."""
		return self.__call__(**kwargs)

	def advance(self, **kwargs):
		""" Function that advances a measurement by iterating the first datapoint"""
		self.datapoint["sessiontime"] = Session.current.timer_elapsed()
		self.datapoint["exptime"]     = Experiment_.current.expclock.time_elapsed()
		self.datapoint["machinetime"] = time.time_ns()
		self.datapoint["dt"] = datetime.datetime.now()
		self.datapoint["measureidx"] = self.datapoint["measureidx"] + 1
		for label, clock in self.clock_subscriptions:
			self.datapoint[f"{label}_clock_elapsed"] = clock.clean_read()
		return self.datapoint

	
	
	def tabulate(self, *args, title=None):
		"""
		Create a tabulated view of the measurement stream with the provided keys.
		"""
		filtered_args = [arg for arg in args if arg in self.datapoint.keys()]
		if list(args) != list(filtered_args):
			log.error("Missing keys passed to MeasurementStream.tabulate. Ignoring those keys.")

		table = Table(*filtered_args, title=f"Table {len(self.tables)}{f' : {title}'*bool(title)}")
		self.tables[tuple(args)] = table
		for i, key in enumerate(args):
			table.columns[i].style = f"color({i+1})"

		## Backfill from the readings already taken. Without this a table only
		## ever shows readings recorded AFTER it was created -- __call__
		## appends to registered tables, and nothing populated them -- so
		## tabulating a stream mid-run printed an empty table. A tabulation of
		## a stream should show the stream.
		for reading in self.readings:
			table.add_row(*[str(dict.get(reading, key, "")) for key in filtered_args])
		return table

	def live_table(self, *args, title=None, refresh_per_second=4, duration=None):
		"""A tabulate() table that redraws as readings arrive.

		Built from this stream's own tabulate(), so the columns, the column
		styling and the registration in self.tables are identical to the
		static view -- one tabulation, two ways of looking at it. It needs no
		polling of its own: __call__ appends to every registered table, so a
		reading recorded on another thread (a scheduled job, say) shows up
		here by itself.

		Blocks until Ctrl-C, or for `duration` seconds if given. Leaving does
		not unregister the table -- tabulate(*args) returns the same one for a
		static look.
		"""
		from rich.live import Live
		if not self.auto_update_tables:
			log.warning(f"MeasurementStream {self.name!r}: auto_update_tables is "
						f"off, so this table will not grow. Set it True to "
						f"watch readings arrive.")
		table = self.tabulate(*args, title=title)
		deadline = time.perf_counter() + duration if duration else None
		try:
			with Live(table, refresh_per_second=refresh_per_second, screen=True) as live:
				while deadline is None or time.perf_counter() < deadline:
					time.sleep(1.0 / refresh_per_second)
					live.update(table)
		except KeyboardInterrupt:
			pass
		return table


	def plot(self, x, y, label=""):
		"""Depreciated -- only works for termainal plotting"""
		plt.cld()
		plt.plot(self.df[x], self.df[y], label=label)
		plt.xlabel(x)
		plt.ylabel(y)
		plt.title(f"Measurement Stream Plot{f':: {self.name}'*(self.name!=None)} :: {x}-{y}")
		plt.show()



	def __summary__(self):
		"""What this stream is, without dumping what it holds.

		The old __repr__/panel() printed every reading inline, so looking at a
		stream with a few hundred readings filled the screen with the data
		instead of describing the stream. Shape, not contents -- `.df`,
		`tabulate()` and `.readings` are how you look at the contents.
		"""
		return {"name": self.name, "measureid": self.uid,
				"readings": len(self.readings),
				**{modality + "s": [self.__field_str__(k)
									for k in self.fields(modality)]
				   for modality in MODALITIES}}

	def __field_str__(self, key):
		"""One field as `name [unit]`, the unit only when there is one."""
		unit = self.descriptors.get(key, {}).get("unit")
		return f"{key} [{unit}]" if unit else key

	def __repr__(self):
		return pretty.pretty_repr(self.__summary__())

	def panel(self):
		print(Panel(Pretty(self.__summary__()),
			title=f"Measurement Stream {f':: {self.name}'*(self.name!=None)}"))


	def edit(self, *fields, page=None, offset=0):
		"""Edit the recorded readings as a table.

		REQUIRES auto_update_explogs to be OFF. With it on, every reading has
		already been serialised into the experiment's results as it was taken,
		and self.readings is a second copy that nothing reads back -- an edit
		would look like it worked and reach nothing. With it off, readings are
		the only copy, so editing them is the whole operation.

		Columns are this stream's declared fields -- fields() -- with their
		units from descriptors. Pass field names to narrow them: a Dialog does
		not scroll sideways, so more than about six columns wants narrowing
		rather than a scrollbar. measureidx is the immutable row label; the
		other fields advance() fills are not shown and not editable.

		Cells are parsed the same way input() parses them, so `54, 49, 36`
		becomes a list. A blank cell becomes None -- the same "not recorded"
		that an untouched field carries.

		Pages itself. `page` defaults to however many rows fit this terminal,
		so a short stream is one screen; longer ones get < Prev / Next >
		buttons and the dialog reopens on the next page with everything typed
		so far already applied. Done closes it, Cancel discards the CURRENT
		page only -- pages already stepped through are kept.

		Edits memory only. write() is a separate call and is never made from
		here: write() APPENDS the whole reading list, so an edit() that wrote
		on its own would append the entire stream again every time it was
		used. Edit as many pages as you like, then write() once.

		Returns the number of cells changed, or None if cancelled on the
		first page without changing anything.
		"""
		if self.auto_update_explogs:
			raise RuntimeError(
				f"MeasurementStream {self.name!r}: edit() needs "
				f"auto_update_explogs to be False. With it True every reading "
				f"is already written to the experiment as it is taken, and "
				f"editing self.readings would change a copy that is never "
				f"written again. Set it False, record, edit, then write().")

		if not self.readings:
			log.warning(f"MeasurementStream {self.name!r}: no readings to edit.")
			return None

		keys = [k for k in (fields or self.fields()) if k in self.descriptors]
		if not keys:
			raise ValueError(f"No declared fields to edit. "
							 f"This stream declares: {', '.join(self.fields())}")

		columns = [(k, self.descriptors[k].get("axis_label") or k,
					self.descriptors[k].get("unit") or self.descriptors[k].get("dtype"))
				   for k in keys]

		page = page or page_size()
		total = len(self.readings)
		changed = 0
		cancelled_immediately = True

		while True:
			offset = max(0, min(offset, max(0, total - 1)))
			with self._lock:
				window = self.readings[offset:offset + page]
				rows = [{k: dict.get(r, k) for k in keys} for r in window]
				labels = [str(dict.get(r, "measureidx", offset + i))
						  for i, r in enumerate(window)]

			last = offset + len(window)
			footer = (f"rows {offset}-{last - 1} of {total}"
					  f"   |   {changed} cell(s) edited so far, nothing written")

			action, edited = grid_dialog(
				f"{self.name}", columns, rows, row_labels=labels, footer=footer,
				has_prev=offset > 0, has_next=last < total)

			if edited is not None:
				cancelled_immediately = False
				with self._lock:
					for reading, cells in zip(window, edited):
						for key, text in cells.items():
							value = parse_value(text) if text.strip() != "" else None
							if dict.get(reading, key) != value:
								reading[key] = value
								changed += 1

			if action == "next":
				offset += page
			elif action == "prev":
				offset -= page
			else:                      ## "done" or "cancel"
				break

		if cancelled_immediately:
			return None

		self._version += 1             ## the .df cache is now stale
		log.info(f"MeasurementStream {self.name!r}: {changed} cell(s) edited "
				 f"in memory. Call write() to put the stream in the experiment.")
		if changed:
			print(f"[yellow]{changed} cell(s) edited. Nothing written yet -- "
				  f"call {self.name or 'stream'}.write() when the table is right.")
		return changed

	def input(self, carry_forward=False, **defaults):
		"""
		Terminal dialog box to enter fields by hand. Some rules:
		  * A blank field is OMITTED, not recorded as "". The field's None
		    default then stands, so a field left blank is missing rather than
		    empty -- which is what it actually is.
		  * The system fields advance() fills (exptime, machinetime, dt,
		    measureidx, clock subscriptions) are never offered.
		carry_forward -- pre-fill monitors from the last reading. `label`,
		`sep`, `df` and the like usually repeat across measurements and retyping
		them is where transcription errors come from. Off by default.
		Measurements are never carried forward -- repeating a measured value
		would be fabrication.

		**defaults -- explicit pre-fills, applied over carry_forward.

		Returns the new reading, or None if cancelled.
		"""
		previous = self.readings[-1] if (carry_forward and self.readings) else {}

		fields, sections = [], {}
		for modality in MODALITIES:
			for key in self.fields(modality):
				if key in defaults:
					value = defaults[key]
				elif modality == "monitor" and key in previous:
					value = dict.get(previous, key)
					## Fields are seeded with None, so a carried-forward blank
					## is nothing to carry.
					if value is None:
						value = ""
				else:
					value = ""
				descriptor = self.descriptors.get(key, {})
				fields.append(Field(key,
									label=descriptor.get("axis_label") or key,
									value=value,
									suffix=descriptor.get("unit")))
				sections[key] = modality + "s"

		if not fields:
			log.error(f"MeasurementStream {self.name!r} declares no fields.")
			return None

		raw = form_dialog(f"{self.name}", fields, sections=sections,
						  ok_text="Record", free_rows=0)
		if raw is None:
			return None

		## Blank means absent, not empty.
		values = {key: parse_value(text) for key, text in raw.items()
				  if text.strip() != ""}
		if not values:
			log.warning(f"MeasurementStream {self.name!r}: every field was "
						f"blank -- nothing recorded.")
			return None

		return self(**values)
