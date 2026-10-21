"""AI Generated -- serial processor groups that are not MicroPython boards.

Written by Claude (Anthropic), 2026-10, for the Poseidon syringe-pump
integration. See docs/notes/fixedvocab_serial_device.pdf for the interface on
one page, and docs/notes/restructuring.md §15 for the reasoning.

Two classes:

	SerialDevice            the shared base: finding a board by its USB
	                        descriptors (VID, PID, serial number) without ever
	                        opening a port. SerialMPDevice inherits it too.

	FixedVocabSerialDevice  a board whose firmware is sealed -- flashed once,
	                        no REPL, it only understands its own command words
	                        (an Arduino running a sketch). The host declares
	                        those words as templates, and incoming frames are
	                        matched by regex and dispatched to callbacks.

Why identity comes from USB descriptors: the OS reads them when the device
enumerates, so nothing has to be opened to know which board is which. That
matters for an Arduino Uno, because opening its port pulses DTR and reboots
it. On a genuine Uno the serial number is factory-set in the ATmega16U2 and
unique per board -- the same kind of key as a Pico's UID.

A FixedVocabSerialDevice deliberately does NOT emit proxies the way
ProcessorGroup.__getattr__ does for MicroPython boards: there is no
interpreter on the other end to forward an attribute to, so a typo must fail
loudly instead of returning a proxy that silently does nothing.
"""

import logging as log
import queue
import re
import string
import threading
import time
from collections import deque

from .abstractprocessorgroup import ProcessorGroup as AbstractProcessorGroup


## ------------------------------------------------------------- exceptions
class SerialDeviceError(Exception):
	"""Base for everything a FixedVocabSerialDevice raises on purpose."""


class VocabularyError(SerialDeviceError):
	"""Unknown command word, or a template field missing / unexpected."""


class FrameTooLong(SerialDeviceError):
	"""The frame is longer than the firmware's input buffer would keep."""


class AckTimeout(SerialDeviceError):
	"""No acknowledging frame arrived in time."""


class NotConnected(SerialDeviceError):
	"""The port is not open, or the board could not be found."""


## ----------------------------------------------------------- shared base
class SerialDevice(AbstractProcessorGroup):
	"""Port discovery shared by every serial processor group.

	No __init__ of its own on purpose: SerialMPDevice reaches this class
	through MicropythonDevice's super().__init__(name), so anything added
	here has to keep passing `name` straight through.
	"""

	@staticmethod
	def ports():
		"""Every serial port the OS knows, as plain dicts. Opens nothing."""
		try:
			from serial.tools import list_ports
		except ImportError:
			log.error("pyserial is not installed -- no serial ports to list.")
			return []
		found = []
		for p in list_ports.comports():
			found.append({
				"device": p.device,
				"vid": p.vid,
				"pid": p.pid,
				"serial_number": p.serial_number,
				"location": p.location,
				"manufacturer": p.manufacturer,
				"description": None if p.description in (None, "n/a") else p.description,
			})
		return found

	@staticmethod
	def print_all_ports():
		"""Table of ports with VID / PID / serial number, for pasting into a config."""
		from rich.console import Console
		from rich.table import Table

		hexid = lambda v: "" if v is None else f"0x{v:04x}"
		table = Table(title="Serial ports (read from USB enumeration; nothing opened)")
		for col in ("port", "vid", "pid", "serial_number", "description"):
			table.add_column(col)
		for p in SerialDevice.ports():
			table.add_row(p["device"], hexid(p["vid"]), hexid(p["pid"]),
						  p["serial_number"] or "", p["description"] or "")
		Console().print(table)

	@staticmethod
	def find(serial_number=None, vid=None, pid=None, port=None):
		"""The port dict matching these descriptors, or None.

		`serial_number` is the key. `vid` / `pid` are only a guard: a board
		whose serial matches but whose VID/PID do not is refused, so a typo in
		a config cannot land on the wrong kind of device. `port` (an explicit
		path) is the fallback for boards without a serial number.
		"""
		candidates = SerialDevice.ports()
		if serial_number is not None:
			candidates = [p for p in candidates if p["serial_number"] == str(serial_number)]
		elif port is not None:
			candidates = [p for p in candidates if p["device"] == port]
		else:
			return None

		for p in candidates:
			if vid is not None and p["vid"] != vid:
				log.error(f"Serial {serial_number} found on {p['device']} but VID is "
						  f"{p['vid']!r}, expected {vid!r} -- refusing it.")
				continue
			if pid is not None and p["pid"] != pid:
				log.error(f"Serial {serial_number} found on {p['device']} but PID is "
						  f"{p['pid']!r}, expected {pid!r} -- refusing it.")
				continue
			return p
		return None


## ---------------------------------------------------- the sealed device
class _Command:
	def __init__(self, word, template, ack, timeout):
		self.word = word
		self.template = template
		self.ack = re.compile(ack) if ack else None
		self.timeout = timeout
		self.fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}


class Handler:
	"""What on() returns; pass it to off() to remove the handler."""

	def __init__(self, pattern, callback, once, queued):
		self.pattern = re.compile(pattern)
		self.callback = callback
		self.once = once
		self.queued = queued

	def __repr__(self):
		return f"<Handler {self.pattern.pattern!r}{' once' if self.once else ''}>"


class _Waiter:
	def __init__(self, pattern):
		self.pattern = pattern
		self.event = threading.Event()
		self.match = None


class FixedVocabSerialDevice(SerialDevice):
	"""A serial board that only understands a fixed set of command words.

		link = FixedVocabSerialDevice("pumps", serial_number="7563...", vid=0x2341,
		                              baud=230400, frame=("<", ">"), max_frame=63,
		                              ready=r"^Arduino is ready$")
		link.command("RUN", "RUN,DIST,{pumps},0.0,{dir},{d1},{d2},{d3}", ack=r"^mode: RUN ")
		link.on(r"^DISP(\\d)\\|(-?\\d+)$", lambda m, raw: print(m[1], m[2]))
		link.send("RUN", pumps="1", dir="F", d1=800, d2=0, d3=0)

	Outgoing: send() fills a declared template, refuses anything longer than
	max_frame, writes it under a lock (one command in flight) and, when the
	word has an ack pattern, waits for the matching frame and returns its
	re.Match.

	Incoming: one reader thread splits the byte stream into frames. Each frame
	is offered first to whoever is waiting (a send() for its ack, or an
	expect()), then to the on() handlers in registration order -- first match
	wins -- and otherwise lands in `unhandled`. Bytes outside any frame (a
	sketch's debug prints) go to `noise`.

	`opener` replaces serial.Serial for tests and simulators: any callable
	(port, baud) -> object with read(n), write(bytes), close() and in_waiting.
	"""

	def __init__(self, name, serial_number=None, vid=None, pid=None, port=None,
				 baud=115200, frame=("<", ">"), max_frame=None, ready=None,
				 ready_timeout=5.0, ack_timeout=2.0, encoding="ascii", vocab=None,
				 connect=True, opener=None, history=500):
		super().__init__(name)
		self.serial_number = None if serial_number is None else str(serial_number)
		self.vid, self.pid = vid, pid
		self.port = port
		self.baud = baud
		self.max_frame = max_frame
		self.ready = re.compile(ready) if ready else None
		self.ready_timeout = ready_timeout
		self.ack_timeout = ack_timeout
		self.encoding = encoding
		self.opener = opener

		if isinstance(frame, str):
			self._start, self._end = None, frame
		else:
			self._start, self._end = frame

		self._commands = {}
		self._handlers = []
		self._waiters = []
		self._lock = threading.Lock()			## guards _handlers / _waiters
		self._send_lock = threading.Lock()		## one command in flight

		self._ser = None
		self._reader = None
		self._running = False
		self._worker = None
		self._work = queue.Queue()

		self.connected = False
		self.ready_seen = False
		self.unhandled = deque(maxlen=history)
		self.noise = deque(maxlen=history)
		self.log = deque(maxlen=history)

		if vocab:
			self.load_vocab(vocab)
		if connect:
			self.connect()

	## A sealed board has nothing to proxy to -- see the module docstring.
	def __getattr__(self, name):
		raise AttributeError(f"{type(self).__name__} has no attribute {name!r} "
							 "(sealed device: only declared command words exist)")

	def __getstate__(self):
		return {"name": self.name, "serial_number": self.serial_number, "port": self.port,
				"baud": self.baud, "commands": sorted(self._commands)}

	def __repr__(self):
		state = "connected" if self.connected else "closed"
		return f"<FixedVocabSerialDevice {self.name} :: {self.port or self.serial_number} :: {state}>"

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()

	## ---------------------------------------------------------- vocabulary
	def command(self, word, template, ack=None, timeout=None):
		"""Declare an outgoing word. `template` uses str.format named fields."""
		if not word or not isinstance(word, str):
			raise VocabularyError(f"Command word must be a non-empty string, not {word!r}")
		self._commands[word] = _Command(word, template, ack, timeout)
		return self._commands[word]

	def on(self, pattern, callback, once=False, queued=False):
		"""Call callback(match, raw_frame) for incoming frames matching pattern.

		Callbacks run on the reader thread and must be quick; queued=True runs
		them on a worker thread instead. An exception in a callback is logged
		and never stops the reader.
		"""
		handler = Handler(pattern, callback, once, queued)
		with self._lock:
			self._handlers.append(handler)
		return handler

	def off(self, handler):
		with self._lock:
			if handler in self._handlers:
				self._handlers.remove(handler)

	def load_vocab(self, spec):
		"""Declare commands from a dict or a YAML file path.

			commands:
			  RUN: {template: "RUN,DIST,{pumps}", ack: "^mode: RUN ", timeout: 2}

		Handlers need callables, so they cannot come from YAML; use on().
		"""
		if isinstance(spec, str):
			import yaml
			with open(spec) as f:
				spec = yaml.safe_load(f) or {}
		for word, entry in (spec.get("commands") or {}).items():
			if isinstance(entry, str):
				entry = {"template": entry}
			self.command(word, entry["template"], ack=entry.get("ack"),
						 timeout=entry.get("timeout"))

	@property
	def vocabulary(self):
		return {"commands": {w: c.template for w, c in self._commands.items()},
				"handlers": [h.pattern.pattern for h in self._handlers]}

	## ----------------------------------------------------------- lifecycle
	def connect(self):
		"""Find the board, open it, start the reader, wait for its banner."""
		if self.connected:
			return True
		port = self.port
		if self.serial_number is not None:
			found = SerialDevice.find(self.serial_number, self.vid, self.pid)
			if found is None and self.opener is None:
				raise NotConnected(f"{self.name}: no board with serial number "
								   f"{self.serial_number} is plugged in.")
			if found is not None:
				port = found["device"]
		if port is None:
			raise NotConnected(f"{self.name}: give a serial_number or a port.")

		banner = self._add_waiter(self.ready) if self.ready else None
		try:
			if self.opener is not None:
				self._ser = self.opener(port, self.baud)
			else:
				import serial
				self._ser = serial.Serial(port, self.baud, timeout=0.05, write_timeout=2)
		except Exception as err:
			self._drop_waiter(banner)
			raise NotConnected(f"{self.name}: could not open {port}: {err}") from err

		self.port = port
		self.connected = True
		self._running = True
		self._reader = threading.Thread(target=self._read_loop, name=f"{self.name}-reader",
										daemon=True)
		self._reader.start()
		log.info(f"{self.name}: opened {port} at {self.baud} baud.")

		if banner is not None:
			self.ready_seen = banner.event.wait(self.ready_timeout)
			self._drop_waiter(banner)
			if not self.ready_seen:
				## Not fatal: a board that did not reset on open never prints
				## its banner, and still works.
				log.warning(f"{self.name}: no ready banner within {self.ready_timeout}s "
							"-- continuing; the board may not have reset.")
		return True

	def disconnect(self):
		self._running = False
		if self._reader is not None and self._reader is not threading.current_thread():
			self._reader.join(timeout=2)
		self._reader = None
		if self._ser is not None:
			try:
				self._ser.close()
			except Exception as err:
				log.debug(f"{self.name}: close failed: {err}")
		self._ser = None
		self.connected = False

	def reconnect(self):
		"""Close and reopen. On an Uno this reboots the board."""
		self.disconnect()
		return self.connect()

	def close(self):
		"""What ScopeAssembly calls at exit."""
		self.disconnect()
		if self._worker is not None:
			self._work.put(None)
			self._worker = None

	## ----------------------------------------------------------- execution
	def send(self, word, wait=True, timeout=None, **fields):
		"""Send a declared word; returns the ack's re.Match (or None)."""
		cmd = self._commands.get(word)
		if cmd is None:
			raise VocabularyError(f"{self.name}: unknown command word {word!r}. "
								  f"Known: {sorted(self._commands)}")
		missing = cmd.fields - set(fields)
		extra = set(fields) - cmd.fields
		if missing or extra:
			raise VocabularyError(f"{self.name}: {word} needs fields {sorted(cmd.fields)}; "
								  f"missing {sorted(missing)}, unexpected {sorted(extra)}")
		body = cmd.template.format(**fields)
		self._check_body(body)

		with self._send_lock:
			waiter = self._add_waiter(cmd.ack) if (cmd.ack and wait) else None
			self._write(self._wrap(body), "tx")
			if waiter is None:
				return None
			limit = timeout or cmd.timeout or self.ack_timeout
			got = waiter.event.wait(limit)
			self._drop_waiter(waiter)
			if not got:
				raise AckTimeout(f"{self.name}: no ack for {word} within {limit}s "
								 f"(sent {body!r})")
			return waiter.match

	def expect(self, pattern, timeout=None):
		"""Wait for the next frame matching pattern; the match, or None on timeout.

		Only frames that arrive after this call are seen.
		"""
		waiter = self._add_waiter(re.compile(pattern))
		got = waiter.event.wait(timeout or self.ack_timeout)
		self._drop_waiter(waiter)
		return waiter.match if got else None

	def write_raw(self, text):
		"""Escape hatch: write text as-is, with no vocabulary check."""
		self._write(text, "raw")

	## ------------------------------------------------------------ internals
	def _wrap(self, body):
		return f"{self._start or ''}{body}{self._end}"

	def _check_body(self, body):
		for marker in (self._start, self._end):
			if marker and marker in body:
				raise VocabularyError(f"{self.name}: frame body contains the framing "
									  f"character {marker!r}: {body!r}")
		if self.max_frame is not None and len(body) > self.max_frame:
			raise FrameTooLong(f"{self.name}: {len(body)} characters, the firmware keeps "
							   f"only {self.max_frame}: {body!r}")

	def _write(self, text, direction):
		if not self.connected or self._ser is None:
			raise NotConnected(f"{self.name}: not connected.")
		self._ser.write(text.encode(self.encoding))
		self.log.append((time.time(), direction, text))
		log.debug(f"{self.name} << {text!r}")

	def _add_waiter(self, pattern):
		waiter = _Waiter(pattern)
		with self._lock:
			self._waiters.append(waiter)
		return waiter

	def _drop_waiter(self, waiter):
		if waiter is None:
			return
		with self._lock:
			if waiter in self._waiters:
				self._waiters.remove(waiter)

	def _read_loop(self):
		buf, in_frame, junk = [], False, []
		while self._running:
			try:
				ser = self._ser
				waiting = getattr(ser, "in_waiting", 0) if ser else 0
				data = ser.read(waiting or 1) if ser else b""
			except Exception as err:
				if self._running:
					log.error(f"{self.name}: read failed, link closed: {err}")
					self.connected = False
				break
			if not data:
				continue
			for ch in data.decode(self.encoding, errors="replace"):
				if self._start is None:					## line framing
					if ch == self._end:
						text = "".join(buf).strip("\r")
						buf = []
						if text:
							self._dispatch(text)
					else:
						buf.append(ch)
					continue
				if ch == self._start:
					if in_frame and buf:
						self.noise.append(self._start + "".join(buf))
					buf, in_frame = [], True
				elif ch == self._end and in_frame:
					in_frame = False
					self._dispatch("".join(buf))
					buf = []
				elif in_frame:
					buf.append(ch)
				elif ch == "\n":
					line = "".join(junk).strip("\r")
					junk = []
					if line:
						self.noise.append(line)
				else:
					junk.append(ch)

	def _dispatch(self, frame):
		self.log.append((time.time(), "rx", frame))
		log.debug(f"{self.name} >> {frame!r}")
		with self._lock:
			for waiter in self._waiters:
				if not waiter.event.is_set():
					m = waiter.pattern.search(frame)
					if m:
						waiter.match = m
						waiter.event.set()
						return
			hit = None
			for handler in self._handlers:
				m = handler.pattern.search(frame)
				if m:
					hit = (handler, m)
					if handler.once:
						self._handlers.remove(handler)
					break
		if hit is None:
			self.unhandled.append(frame)
			return
		handler, m = hit
		if handler.queued:
			self._ensure_worker()
			self._work.put((handler, m, frame))
		else:
			self._call(handler, m, frame)

	def _call(self, handler, m, frame):
		try:
			handler.callback(m, frame)
		except Exception:
			log.exception(f"{self.name}: handler {handler!r} failed on {frame!r}")

	def _ensure_worker(self):
		if self._worker is None:
			def work():
				while True:
					item = self._work.get()
					if item is None:
						return
					self._call(*item)
			self._worker = threading.Thread(target=work, name=f"{self.name}-worker",
											daemon=True)
			self._worker.start()
