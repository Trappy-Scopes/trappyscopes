#from abcs.camera import AbstractCamera

from copy import deepcopy
import logging as log
import time
import subprocess
from io import StringIO 
import atexit
import numpy as np
import os
import gc
import logging as log

## picamera2 imports
from picamera2 import Picamera2, Preview
from picamera2.outputs import FileOutput, Output, SplittableOutput
from picamera2.encoders import JpegEncoder, H264Encoder, MJPEGEncoder
from libcamera import controls
import simplejpeg
from picamera2.request import MappedArray
from threading import Event, Lock
## TS imports
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.permaconfig.sharing import Share
from core.precision.timing import precise_sleep
from detectors.cameras.abstractcamera import Camera as AbstractCamera

from expframework.experiment import Experiment


class JpegEncoderGrayChannel(JpegEncoder):
    """
    Encodes a single colour channel as a grayscale JPEG, discarding the rest.

    Channel order
    -------------
    With the configured format "BGR888" the array is laid out [R, G, B] --
    libcamera names its formats by byte order within a little-endian word, so
    the name reads backwards relative to the numpy axis. Per the Picamera2
    manual (Appendix A, Table 1): "BGR888 ... Each pixel is laid out as
    [R, G, B]" and "RGB888 ... [B, G, R]". So index 0 is RED here.

    channel: "r", "g" or "b" (or an int index) -- the channel that is encoded.

    intensity_channels: optional, default () == OFF. Names of the *other*
    channels whose mean intensity should be recorded per frame into
    `self.intensities`. This costs a full-frame reduction per channel per
    frame inside the encoder thread, so it is opt-in: leave it empty and this
    class behaves exactly like the single-channel encoder it replaces.

    Intensities are accumulated in memory and must be drained by the caller
    after recording stops. Do NOT write them to a MeasurementStream per frame:
    MeasurementStream.__call__ triggers Experiment.__save__(), i.e. a YAML
    write to disk, which will not keep up with the frame rate.
    """

    CHANNELS = {"r": 0, "g": 1, "b": 2}
    NAMES = ("r", "g", "b")

    def __init__(self, *args, channel="r", intensity_channels=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.channel = self.CHANNELS[channel.lower()] if isinstance(channel, str) else int(channel)
        self.intensity_channels = tuple(
            self.CHANNELS[c.lower()] if isinstance(c, str) else int(c)
            for c in intensity_channels
        )
        ## One record per frame: {"t_ns": <sensor timestamp>, "g": mean, ...}
        ## Empty unless intensity_channels was given. Drain it with drain().
        self.intensities = []
        self._lock = Lock()

    def __repr__(self):
        """Readable identity for the experiment event log.

        Camera.read() reduces non-primitive kwargs with str() before logging
        them, so without this the recorded encoder is an unhelpful
        `<...JpegEncoderGrayChannel object at 0x...>`.
        """
        return (f"{type(self).__name__}(channel={self.NAMES[self.channel]}, "
                f"intensity_channels="
                f"{tuple(self.NAMES[c] for c in self.intensity_channels)}, "
                f"q={getattr(self, 'q', None)}, "
                f"num_threads={getattr(self, 'num_threads', None)})")

    def encode_func(self, request, name):
        """Performs encoding

        :param request: Request
        :type request: request
        :param name: Name
        :type name: str
        :return: Jpeg image
        :rtype: bytes
        """
        with MappedArray(request, name) as m:
            self.colour_space = self.FORMAT_TABLE[request.config[name]["format"]]
            width, height = request.config[name]['size']
            frame = m.array.reshape(height, width, 3)

            if self.intensity_channels:
                self.__record_intensities__(request, frame)

            ch_frame = frame[..., self.channel:self.channel + 1].copy(order='C')
            return simplejpeg.encode_jpeg(ch_frame,
                quality=self.q, colorspace="GRAY", colorsubsampling='Gray')

    def __record_intensities__(self, request, frame):
        """
        One record per frame, keyed by the sensor timestamp rather than by a
        counter: JpegEncoder runs encode_func on a thread pool, so frames are
        NOT measured in order. Sort by "t_ns" to line the records up with the
        .tpts file; drain() already does that.
        """
        try:
            t_ns = request.get_metadata()["SensorTimestamp"]
        except Exception:
            t_ns = time.monotonic_ns()

        record = {"t_ns": t_ns}
        record.update({self.NAMES[c]: float(frame[..., c].mean())
                       for c in self.intensity_channels})

        with self._lock:
            self.intensities.append(record)
            batch = self.__take_batch__()
        if batch:
            self.__flush__(batch)

    def __take_batch__(self):
        """
        Called with self._lock held. Return a list of records to hand to
        __flush__ (and detach from self.intensities), or None to keep
        accumulating. The base class never batches.
        """
        return None

    def __flush__(self, batch):
        """Dispose of a batch taken by __take_batch__. No-op in the base."""
        pass

    def drain(self):
        """
        Take every record accumulated so far, in timestamp order, and reset.
        Call this after stop_recording().
        """
        with self._lock:
            batch, self.intensities = self.intensities, []
        return sorted(batch, key=lambda r: r["t_ns"])


class JpegEncoderGrayRedCh(JpegEncoderGrayChannel):
    """Backwards-compatible alias: the red channel, no intensity mapping.

    Kept because deployed scripts and the actions below name it directly.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("channel", "r")
        super().__init__(*args, **kwargs)


class JpegEncoderRedWithBGStats(JpegEncoderGrayChannel):
    """
    Records the RED channel as a grayscale MJPEG while measuring the mean
    intensity of the BLUE and GREEN channels on every frame. This is the
    encoder to pass to `vid_mjpeg_tpts` when the blue/green signal is wanted
    alongside a red-channel recording.

    Cost: two full-frame means per frame, inside the encoder thread pool. If
    the recording starts dropping frames, either reduce `intensity_channels`
    to one channel or raise num_threads.

    flush_fn
        Optional callable invoked with a list of records (oldest first) about
        every `flush_interval_s` seconds, and once more from drain(). It runs
        on an encoder thread, so it must be quick -- a MeasurementStream write
        every 60 s is fine, one per frame is not (MeasurementStream.__call__
        triggers Experiment.__save__(), i.e. a YAML write to disk). Exceptions
        raised by it are logged and swallowed so a bad callback cannot kill a
        recording.

        With flush_fn set, self.intensities only ever holds the records since
        the last flush -- the callback owns the rest.

    Each record is {"t_ns": <SensorTimestamp>, "g": <mean>, "b": <mean>},
    i.e. directly writable as CSV or YAML.

    Example
    -------
        rows = []
        enc = JpegEncoderRedWithBGStats(q=100, num_threads=3,
                                        flush_fn=rows.extend,
                                        flush_interval_s=30)
        scope.cam.read("vid_mjpeg_tpts", "run.mjpeg", tsec=600, encoder=enc)
        enc.drain()          ## flushes the tail into rows
    """

    def __init__(self, *args, flush_fn=None, flush_interval_s=60.0, **kwargs):
        kwargs["channel"] = "r"
        kwargs.setdefault("intensity_channels", ("g", "b"))
        super().__init__(*args, **kwargs)
        self.flush_fn = flush_fn
        self.flush_interval_s = flush_interval_s
        self._next_flush = None

    def __take_batch__(self):
        """Called with self._lock held."""
        if self.flush_fn is None or not self.flush_interval_s:
            return None

        now = time.monotonic()
        if self._next_flush is None:        ## first frame: start the clock
            self._next_flush = now + self.flush_interval_s
            return None
        if now < self._next_flush:
            return None

        self._next_flush = now + self.flush_interval_s
        batch, self.intensities = self.intensities, []
        return batch

    def __flush__(self, batch):
        if not batch:
            return
        try:
            self.flush_fn(sorted(batch, key=lambda r: r["t_ns"]))
        except Exception as e:
            log.error(f"JpegEncoderRedWithBGStats: flush_fn failed: {e}")

    def drain(self):
        """Take the tail, hand it to flush_fn as well, and return it."""
        batch = super().drain()
        if self.flush_fn is not None:
            self.__flush__(batch)
        return batch


class Camera(AbstractCamera):
    """
    Camera object framework specialised for Raspberry Pi HQ Camera.
    Implementation used Picamera v2 python library.


    config parameter can be used to pass a configuration dict. 
    The default mode is to configure the camera for a "video" mode.

    Development rules:
    1. Create camera -> configure -> start recording, previews, etc.
    2. Normal modes always open and reconfigure the camera. Then they close on exit.
    """

    ## Default encoders
    ENCODERS = {"h264encoder":  H264Encoder,
                "mjpegencoder": MJPEGEncoder,
                "jpegencoder":  JpegEncoder}


    def __init__(self):
         
        #Picamera2.set_logging(Share.logginglevel)
        self.cam = None
        self.cam_fsaddr = None
        self.opentime_ns = None
        self.cam_manager_cleanup = None

        ## Detector actions are specified.
        self.actions = {
                          "preview"       : self.preview,
                          "img"           : self.__image__,
                          "timelapse"     : self.__timelapse__,
                          "vid"           : self.__video__,
                          "vid_noprev"    : self.__video_noprev__,
                          "vid_mjpeg_tpts": self.__vid_mjpeg_tpts__,
                          "vid_mjpeg_tpts_multi":self.__vid_mjpeg_tpts_multi__,
                          "img_formatted":self.__image_fomatted__,
                          "lux_estimate" : self.__lux_estimate__
                        }

        ## Controls are different than config in this API
        self.options = {"quality":100, "compression":0}
        self.controls = {"ExposureTime": 18*1000, "AnalogueGain": 1.0, "AwbEnable": False, "AeEnable":False, 
                         "ColourGains":(0.0,0.0), "Contrast":2.0, 
                         "NoiseReductionMode":controls.draft.NoiseReductionModeEnum.Fast, 
                         'FrameDurationLimits':(int(1e6/25), int(1e6/25))
                        }
        self.cam = Picamera2(tuning="/usr/share/libcamera/ipa/rpi/vc4/imx477_scientific.json")
        self.config = self.cam.create_video_configuration(buffer_count=10, 
            main={"size":(1520, 1520), "format":"BGR888"}, queue=False,
            controls=self.controls,
            encode="main", display="main")

        # Preview Window Settings
        self.preview_type = Preview.DRM      #Preview.QT # Other options: Preview.DRM, Preview.QT, Preview.QTGL
        self.preview_options = {"height":1080, "width":1080, "x":504, "y":0}
        self.win_title_fields = ["ExposureTime", "FrameDuration"]
        self.cam.close()

    def __getstate__(self):
        """Returns pickalable camera state.
        """
        def picklable(value):
            if isinstance(value, (str, int, float, bool, type(None))):
                return value
            if isinstance(value, dict):
                return {k: picklable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return type(value)(picklable(v) for v in value)
            return str(value)   ## libcamera Transform / ColorSpace / control enums

        return {key: picklable(value) for key, value in self.config.items()}

    def configure(self, *args, **kwargs):
        # deepcopy breaks on some microscopes
        self.cam.options.update(self.options.copy()) ## Set compression
        self.cam.configure(self.config.copy())
        log.info("Camera configured.")

    def open(self):
        self.opentime_ns = time.perf_counter()
        log.info("TS::Camera::PiCamera2 Camera was opened.")
        self.cam = Picamera2(tuning="/usr/share/libcamera/ipa/rpi/vc4/imx477_scientific.json")
        
        self.cam.configure()
        self.cam.title_fields = self.win_title_fields
        
        #self.cam_fsaddr = None   ## TODO
        self.cam_manager_cleanup = lambda : self.cam.camera_manager.cleanup(self.cam.cam_num) 
        atexit.register(self.close)


    def is_open(self):
        return self.cam.is_open


    def close(self):
        if self.cam.is_open:
            self.cam.close()
        now = time.perf_counter()
        ## opentime_ns is only set by open(); the constructor opens the hardware
        ## but leaves it None, so a close() before any open() would raise here.
        duration = f"{now-self.opentime_ns:.2f} s" if self.opentime_ns else "never opened"
        log.info(f"PiCamera2 Camera was closed: {now} : duration {duration}.")
        #try:
        #    self.cam_manager_cleanup()
        #except Exception as e:
        #    log.error(e)
        atexit.unregister(self.close)


    def preview(self, tsec=10):
        self.cam.start_preview(self.preview_type, **self.preview_options)
        try:
            self.cam.start()
            precise_sleep(tsec)
        except KeyboardInterrupt:
            print("Preview has ended...")
        finally:
            self.cam.stop()
            self.cam.stop_preview()
            gc.collect()

    def rpreview(self, tsec=10, channel="r"):
        """
        Live preview of a single colour channel, as grayscale. Nothing is
        written to file.

        channel: "r" (default), "g" or "b", or an int index. The indices are
        the ones documented on JpegEncoderGrayChannel: with format "BGR888"
        the array is laid out [R, G, B], so "r" is 0.

        No encoder runs in preview mode, so nothing else is reading the frame
        buffer and it can simply be modified in place: the chosen channel is
        broadcast into the other two. That is only safe here -- the same trick
        during a recording would reach the encoder as well, because
        pre_callback and post_callback both run *before* the encoder and the
        preview (Picamera2 manual, 8.2.2).

        post_callback is cleared in the finally block so a grayscale preview
        cannot leak into a later recording or capture_file().

        Cost: two full-frame writes per displayed frame on the camera event
        loop (~4.6 MB at 1520x1520). It cannot be throttled -- skipping frames
        would make the preview flicker between colour and gray.
        """
        ch = JpegEncoderGrayChannel.CHANNELS[channel.lower()] \
             if isinstance(channel, str) else int(channel)
        others = tuple(c for c in (0, 1, 2) if c != ch)

        def to_grayscale(request):
            with MappedArray(request, "main") as m:
                for other in others:
                    m.array[..., other] = m.array[..., ch]

        self.cam.post_callback = to_grayscale
        self.cam.start_preview(self.preview_type, **self.preview_options)
        try:
            self.cam.start()
            precise_sleep(tsec)
        except KeyboardInterrupt:
            print("Preview has ended...")
        finally:
            self.cam.post_callback = None
            self.cam.stop()
            self.cam.stop_preview()
            gc.collect()

    ### ----------------------------- ACTION IMPLEMENTATIONS ---------------------------------------------
    def __image__(self, filename, *args, tsec=3, show_preview=False, **kwargs):
        """
        Capture an image. 
        tsec : delay without capture.
        """

        if show_preview:
            self.cam.start_preview()
        precise_sleep(1)
        self.cam.start()
        precise_sleep(tsec)
        self.cam.capture_file(filename)
        self.cam.stop()
        self.cam.stop_preview()


    def __timelapse__(self, filename, *args, show_preview=True, **kwargs):
        """
        Capture a timelapse sequence. Each frame is written next to `filename`
        as <nnn>_<stem>.<ext>, i.e. preceded by the capture sequence number.

        frames  : number of frames to capture.
        delay_s : delay between frames, in seconds.

        Three bugs fixed here:
          * os.makedirs(os.path.basename(...)) created a directory named after
            the FILE, in the cwd. It needs dirname.
          * filenames_ was a format *string*, so filenames_[i] indexed a single
            character of it and every r.save() got a one-character path.
          * self.cam.start() was never called, so capture_request() blocked
            forever on a camera that was not running.
        """
        frames = kwargs["frames"]
        delay_s = kwargs["delay_s"]

        directory = os.path.dirname(os.path.abspath(filename))
        os.makedirs(directory, exist_ok=True)

        stem, _, ext = os.path.basename(filename).rpartition(".")
        if not stem:                       ## no extension in the given name
            stem, ext = os.path.basename(filename), "jpg"
        template = os.path.join(directory, "{:03d}" + f"_{stem}.{ext}")

        if show_preview:
            self.cam.start_preview(self.preview_type, **self.preview_options)
        self.cam.start()

        start_time = time.time()
        try:
            for i in range(0, frames):
                r = self.cam.capture_request()
                r.save("main", template.format(i))
                r.release()
                print(f"Captured image {i+1} of {frames} at {time.time() - start_time:.2f}s")
                precise_sleep(delay_s)
        except KeyboardInterrupt:
            print("Timelapse interrupted.")
        finally:
            self.cam.stop()
            if show_preview:
                self.cam.stop_preview()
            gc.collect()


    def __video__(self, filename, show_preview=True, *args, **kwargs):
        """
        Record a video straight to file with picamera2's own encoder.
        RPi hardware supports processing up to 1080p30.

        encoder: an encoder instance, or one of the names in Camera.ENCODERS.
                 Defaults to H264Encoder.

        self.encodermap was legacy -- it was never defined anywhere, so both
        the `vid` and `vid_noprev` actions raised AttributeError on every call.
        This now uses start_recording(), which drives the encoder and the
        camera together and writes the file itself.
        """
        tsec = kwargs["tsec"]     ## To ensure failure if the time-duration is not specified.

        encoder = kwargs.get("encoder") or H264Encoder()
        if isinstance(encoder, str):
            encoder = Camera.ENCODERS[encoder.lower()]()

        if show_preview:
            self.cam.start_preview(self.preview_type, **self.preview_options)

        try:
            self.cam.start_recording(encoder, FileOutput(filename))
            Experiment.current.delay("acq_delay", tsec)
        except Exception as e:
            ## print_exception() takes no positional arguments; passing one
            ## raised a TypeError that masked the real error. Re-raise so
            ## read() records a cam_acq_failed event and returns False -- the
            ## finally block below still runs. Swallowing here would make a
            ## failed recording look like a successful one to the caller.
            print("TS::Camera::__video__ :: exception raised")
            Camera.console.print_exception()
            raise
        finally:
            try:
                self.cam.stop_recording()
            except Exception as e:
                log.error(f"TS::Camera::__video__ :: stop_recording failed: {e}")
            if show_preview:
                self.cam.stop_preview()
            gc.collect()


    def __video_noprev__(self, filename, *args, **kwargs):
        """
        Record a video without preview in a given format.
        Recommended for high fps recordings.
        """
        self.__video__(filename, show_preview=False, *args, **kwargs)

    def __lux_estimate__(self, filename=None, tsec=10, init_delay_s=3, *args, **kwargs):
        """
        Estimate scene illuminance (Lux, a.u.) from the camera's own metadata,
        sampled for `tsec` seconds and written to `filename` as CSV.

        Lux and FrameDuration are both read-only per-frame metadata, so the
        real sample rate is just the camera's frame rate -- there is nothing to
        set and nothing to sleep for. capture_metadata() already blocks until
        the next frame. FrameDuration is the microseconds since the previous
        frame, so fps = 1e6 / FrameDuration; that is measured here rather than
        assumed.

        Previously this read an undefined `self.fps` and called
        `self.cam.open()`, which Picamera2 does not have, so it raised on the
        first line of its body. It was also not registered in self.actions.
        """
        started_here = not self.cam.started
        if started_here:
            self.cam.start()
        precise_sleep(init_delay_s)

        results, durations = [], []
        try:
            deadline = time.monotonic() + tsec
            while time.monotonic() < deadline:
                md = self.cam.capture_metadata()
                results.append(md["Lux"])
                durations.append(md["FrameDuration"])
        finally:
            if started_here:
                self.cam.stop()

        if not results:
            log.error("TS::Camera::__lux_estimate__ :: no frames captured.")
            return results

        fps = 1e6 / float(np.mean(durations))
        print(f"Lux average: {np.mean(results):.3f}±{np.std(results):.3f} "
              f"[fps: {fps:.2f}, frames: {len(results)}, tsec: {tsec}]")

        if filename:
            with open(filename, "w") as f:
                f.write("frame,frame_duration_us,lux\n")
                for i, (d, lx) in enumerate(zip(durations, results)):
                    f.write(f"{i},{d},{lx}\n")

        return results

    ## AI Generated -- __overlay_preview__ deleted: it was unreachable
    ## (not in self.actions, no callers) and its loop called
    ## self.perf_counter(1.0/update_rate), which is not a method of this class.

    def __image_fomatted__(self, filename, tsec=3, show_preview=True, *args, **kwargs):
        self.open()
        self.cam.start_and_capture_file(filename, delay=tsec, capture_mode="video", show_preview=show_preview)
        self.close()


    def __vid_mjpeg_tpts__(self, filename, tsec=30, show_preview=False, quality=100,
                           encoder=None, **kwargs):
        """
        MJPEG encoded video using a software encoder.

        encoder: optional encoder instance. Pass a JpegEncoderGrayChannel to
        pick a different channel, or a JpegEncoderRedWithBGStats to also
        measure blue/green while recording red. Keep a reference to it: read()
        discards action return values, so the caller drains the stats itself.
        Defaults to the red-channel encoder, unchanged.
        """
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)
        #self.open()
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = encoder or JpegEncoderGrayRedCh(q=quality, num_threads=3)

        tpts_filename = filename.replace(".mjpeg", ".tpts")
        self.cam.start_recording(encoder, filename, pts=tpts_filename)
        time.sleep(tsec)
        self.cam.stop_recording()
        if show_preview:
            self.cam.stop_preview()
        #self.close()


    def __vid_mjpeg_tpts_multi__(self, filename_fn, no_splits=1, tsec=30, show_preview=False, **kwargs):
        """
        MJPEG encoded video using a software encoder.
        
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)

        Looks like the encoder can be reused.
        """
        #log.info("Reopening camera...")
        #self.open()
        #self.configure()
        time.sleep(1)

        log.info(f"Splits: {no_splits}")
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = JpegEncoderGrayRedCh(q=self.options["quality"], num_threads=4)
        output = SplittableOutput(output=FileOutput("prerec.mjpeg", pts="prerec.tpts"))
        log.info("Beginning recording...")
        self.cam.start_recording(encoder, output)
        log.info("Beginning splitting...")
        try:
            for file_no in range(no_splits):
                
                ## Genrate splitname
                filename = filename_fn(file_no)
                tpts_filename = filename.replace(".mjpeg", ".tpts")
                output.split_output(FileOutput(filename, pts=tpts_filename), wait_for_keyframe=False)
                log.info(f"Acquiring: {filename}")
                if not self.is_open():
                    self.close()
                    self.open()
                    self.configure()
                    log.error("[red]Opps Camera fried! Reopening camera")

                ## Wait for the recording time
                precise_sleep(tsec)
                gc.collect()      
        ## Stop
        except KeyboardInterrupt:
            print("Recording interrupted!")
        
        finally:    
            self.cam.stop_recording() 
            if show_preview:
                self.cam.stop_preview()
            self.close()
            gc.collect()

