import sys
sys.path.append("./lights/")

def LightSelector(device):

	device = device.strip().lower()
	

	if device.__contains__("ca_pwm_rgb_led"):
		import ca_pwm_rgb_led.CAPwmRgbLed
		return ca_pwm_rgb_led.CAPwmRgbLed()

	if device.__contains__("cc_pwm_rgb_led"):
		import cc_pwm_rgb_led.CCPwmRgbLed
		return cc_pwm_rgb_led.CCPwmRgbLed()


