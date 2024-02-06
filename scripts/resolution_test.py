import datetime
from time import sleep



# Start experiment
unique_check = False
dt = str(datetime.date.today()).replace("-", "_")
exp = Experiment(f"{scopeid}_resolution_tests_{dt}")
sleep(2)

## Explore colour space
colors = {}
colors["r"] = 0.0
colors["g"] = 0.0
colors["b"] = 0.0
levels = 20
for ch in ["r", "g", "b"]:
	colors["r"] = 0.0
	colors["g"] = 0.0
	colors["b"] = 0.0
	
	### Explore colour space
	for i in range(levels):
		print(f"Setting light : r:{colors["r"]}, g:{colors["g"]}, b:{colors["b"]}")
		colors[ch] = colors[ch] + (3.3/levels)*i
		l1.setVs.({colors["r"]}, {colors["g"]}, {colors["b"]})
		
		### Binnging enabled
		capture(img, f"{ch}-{colors[ch]}.mp4", tsec=5, init_delay_s=1)

		### Full resolution
		cam.config_fullres()
		capture(img, f"{ch}-{colors[ch]}.mp4", tsec=5, init_delay_s=5)


## Close experiment
exp.close(sc)