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
from libcamera import controls
import simplejpeg
from picamera2.request import MappedArray

## TS imports
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.permaconfig.sharing import Share

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
        with MappedArray(request, name) as m:
            if fmt == "YUV420":
                width, height = request.config[name]['size']
                Y = m.array[:height, :width]
                reshaped = m.array.reshape((m.array.shape[0] * 2, m.array.strides[0] // 2))
                U = reshaped[2 * height: 2 * height + height // 2, :width // 2]
                V = reshaped[2 * height + height // 2:, :width // 2]
                return simplejpeg.encode_jpeg_yuv_planes(Y, U, V, self.q)
            if self.colour_space is None:
                self.colour_space = self.FORMAT_TABLE[request.config[name]["format"]]
                width, height = request.config[name]['size']
                #bgr_frame = 
                #r_frame = bgr_frame
                #r_frame = r_frame
                print(height, width)
                return simplejpeg.encode_jpeg(m.array.reshape(height, width, 3)[:, :, 2].reshape((height, width), order='C'),
                                          quality=self.q, colorspace="GRAY", colorsubsampling='Gray')




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


    def __init__(self, quality=100, compression=0, fps=20, res=[1520, 1520]):
         
        #Picamera2.set_logging(Share.logginglevel)
        self.cam = None
        self.cam_fsaddr = None


        self.opentime_ns = None
        ## Set of different configurations
        self.configset = {}

        self.config  = {"res":res, "quality":quality, "fps":fps, "compression":compression, "exposure_ms":18}
        self.controls = {"ExposureTime": self.config["exposure_ms"]*1000, "AnalogueGain": 1.0, "AwbEnable": False, "AeEnable":False, 
                         "ColourGains":(4.0,0.0), "Contrast":2.0, 
                         "NoiseReductionMode":controls.draft.NoiseReductionModeEnum.Fast, 
                         'FrameDurationLimits':(int(1e6/self.config["fps"]), int(1e6/self.config["fps"]))
                        }

        self.cam = None
        #self.video_config = self.cam.create_video_configuration(buffer_count=6, 
        #    main={"size":(self.config["res"][0], self.config["res"][1])}, 
        #    lores={"size":(self.config["res"][0], self.config["res"][1])},
        #    controls=self.controls, encode="main", display="lores")
        

        # Capture Modes for this implementation
        self.actions = {
                          "preview"       : self.preview,
                          "img"           : self.__image__,
                          "timelapse"     : self.__timelapse__,
                          "vid"           : self.__video__,
                          "vid_noprev"    : self.__video_noprev__,
                          "vid_mjpeg_tpts": self.__vid_mjpeg_tpts__,
                          "vid_mjpeg_tpts_multi":self.__vid_mjpeg_tpts_multi__
                        }




        ## In the spirit of reproducability
        self.encodermap= {"rawencoder" : lambda: Encoder(), 
                          "jpegencoder": lambda: JpegEncoder(q=self.cam.options["quality"], num_threads=4), 
                          "mjpegencoder": lambda: MJPEGEncoder(bitrate=int(50*(10**6))),  ## Very high bitrate
                          "h264encoder": lambda: H264Encoder()} ## Let the algorithm choose the bitrate based on the quality factor.

        

        ## Extra things ------------------------------------------------------------------


        # Preview Window Settings
        self.preview_type = Preview.QT      #Preview.QT # Other options: Preview.DRM, Preview.QT, Preview.QTGL
        self.win_title_fields = ["ExposureTime", "FrameDuration"]


    def open(self):
        self.opentime_ns = time.perf_counter()
        log.info("TS::Camera::PiCamera2 Camera was opened.")
        self.cam = Picamera2()
        self.video_config = self.cam.create_video_configuration(buffer_count=6, 
            main={"size":(self.config["res"][0], self.config["res"][1]), "format":"BGR888"},
            controls=self.controls, 
            encode="main", display="main")
        self.cam.configure(self.video_config)
        #self.cam.video_config.enable_raw()
        #self.cam.video_config.enable_lores()
        self.cam.options["quality"] = self.config["quality"]
        self.cam.options["compress_level"] = self.config["compression"]
        self.cam.title_fields = self.win_title_fields
        
        #self.cam_fsaddr = None   ## TODO
        cam_manager_cleanup = lambda : self.cam.camera_manager.cleanup(self.cam.cam_num) 
        atexit.register(self.close)
        #self.cam.open()

        
    def is_open(self):
        return self.cam.is_open


    def close(self):
        if self.cam.is_open:
            self.cam.close()
            now = time.perf_counter()
            log.info(f"PiCamera2 Camera was closed: {now} : duration {now-self.opentime_ns:.2f} s.")


    def preview(self, tsec=10):
        self.cam.start_preview(self.preview_type)
        time.sleep(tsec)
        self.cam.stop_preview()
        gc.collect()

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
        #if not all(["frames", "delay_s"]) in kwargs.keys():
        #    raise KeyError("Either arguments missing: frames and/or delay_s")

        ## Make sure that the filename folder exists -> this logic is wrong.
        os.makedirs(os.path.basename(filename), exist_ok=True)
        
        filenames_ = "{:03d}" + f"_{filename.split('.')[0]}"*(filename.split(".")[0] != "") + \
                          f".{filename.split('.')[1]}"    

        #self.cam.start_preview(self.preview_type)
        
        self.cam.start_and_capture_files( \
            name=filenames_,  \
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


    def __vid_mjpeg_tpts__(self, filename, tsec=30, show_preview=False, quality=100, **kwargs):
        """
        MJPEG encoded video using a software encoder.
        """
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)
        self.open()
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = JpegEncoderGrayRedCh(q=quality)

        tpts_filename = filename.replace(".mjpeg", ".tpts")
        self.cam.start_recording(encoder, filename, pts=tpts_filename)
        time.sleep(tsec)
        self.cam.stop_recording()
        if show_preview:
            self.cam.stop_preview()
        self.close()


    def __vid_mjpeg_tpts_multi__(self, filename_prefix, filename_suffix_fn, no_iterations=1, tsec=30, show_preview=False, quality=100, **kwargs):
        """
        MJPEG encoded video using a software encoder.
        
        #video_config = self.cam.create_video_configuration(main={"size": self.config.res})
        #self.cam.configure(self.video_config)
        """
        self.open()
        if show_preview:
            self.cam.start_preview(self.preview_type)
        encoder = JpegEncoderGrayRedCh(q=quality)

        for file_no in range(no_iterations):
            filename = filename_prefix + filename_suffix_fn(file_no)
            tpts_filename = filename.replace(".mjpeg", ".tpts")
            self.cam.start_recording(encoder, filename, pts=tpts_filename)
            time.sleep(tsec)
            self.cam.stop_recording()
            if show_preview:
                self.cam.stop_preview()
        ## Finally close camera
        self.close()

