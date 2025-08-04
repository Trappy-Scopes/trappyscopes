"""
Test script header which should mention important information like author, references, and licencing
information.

author: Yatharth Bhasin
date: 30-July-2025
licence: MIT Licence

Copyright (c) <year> <copyright holders>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


## Do common imports
import time
import random
from expframework.experiment import Experiment

## Describe the script. This is important and will be logged in the Experiment system.
__description__ = \
"""
Simple script that demonstrates blocking experiment and how interruption
is done and logged.
"""

def start_inf():
	"""
	Start a never-ending random experiemnt.
	"""
	while True: # Scary! Will never end.
		print(f"Complex calculation yields: {random.random()*100} scary number.")
		print("[bold]Interrupt this blocking experiment by pressing Ctrl+C.")
		time.sleep(1)
if __name__ == "__main__":
	global exp
	exp = Experiment.Construct(["test", "interruptable", "experiment"])

	start_inf()
	print("This will not get printed as the script exist abruptly!")
