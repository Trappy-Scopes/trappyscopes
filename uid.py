import nanoid

def uid():
	return nanoid.generate('1234567890abcdef', 10)

def uid_hex():
	return nanoid.generate('1234567890abcdef', 10)