import datetime
from experiment import Test
import numpy as np
import time
import gc



dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())
exp = Experiment(f"{scopeid}_simple_captures_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)

for i in np.arange(0, 3.0, 0.5):
	scope.lit.setVs(i, 0, 0)
	exp.delay("Stabilization delay", 3)
	exp.log("Cam capture")
	cam.capture("img", f"illm_{i}V_red.png")
