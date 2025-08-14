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

## picamera2 imports
from picamera2 import Picamera2, Preview
from picamera2.outputs import FileOutput, Output
from picamera2.encoders import JpegEncoder
from libcamera import controls
import simplejpeg
from picamera2.request import MappedArray

## TS imports
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.permaconfig.sharing import Share
from core.precision.timing import precise_sleep
from detectors.cameras.abstractcamera import Camera as AbstractCamera

from expframework.experiment import Experiment


class JpegEncoderGrayRedCh(JpegEncoder):
    """
    For this encoder, we overload the encoder function to encode only the red-channel.
    Assumes that the format is "BGR888": pixel format: [B0, G0, R0, B1, G1, R1, ..., Bₙ, Gₙ, Rₙ]
    """
    def encode_func(self, request, name):
        """Performs encoding

        :param request: Request
        :type request: request
        :param name: Name
        :type name: str
        :return: Jpeg image
        :rtype: bytes
        """
        fmt = request.config[name]["format"]
        r_frame = None
        with MappedArray(request, name) as m:
            self.colour_space = self.FORMAT_TABLE[request.config[name]["format"]]
            width, height = request.config[name]['size']
            r_frame = m.array.reshape(height, width, 3)[..., 0:1].copy(order='C')
            return simplejpeg.encode_jpeg(r_frame,
                quality=self.q, colorspace="GRAY", colorsubsampling='Gray')

class SplittableOutput(Output):
    """
    Allows splitting of FileOutputs from a stream.
    Adopted from: https://github.com/raspberrypi/picamera2/discussions/569#discussioncomment-11717202
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.output = None
        self.new_output = None
        self.split_done = Event()

    def split_output(self, new_output):
        old_output = self.output
        # Start the new outoput in this thread, then schedule outputframe to make the switch.
        new_output.start()
        self.new_output = new_output
        # Wait for the switch-over to happen, and close the old output in this thread too.
        self.split_done.wait()
        self.split_done.clear()
        if old_output:
            old_output.stop()
        
    def outputframe(self, frame, keyframe=True, timestamp=None, packet=None, audio=False):
        if keyframe and self.new_output:
            self.split_done.set()
            # split_output will close the old output.
            self.output = self.new_output
            self.new_output = None
        if self.output:
            self.output.outputframe(frame, keyframe, timestamp)

    def stop(self):
        super().stop()
        if self.output:
            self.output.stop()



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
                          "img_formatted":self.__image_fomatted__
                        }

        ## Controls are different than config in this API
        self.options = {"quality":100, "compression":0}
        self.controls = {"ExposureTime": 18*1000, "AnalogueGain": 1.0, "AwbEnable": False, "AeEnable":False, 
                         "ColourGains":(0.0,0.0), "Contrast":2.0, 
                         "NoiseReductionMode":controls.draft.NoiseReductionModeEnum.Fast, 
                         'FrameDurationLimits':(int(1e6/25), int(1e6/25))
                        }
        self.cam = Picamera2()
        self.config = self.cam.create_video_configuration(buffer_count=10, 
            main={"size":(1520, 1520), "format":"BGR888"}, queue=False,
            controls=self.controls,
            encode="main", display="main")

        # Preview Window Settings
        self.preview_type = Preview.DRM      #Preview.QT # Other options: Preview.DRM, Preview.QT, Preview.QTGL
        self.preview_options = {"height":1080, "width":1080, "x":504, "y":0}
        self.win_title_fields = ["ExposureTime", "FrameDuration"]
        self.cam.close()
    def configure(self, *args, **kwargs):
        self.cam.options.update(self.options) ## Set compression
        self.cam.configure(self.config)
        log.info("Camera configured.")

    def open(self):
        self.opentime_ns = time.perf_counter()
        log.info("TS::Camera::PiCamera2 Camera was opened.")
        self.cam = Picamera2()
        
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
        log.info(f"PiCamera2 Camera was closed: {now} : duration {now-self.opentime_ns:.2f} s.")
        try:
            self.cam_manager_cleanup()
        except Exception as e:
            log.error(e)
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
        Captures a timelapse sequence in jpeg format.
        filenames: is preceeded by the capture sequence number.
        frames: number of frames that must be captured.
        delay_s (optional) : Delay between images in seconds.
        Preview seems to be stuck.
        """
        #if not all(["frames", "delay_s"]) in kwargs.keys():
        #    raise KeyError("Either arguments missing: frames and/or delay_s")

        ## Make sure that the filename folder exists -> this logic is wrong.
        os.makedirs(os.path.basename(filename), exist_ok=True)
        
        filenames_ = "{:03d}" + f"_{filename.split('.')[0]}"*(filename.split(".")[0] != "") + \
                          f".{filename.split('.')[1]}"    
        frames = kwargs["frames"]
        delay_s = kwargs["delay_s"]
        if show_preview:
            self.cam.start_preview()

        start_time = time.time()
        for i in range(0, frames):
            r = self.cam.capture_request()
            r.save("main", filenames_[i])
            r.release()
            print(f"Captured image {i} of {frames} at {time.time() - start_time:.2f}s")
            precise_sleep(delay_s)
        #self.cam.start_preview(self.preview_type)
        
        #self.cam.capture_files( \
        #    name=filenames_,  \
        #    num_files = kwargs["frames"], delay = kwargs["delay_s"], \
        #    show_preview = True)
        #self.cam.stop_preview()

    

    def __video__(self, filename, show_preview=True, *args, **kwargs):
        """
        Record an h264 video.
        RPi Hardware supports processing upto 1080p30.
        timestamping is allowed for this mode.
        """


        tsec = kwargs["tsec"]     ## To ensure failure if the time-duration is not specified.
        output = FileOutput(filename)
        
        ## Choose encoder --------------------------------------
        if "encoder" in kwargs:
            encoder = self.encodermap[kwargs["encoder"].lower()]()
        else:
            encoder = self.encodermap["h264encoder"]()
        ## Choose encoder --------------------------------------

        try:
            self.cam.start_encoder(encoder=encoder, output=output)
            self.cam.start(show_preview=show_preview)
            Experiment.current.delay("acq_delay", tsec)
            
        except Exception as e:
            print("TS::Camera::__video__ :: exception rasied")
            Camera.console.print_exception(e)
        finally:
            self.cam.stop()
            self.cam.stop_encoder()
            if show_preview:
                self.cam.stop_preview()
            gc.collect()


    def __video_noprev__(self, filename, *args, **kwargs):
        """
        Record a video without preview in a given format.
        Recommended for high fps recordings.
        """
        self.__video__(filename, show_preview=False, *args, **kwargs)

    def __lux__(self, filename, init_delay_s=3, *args, **kwargs):
        """
        Measure the lux (a.u) from the camera sensor. Averages at the defined fps.
        """ 
        tsec = kwargs["tsec"]     ## To ensure failure if the time-duration is not specified.
        fps = self.fps
        no_frames = int(fps*tsec)
        delay = 1.0/fps
        results = []

        self.cam.close()
        self.cam.open()
        time.sleep(init_delay_s)

        for i in range(no_frames):
            md = self.cam.capture_metadata()
            results.append(md["Lux"])
            time.sleep(delay)
        print(f"Lux average: {np.mean(results)}±{np.std(results)} [fps: {fps}, tsec:{tsec}]")
        return results

    def __overlay_preview__(self, tsec, overlay_fn, update_rate):
        """
        Preview where the buffer is pushed to an `overlay_fn`, which updates at a 
        rate of `update_rate` until the `tsec` seconds expire.  
        """

        start_time = time.perf_counter()
        self.cam.start_preview(self.preview_type)
        
        while time.perf_counter() - start_time <= tsec:
            int_start_time = time.perf_counter()
            array = self.cam.capture_array()
            self.cam.set_overlay(overlay_fn(array))

            sleep_time = max(0, self.perf_counter(1.0/update_rate)-int_start_time)
            time.sleep(sleep_time)
        self.cam.stop_preview()

    def __image_fomatted__(self, filename, tsec=3, show_preview=True, *args, **kwargs):
        self.open()
        self.cam.start_and_capture_file(filename, delay=tsec, capture_mode="video", show_preview=show_preview)
        self.close()


    def __vid_mjpeg_tpts__(self, filename, tsec=30, show_preview=False, quality=100, **kwargs):
        """
        MJPEG encoded video using a software encoder.
        """
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)
        self.open()
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = JpegEncoderGrayRedCh(q=quality, num_threads=3)

        tpts_filename = filename.replace(".mjpeg", ".tpts")
        self.cam.start_recording(encoder, filename, pts=tpts_filename)
        time.sleep(tsec)
        self.cam.stop_recording()
        if show_preview:
            self.cam.stop_preview()
        self.close()


    def __vid_mjpeg_tpts_multi__(self, filename_fn, no_iterations=1, tsec=30, show_preview=False, **kwargs):
        """
        MJPEG encoded video using a software encoder.
        
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)

        Looks like the encoder can be reused.
        """
        print("[red]Exp Syncing is not implemented!")
        self.open()
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = JpegEncoderGrayRedCh(q=self.options["quality"])
        output = SplittableOutput()
        
        self.cam.start_recording(encoder, output)
        
        try:
            for file_no in range(no_iterations):
                
                ## Geenrate splitname
                filename = filename_fn(file_no)
                tpts_filename = filename.replace(".mjpeg", ".tpts")
                output.split_output(FileOutput(filename, pts=tpts_filename))

                if not self.is_open():
                    self.close()
                    self.open()
                    self.configure()
                    print("[red]Opps Camera fried! Reopening camera")

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

