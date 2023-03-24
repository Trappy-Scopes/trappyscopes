import picamera
import os

"""
There are 4 splitter ports in total that can be used (numbered 0, 1, 2, and 3). The video recording methods default to using splitter port 1, while the image capture methods default to splitter port 0 (when the use_video_port parameter is also True). A splitter port cannot be simultaneously used for video recording and image capture so you are advised to avoid splitter port 0 for video recordings unless you never intend to capture images whilst recording.
"""

# camera parameters
RES_X = 1536
RES_Y = 1152
FR = 30

ISO = 100               # camera sensitivy - controls the analog_gain and digital_gain
SHUTTER_SPEED = 0       # if camera.shutter_speed = 0, camera uses the auto value for exposure_speed
EXPOSURE_MODE = 'fixedfps'
AWB_MODE = 'off'        # white balance
FLASH_MODE = 'off'
IMAGE_EFFECTS = 'none'

VIDEO_TIME = 5 # in seconds
filename = 'highres_w{}_h{}_fps{}_exp_mode_not_set_fps_iso_100'.format(RES_X, RES_Y, FR) # to write the parameters

def write_params (camera, filename):
    '''
    writes recording camera parameters on txt file
    '''
    fn = filename
    if os.path.exists(fn + '_parameters.txt'):
        x = input("File already exists. Press enter to rewrite, press Ctrl+D to exit")
    f = open (fn + '_parameters.txt', 'w')
    f.write('Camera parameters for video' + filename + '\n\n')
    f.write('RESOLUTION                ---> ' + str(camera.resolution))
    f.write('\nFRAMERATE                ---> ' + str(camera.framerate))
    f.write('\nISO                      ---> ' + str(camera.iso))
    f.write('\nANALOG_GAIN              ---> ' + str(camera.analog_gain))
    f.write('\nDIGITAL_GAIN             ---> ' + str(camera.digital_gain)) 
    f.write('\nEXPOSURE_SPEED           ---> ' + str(camera.exposure_speed/1000) + ' ms')
    f.write('\nEXPOSURE_MODE            ---> ' + str(camera.exposure_mode))
    f.write('\nMAX_RESOLUTION           ---> ' + str(camera.MAX_RESOLUTION))
    f.write('\nMAX_FRAMERATE            ---> ' + str(camera.MAX_FRAMERATE))
    f.write('\nDRC_STRENGTHS            ---> ' + str(camera.DRC_STRENGTHS))
    
    f.close()
    

with picamera.PiCamera(resolution = (RES_X, RES_Y), framerate = FR) as camera:
    #parameters that should be defined during initialization to speed optimization:
        #resolution, framerate, framerate_range, sensor_mode, clock_mode
    
    camera.iso = ISO
    camera.shutter_speed = SHUTTER_SPEED
    #camera.exposure_mode = EXPOSURE_MODE
    
    camera.start_recording(filename + '.h264')
    #camera.start_recording('lowres.h264', splitter_port=2, resize=(320, 240))
    camera.wait_recording(VIDEO_TIME)
    write_params(camera, filename)
    #camera.stop_recording(splitter_port=2)
    camera.stop_recording()
