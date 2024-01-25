import datetime
from time import sleep


# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Experiment(f"{scopeid}_framerate_consistency_{dt}")
sleep(2)


lit.setVs(1,1,1)

## Capture for an hour
for hour in [1, 4, 8, 16]:
	name = f"{hour}_hour"
	#cam.en_pre_timestamps(f"{name}_pre_callback_ts.txt")
	capture(vidmp4, f"{name}.mp4", tsec=60*60*hour, init_delay_s=5)


# Close experiment
exp.close()