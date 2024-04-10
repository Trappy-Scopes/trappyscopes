import asyncio
import os
import subprocess
import colorama
from rich import print

class MP4Box:

	def check():
		"""
		Check and install MP4Box Libraries
		"""
		output = subprocess.check_output(["MP4Box", "-version"])
		output = output.decode()
		print(f"{colorama.Fore.YELLOW}output{colorama.Fore.RESET}")

		if all(["MP4Box", "version", "release"]) in output:
			print("MP4Box is installed!")
		else:
			print("MP4Box not found! Installing!")
			output = subprocess.check_output(["sudo", "apt-get", "install", "-y", "gpac"])
			output = output.decode()
			print(f"{colorama.Fore.YELLOW}output{colorama.Fore.RESET}")

		if not os.path.isdir("converted"):
			os.mkdir("converted")

	def convert_all(folder, prompt=True, fps=30):

			all_files = os.listdir(folder)
			h264files = list(filter(lambda fn: fn.endswith("h264"), all_files))
			mp4files = list(filter(lambda fn: fn.endswith("mp4"), all_files))

			# TODO - update to the new improved version - which is what???
			h264files = [fn.split(".")[0] for fn in h264files]
			mp4files  = [fn.split(".")[0] for fn in mp4files]


			not_converted = [fn for fn in h264files if fn not in mp4files]
			print("Conversions: ", len(not_converted))
			
			do_convert = True
			if prompt:
				do_convert = False
				print ("To be converted") 
				print(not_converted)
				x = input("Press enter to begin conversion, press Ctrl+D to exit")
				if x == "":
					do_convert = True
			for fn in not_converted:
				#os.system(f" MP4Box -add {os.path.join(dir_, fn) + '.h264'}:fps={fps} {os.path.join(dir_, fn) + '.mp4'}")
				MP4Box.convert(os.path.join(folder, fn + '.h264'), 
							   os.path.join(folder, "converted", fn + '.mp4'), 
							   fps=fps, delay=False)

	def convert_set(folder, prompt=True, fps=30):
		all_exps = os.listdir(folder)
		all_exps = [os.path.join(folder, dir_) for dir_ in all_exps if \
			os.path.isfile(os.path.join(folder, dir_, ".experiment"))]

		print("All experiments to be converted: ", all_exps)
		for exp in all_exps:
			MP4Box.convert_all(exp, prompt=prompt, fps=fps)

	def convert(infile, outfile, fps, delay=True):
		"""
		Convert to .MP4 (or other formats) in asynchronously.
		Always dumps the file in a folder named "converted".
		Includes a 5 second delay to make sure that the data is actually written
		to file before the conversion begins.
		"""
		async def convert_async():
			if delay:
				await asyncio.sleep(5)
			process = await asyncio.create_subprocess_exec(
				"MP4Box", "-add", f"{infile}:fps={fps}", \
				"-new", os.path.join("converted", outfile), \
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE
			)

			await process.wait()
			# Retrieve the output
			stdout, stderr = await process.communicate()
			print(f"{colorama.Fore.YELLOW}Conversion results: {infile} @{fps}fps{colorama.Fore.RESET}")
			print(f"{colorama.Fore.YELLOW}{stdout}{colorama.Fore.RESET}")
			print(f"{colorama.Fore.RED}{stderr}{colorama.Fore.RESET}")

		print(f"{colorama.Fore.YELLOW}Converting file to MP4: {infile} @{fps}fps{colorama.Fore.RESET}")
		# Run the async function
		asyncio.run(convert_async())



		
