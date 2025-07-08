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
from picamera2.outputs import *
from picamera2.encoders import *

## TS imports
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.permaconfig.sharing import Share

from detectors.cameras.abstractcamera import Camera as AbstractCamera

from expframework.experiment import Experiment

class Camera(AbstractCamera):
    """
    Camera object framework specialised for Raspberry Pi HQ Camera.
    Implementation used Picamera v2 python library.

    config parameter can be used to pass a configuration dict.
    """


    def __init__(self, quality=95, compression=0, fps=30, res=[1920, 1080]):
         
        #Picamera2.set_logging(Share.logginglevel)

        self.id_ = "detectors.cameras.rpi_hq_picam2"
        self.cam = None
        self.cam_fsaddr = None
        self.opentime_ns = None
        self.configset = {}
        self.open()
        

        # Capture Modes for this implementation
        self.fps = fps
        self.res = res
        self.actions = {
                          "preview"      : self.preview,
                          "img"          : self.__image__,
                          "timelapse"    : self.__timelapse__,
                          "vid"          : self.__video__,
                          "vid_noprev"   : self.__video_noprev__,
                        }


        ## Default quality and compression
        self.set_quality_compression(quality=quality, compression=compression)

        ## In the spirit of reproducability
        self.encodermap= {"rawencoder" : lambda: Encoder(), 
                          "jpegencoder": lambda: JpegEncoder(q=self.cam.options["quality"], num_threads=4), 
                          "mjpegencoder": lambda: MJPEGEncoder(bitrate=int(50*(10**6))),  ## Very high bitrate
                          "h264encoder": lambda: H264Encoder()} ## Let the algorithm choose the bitrate based on the quality factor.

        

        ## Extra things ------------------------------------------------------------------


        # Preview Window Settings
        self.preview_type = 1      #Preview.QT # Other options: Preview.DRM, Preview.QT, Preview.QTGL
        self.win_title_fields = ["ExposureTime", "FrameDuration"]


    def open(self):
        self.cam = Picamera2()

        ## TODO -> Create main streams as well
        #self.cam.preview_configuration = self.create_preview_configuration()
        self.cam.preview_configuration.enable_raw()  # causes the size to be reset to None
        #self.cam.still_configuration = self.create_still_configuration()
        self.cam.still_configuration.enable_raw()  # ditto
        #self.cam.video_configuration = self.create_video_configuration()
        self.cam.video_configuration.enable_raw()  # ditto

        self.configset = {"preview": self.cam.preview_configuration,
                          "still"  : self.cam.still_configuration,
                          "video"  : self.cam.video_configuration}
        #self.cam.title_fields = self.win_title_fields
        
        self.cam_fsaddr = None   ## TODO
        self.opentime_ns = time.perf_counter()
        log.info("TS::Camera::PiCamera2 Camera was created.")
        cam_manager_cleanup = lambda : self.cam.camera_manager.cleanup(self.cam.cam_num) 
        atexit.register(self.close)

        
    def is_open(self):
        return self.cam.is_open


    def close(self):
        if self.cam.is_open:
            self.cam.close()
            now = time.perf_counter()
            log.info(f"PiCamera2 Camera was closed: {now} : duration {now-self.opentime_ns:.2f} s.")


    def set_quality_compression(self, quality, compression):
        self.cam.options["quality"] = quality
        self.cam.options["compress_level"] = compression


    def configure(self, config_file):
        pass



    def preview(self, tsec=10):
        pass


    ### ----------------------------- ACTION IMPLEMENTATIONS ---------------------------------------------

    def __image__(self, filename, tsec=3, *args, **kwargs):
        """
        Capture an image. 
        tsec : delay without capture.
        """

        if "preveiw" in kwargs:
            preview = kwargs["preview"]
        else:
            preview = True
        
        self.cam.start_and_capture_file(filename, delay=tsec, capture_mode="still", show_preview=preview)
        self.cam.stop_preview()


    def __timelapse__(self, filename, *args, **kwargs):
        """
        Captures a timelapse sequence in jpeg format.
        filenames: is preceeded by the capture sequence number.
        frames: number of frames that must be captured.
        delay_s (optional) : Delay between images in seconds.
        """
        if not all(["frames", "delay_s"]) in kwargs:
            raise KeyError("Either arguments missing: frames and/or delay_s")

        ## Make sure that the filename folder exists.
        os.makedirs(os.path.basename(filename), exist_ok=True)
        filenames_ = "{:03d}" + f"_{filename.split('.')[0]}"*(filename.split(".")[0] != "") + \
                          f".{filename.split('.')[1]}"    

        self.cam.start_preview(self.preview_type)
        
        self.cam.start_and_capture_files( \
            name=filenames_, init_delay=0, \
            num_files = kwargs["frames"], delay = kwargs["delay_s"], \
            show_preview = True)
        self.cam.stop_preview()

    

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
            self.start_encoder(encoder=encoder, output=output)
            self.cam.start(show_preview=show_preview)
            
            Experiment.current.delay("acq_delay", tsec)
            
        except Exception as e:
            print("TS::Cmaera::__video__ :: exception rasied")
            Camera.console.print_exception(e)
        finally:
            self.cam.stop()
            encoder.stop_encoder()
            self.cam.stop_preview()
            gc.collect()


    def __video_noprev__(self, filename, *args, **kwargs):
        """
        Record a video without preview in a given format.
        Recommended for high fps recordings.
        """

        self.__video__(filename, show_preview=False, *args, **kwargs)

    def __lux__(self, filename, *args, **kwargs):
        
        tsec = kwargs["tsec"]     ## To ensure failure if the time-duration is not specified.
        fps = self.fps
        no_frames = int(fps*tsec)
        delay = 1.0/fps
        results = []

        for i in range(no_frames):
            md = self.cam.capture_metadata()
            results.append(md["Lux"])
            time.sleep(delay)
        print(f"Lux average: {np.mean(results)}±{np.std(results)} [fps: {fps}, tsec:{tsec}]")
        return results

