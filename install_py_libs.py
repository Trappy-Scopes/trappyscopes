import pip

def install_py_libs(required_libs):
	for lib in required_libs:
		try: 
			__import__(lib)
			print(lib, "exists!")
		except ImportError:
			pip.main(['install', lib])
			print(lib, "was installed!")


if __name__ == "__main__":
	reqd_libs = ["pyyaml", "colorama", "nanoid"]

	install_py_libs(reqd_libs)
