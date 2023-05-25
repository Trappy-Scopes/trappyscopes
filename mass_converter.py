import os
from pprint import pprint


"""
Bulk directory wide converter for h264 to mp4 conversion.
Warning: Assumes that the fps is 30.
"""

def convert_h264_to_mp4(dir_="."):
	all_files = os.listdir(dir_)
	h264files = list(filter(lambda fn: fn.endswith("h264"), all_files))
	mp4files = list(filter(lambda fn: fn.endswith("mp4"), all_files))


	h264files = [fn.split(".")[0] for fn in h264files]
	mp4files  = [fn.split(".")[0] for fn in mp4files]

	not_converted = [fn for fn in h264files if fn not in mp4files]
	print ("To be converted") 
	pprint(not_converted)
	x = input("Press enter to begin conversion, press Ctrl+D to exit")
	for fn in not_converted:
		os.system(f" MP4Box -add {fn + '.h264'}:fps=30 {fn + '.mp4'}")
	print(f"All conversions were completed: {len(not_converted)}")

if __name__ == "__main__":
	import sys
	if len(sys.argv) < 2:
		convert_h264_to_mp4()
	else:
		if os.path.isdir(sys.argv[1]):
			convert_h264_to_mp4(sys.argv[1])
		else:
			print("Invalid directory!")
