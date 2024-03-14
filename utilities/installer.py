
### Minimal imports. Remeber nothing exists yet. Only libraries in the standard
### Distribution
import os
import sys

class Installer:
	pylibs = ["pyyaml", "colorama", "nanoid", "plotext", "asciichartpy"]
	binlibs = []
	gitclones = []
	

	def do_all():

		platform = sys.platform.startswith('linux')*"linux" +
		           sys.platform.startswith('darwin')*"darwin"
		if not plateform:
			print("We don't do Windows! Sorry!")
			exit()

		print(f"Plateform is: {platform}").
		if platform == "darwin":
			print("Please ensure that `brew` package manager is installed.")


		print(f"You are ready to trap cells, you just need the following: \
			  \npython libraries: {Installer.pylibs} \
			  \n other libraries: {Installer.binlibs}")
		x = input("Let's go, we will need sudo previledges [press Enter]:")


		## python
		Installer.install_py_libs(Installer.pylibs)
		#Installer.install_bin_libs(Installer.binlibs)
		#Installer.gitclone(Installer.gitclones)
		Installer.check_submodules()

		
		## Also check if the submodules are properly installed here

		### -----

		print("\n\nIf everyhting went well, we are ready to go!\n\n")

		

	def install_py_libs(required_libs):
		for i, lib in enumerate(required_libs):
			try: 
				__import__(lib)
				print(f"{i}. {lib} : already exists!")
			except ImportError:
				#pip.main(['install', lib, "--break-system-packages"])
				os.system(f"sudo pip install {lib} --break-system-packages")
				print(f"{i}. {lib} : was installed!")

	def install_bin_libs(required_libs):
		pass

	def gitclone(loc="./utilities"):
		pass

	def check_submodules():
		pass