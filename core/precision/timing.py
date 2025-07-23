import time


def precise_sleep(tsec):
	time.sleep(tsec)

class DriftCorrected:
	def monitored_sleep(self, name, seconds, steps=100):
			"""
			Add a experiment step dealy with a progress bar and automatic logging.
			Todo: Correct processor drift.
			"""
			interrupted = False
			start = time.time_ns()
			print(start)
			try:
				for i in track(range(steps), description=f"exp-step: blocking delay: [red]{name}[default] | [cyan]{seconds}s[default] >> "):
				    time.sleep(seconds/steps)  # Simulate work being done
			except KeyboardInterrupt:
				interrupted = True
				print(f"[red]Dealy interrupted @ {((time.time_ns()-start)*10**-9):3f}/{seconds}")
			self.log("delay", attribs={"name":name, "duration":seconds, "start_ns":start,
					 "end_ns": time.time_ns(), "interrupted": interrupted})
			print(time.time_ns())

