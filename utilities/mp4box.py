import asyncio
import os
import subprocess

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
			output = subprocess.check_output(["sudo", "apt", "install", "gpac"])
			output = output.decode()
			print(f"{colorama.Fore.YELLOW}output{colorama.Fore.RESET}")

		if not os.path.isdir("converted"):
			os.mkdir("converted")

	def convert(infile, outfile, fps):
		"""
		Convert to .MP4 (or other formats) in asynchronously.
		Always dumps the file in a folder named "converted".
		Includes a 5 second delay to make sure that the data is actually written
		to file before the conversion begins.
		"""
		async def convert_async():
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



		
