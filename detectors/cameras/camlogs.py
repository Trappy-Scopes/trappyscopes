# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : November 2026                                                  |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+


"""
AI Generated -- new file, Claude (Anthropic), 2026-11.

What the camera stack said during a run, written live into the experiment
folder: libcamera's messages, the kernel log, and the CSI receiver's
interrupt count.

    from detectors.cameras.camlogs import CameraLogs
    logs = CameraLogs().start()     # in the experiment folder
    ...                             # acquisition
    logs.stop()

libcamera.log
    libcamera has its own logger, separate from Python's logging, and writes
    to stderr unless LIBCAMERA_LOG_FILE was set before it first started. In
    the framework that is at launch, when the camera is built, so a script
    cannot set it. Its Python bindings offer only log_set_level, no file or
    target, and the picamera2 maintainers say it "simply can't be controlled
    by us other than through the coarse switch of the environment variable"
    (raspberrypi/picamera2 #309, #1074). So this copies file descriptor 2:
    every line still reaches the terminal, and a copy with the wall time in
    front goes to libcamera.log. Colour codes are stripped from the copy.
    The copy holds everything else written to stderr too (Python warnings,
    tracebacks, child processes' errors).
    If LIBCAMERA_LOG_FILE was set at launch, libcamera writes to that file
    instead of stderr; stop() copies it in as libcamera_file.log.

kernel.log
    `dmesg --follow`, line-buffered. Under setpriv --pdeathsig where
    available, so the child dies with this process instead of appending
    forever after a killed run.

csi_irq()
    Total interrupts on the CSI receiver, the one counter below picamera2:
    still climbing while frames stand still means the link is alive and the
    stall is software-side; flat means the link or the sensor stopped.
"""

import atexit
import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ANSI = re.compile(rb"\x1b\[[0-9;]*m")


def csi_irq():
    """Total interrupts on the CSI receiver (Unicam on a Pi 4, rp1-cfe on a
    Pi 5); -1 if /proc/interrupts cannot be read."""
    try:
        total = 0
        with open("/proc/interrupts") as f:
            for line in f:
                if re.search(r"csi|unicam|rp1-cfe|mipi", line, re.I):
                    total += sum(int(x) for x in line.split()[1:] if x.isdigit())
        return total
    except Exception:
        return -1


def _run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, shell=True, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.stdout.decode("utf-8", "replace")
    except Exception as e:
        return f"<{type(e).__name__}: {e}>"


class StderrTee:
    """Copy everything written to file descriptor 2 into a file, wall time in
    front of each line, while still passing it to the terminal.

    The copy runs on one daemon thread reading a pipe. That thread must keep
    reading: a pipe that is not drained blocks its writers once 64 KB are
    queued, and libcamera writes from the camera thread. So the loop never
    raises, and stop() puts the original stderr back."""

    active = None

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.thread = None

    def start(self):
        if StderrTee.active is not None:          # one tee per process
            StderrTee.active.stop()
        sys.stderr.flush()
        self.saved = os.dup(2)
        self.r, w = os.pipe()
        os.dup2(w, 2)
        os.close(w)
        self.f = open(self.path, "ab")
        self.thread = threading.Thread(target=self._pump, daemon=True,
                                       name="stderr-tee")
        self.thread.start()
        StderrTee.active = self
        return self

    def _write(self, lines):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        try:
            self.f.write(b"".join(stamp.encode() + b" | " + ANSI.sub(b"", l) + b"\n"
                                  for l in lines))
            self.f.flush()
        except Exception:
            pass

    def _pump(self):
        buf = b""
        while True:
            try:
                data = os.read(self.r, 65536)
            except Exception:
                break
            if not data:
                break
            try:
                os.write(self.saved, data)        # the terminal, unchanged
            except Exception:
                pass
            buf += data
            *lines, buf = buf.split(b"\n")
            if lines:
                self._write(lines)
        if buf:
            self._write([buf])

    def stop(self):
        if StderrTee.active is not self:
            return
        StderrTee.active = None
        try:
            sys.stderr.flush()
        except Exception:
            pass
        os.dup2(self.saved, 2)    # drops fd 2's hold on the pipe: the reader sees EOF
        self.thread.join(timeout=2)
        for fd in (self.r, self.saved):
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            self.f.close()
        except Exception:
            pass


class KernelLog:
    """Stream kernel messages to a file for the whole run.

    `dmesg --follow` rather than snapshots: the ring buffer is bounded and a
    long run can wrap it. stdbuf -oL because dmesg block-buffers into a file
    and the last lines before a failure would be lost."""

    CANDIDATES = (
        ["setpriv", "--pdeathsig", "TERM", "stdbuf", "-oL", "dmesg", "--follow", "-T"],
        ["stdbuf", "-oL", "dmesg", "--follow", "-T"],
        ["sudo", "-n", "stdbuf", "-oL", "dmesg", "--follow", "-T"],
        ["dmesg", "--follow", "-T"],
    )
    REFUSED = re.compile(r"operation not permitted|password is required|not found|"
                         r"read kernel buffer failed|invalid option|unrecognized|"
                         r"unknown option|illegal option|permission denied|must be root|usage:", re.I)

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.proc = None
        self.command = None

    def start(self):
        for cmd in self.CANDIDATES:
            try:
                with open(self.path, "ab", buffering=0) as f:
                    start = f.tell()
                    proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
            except Exception:
                continue
            ## Liveness alone is too weak: sudo -n stays alive briefly before
            ## failing, and a restricted dmesg writes its refusal and exits.
            ## Checked twice, because a refusal can take a moment to appear.
            ok = True
            for wait in (0.8, 0.8):
                time.sleep(wait)
                try:
                    with open(self.path, "rb") as r:
                        r.seek(start)
                        said = r.read(400).decode("utf-8", "replace")
                except Exception:
                    said = ""
                ok = ok and proc.poll() is None and not self.REFUSED.search(said)
            if ok:
                self.proc, self.command = proc, " ".join(cmd)
                atexit.register(self.stop)
                return True
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
            try:                                  # drop the refusal text
                with open(self.path, "rb+") as f:
                    f.truncate(start)
            except Exception:
                pass
        return False

    def stop(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


class CameraLogs:
    """libcamera.log and kernel.log together, in one folder (default: the
    current directory, which is the experiment's while one is open)."""

    current = None

    def __init__(self, folder="."):
        self.folder = os.path.abspath(folder)
        self.tee = StderrTee(os.path.join(self.folder, "libcamera.log"))
        self.kernel = KernelLog(os.path.join(self.folder, "kernel.log"))
        self.kernel_ok = False

    def start(self):
        self.tee.start()
        self.kernel_ok = self.kernel.start()
        CameraLogs.current = self
        print(f"camlogs: libcamera -> {self.libcamera_path}; kernel.log "
              f"{'via ' + self.kernel.command if self.kernel_ok else 'unavailable (dmesg restricted)'}")
        return self

    def stop(self):
        self.kernel.stop()
        self.tee.stop()
        env = os.environ.get("LIBCAMERA_LOG_FILE")
        if env and os.path.isfile(env):
            try:
                shutil.copy2(env, os.path.join(self.folder, "libcamera_file.log"))
            except Exception:
                pass

    @property
    def libcamera_path(self):
        """Where libcamera's lines are going: its own file if one was set at
        launch, otherwise the stderr copy."""
        env = os.environ.get("LIBCAMERA_LOG_FILE")
        return env if env and os.path.isfile(env) else self.tee.path

    def tail(self, n=40):
        p = self.libcamera_path
        return _run(f"tail -{int(n)} '{p}'") if os.path.exists(p) else ""

    def reason(self, since=None):
        """Why the camera stopped, in libcamera's words: it logs the timeout
        and returns, so its log is the only place the reason exists. Searches
        the log from byte offset `since` (default: its last 256 KB), so other
        stderr output cannot push the line out of view. Returns (label, the
        matching lines or the tail)."""
        p = self.libcamera_path
        try:
            with open(p, "rb") as f:
                size = f.seek(0, 2)
                f.seek(since if since is not None else max(0, size - 262144))
                text = f.read().decode("utf-8", "replace")
        except Exception:
            text = ""
        for pattern, label in (("frontend has timed out", "frontend_timeout"),
                               ("Dequeue timer", "dequeue_timeout"),
                               ("vc_sm_cma", "cma_failure"),
                               ("v4l2_m2m", "v4l2_poll_block")):
            hits = [l for l in text.splitlines() if pattern.lower() in l.lower()]
            if hits:
                return label, "\n".join(hits[-5:])
        return "unknown", "\n".join(text.splitlines()[-20:])

    def size(self):
        """Current size of the libcamera log, as an offset for reason()."""
        try:
            return os.path.getsize(self.libcamera_path)
        except Exception:
            return 0

    def snapshot(self, path):
        """Machine state at a failure, into one text file. Returns its path."""
        try:
            with open(path, "w") as f:
                f.write(f"## {datetime.datetime.now()}\n")
                for title, cmd in (
                        ("dmesg", "dmesg -T 2>/dev/null | tail -60"),
                        ("journal", "journalctl -b --no-pager 2>/dev/null | tail -40"),
                        ("throttled", "vcgencmd get_throttled; vcgencmd measure_temp; "
                                      "vcgencmd measure_volts"),
                        ("csi interrupts", "grep -iE 'csi|unicam|rp1-cfe|mipi' /proc/interrupts"),
                        ("meminfo", "grep -iE 'cma|MemAvailable' /proc/meminfo")):
                    f.write(f"\n===== {title} =====\n{_run(cmd)}")
                f.write(f"\n===== libcamera ({self.libcamera_path}) =====\n{self.tail(40)}")
            return path
        except Exception:
            return None
