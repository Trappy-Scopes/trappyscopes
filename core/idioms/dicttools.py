

def absent_key_false(key, dict_):
	if not key in dict_:
		return False
	else:
		return dict_[key]