



class Transfer:
	"""
	Object responsible for making file transfers


	Attention
	---------
	+ Filenames and foldernames will be treated the same and are interchangable.
	  Should consider changing it to "dirfile" or something.

	if transfer.prompt(filenames):
		transfer.to_next_cloud(filenames)

	"""




	def __init__():


		pass


	def to_next_cloud(self, url=None, login_id=None, password=None):

		"""
		Protocol
		--------

		1. For the current date, create a folder.
		2. Within the date folder, make a microscope specific folder.
		3. Upload the mp4 file there and return status.
		*4. Update the log file in the next cloud server.
		"""

	def prompt(self, filenames=[]):


		print("The following filenames will be transfered:")
		pprint(filenames)
		input_ = input("Type `yes` to proceed, anything else to reject: ")
		
		return input_.lower().strip() == "yes"