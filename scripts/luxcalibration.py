import datetime
import datetime
from experiment import Calibration
import numpy as np
import time

# Start experiment
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Calibration(f"{scopeid}_luxcalib_{dt}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}")
print(lit)
colors = {}
colors["r"] = 0.0
colors["g"] = 0.0
colors["b"] = 0.0
levels = 20
for ch in ["r", "g", "b"]:
	colors["r"] = 0.0
	colors["g"] = 0.0
	colors["b"] = 0.0
	for i in range(levels):
		colors[ch] = (3.3/levels)*i
		pico(f'l1.setVs({colors["r"]}, {colors["g"]}, {colors["b"]})')
		name = f"{ch}_{colors[ch]:.3f}"
		name = name.replace(".", "pt") + ".mp4"
		capture(vidmp4, name, tsec=10, init_delay_s=0)
# Close experiment
exp.close()
