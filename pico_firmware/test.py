import requests
import secrets
import pprint

message = "test"
title = "pico-firmware State"
req = "https://api.pushover.net/1/messages.json?token={}&user={}&title={}&message={}".format(\
secrets.not_token, secrets.not_user_key, title, message)
response = requests.post(req)
print(dir(response))