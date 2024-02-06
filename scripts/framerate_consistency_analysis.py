import datetime
from time import sleep


# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Experiment(f"{scopeid}_framerate_consistency_{dt}")
sleep(2)

#cam.config_cammode2()
lit.setVs(0,0.5,0)

## Capture for an hour
for hour in [1, 4, 8, 16]:
	name = f"{hour}_hour"
	cam.en_pre_timestamps(f"{name}_pre_callback_ts.txt")
	#print(f"FPS: {cam.cam.video_configuration.controls.FrameRate}")
	capture(vid_noprev, f"{name}.h264", tsec=10, it=hour*2, it_delay_s=5)


# Close experiment
exp.close()