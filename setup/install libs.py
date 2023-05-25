
maintainance  = ["GitPython"]
hardware_libs = ["pyserial", "picamera"]
tracking_libs = ["trackpy", "matplotlib", "numpy", "pandas", "scikit-video"]



import pip 
# PIP (Pip Installs Packages) is a module that installs packages/modules/libraries


def install_libs(required_libs):
	"""
	Takes a list of libraries and installs those that are not present on the
	current python environment.
	"""
	required_libs = list(required_libs)
    print(f"Simple Library Installer using pip: {required_libs}")
    for lib in required_libs:
        try:                                # Try importing the library.
            __import__(lib)
            print(lib, "exists!")
        except ImportError:                 # If import fails, then install.
            pip.main(['install', lib])
            print(lib, ": attempted install.")


def git_clone(required_repos, name=None):
	"""
	Installs the list of github repositories using pip.

	How to you check for installation??
	"""
	required_repos = list(required_repos)
	for repo in required_repos:
		pip.main(["install" f"git+{repo}"])


def apt_get_automatron(list_of_libs):
	command = f"sudo apt-get --assume-yes install {}"


if __name__ == "__main__":
	install_libs(maintainance)
	install_libs(hardware_libs)
