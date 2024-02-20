import datetime
import datetime
from experiment import Test
import numpy as np
import time

# Start experiment
dt = str(datetime.date.today()).replace("-", "_")
exp = Test(f"{scopeid}_test_cameraclosure_{dt}")
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
		colors[ch] = colors[ch] + ((3.3/levels)*i)
		pico(f'l1.setVs({colors["r"]}, {colors["g"]}, {colors["b"]})')
		capture(vidmp4, f"{ch}-{colors[ch]}.mp4", tsec=10, init_delay_s=5)
# Close experiment
exp.close()
