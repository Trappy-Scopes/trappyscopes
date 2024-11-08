import numpy as np

class CellCounter:

	def density_per_mL(*args, df=2):
		"""
		Average of all counts (excluding nans) multiplied by dilution factor and 10,000.
		"""
		return np.nanmean(list(args))*df*1.0e4


	def process_pallmoloids(*args):
		"""
		Non-regex parser.
		*args: counts with format: I+Lpm2+Npm4+Mpm8+Qpm16.
		
		Legend:
		I     : individual cells (planktonic)
		Lpm2  : L pallmoloids of size 2  (binary)
		Npm4  : N pallmoloids of size 4  (quadruple)
		Mpm8  : M pallmoloids of size 8  (octonary)
		Qpm16 : Q pallmoloids of size 16 (hexadecanary)

		returns: dict: {1:I; 2:L, 4:N, 8:M, 16:Q}
		"""

		from ast import literal_eval
		from copy import deepcopy


		def __numeric_conversion__(string):

			try:
				string = int(string)
			except ValueError:
				try:
					# If it's not an integer, try to convert to a float
					string = float(string)
				except ValueError:
					pass
			return string


		result_template  = {1:0, 2:0, 4:0, 8:0, 16:0}
		processed_counts = []

		args = [str(count).replace(" ", "").lower() for count in args]   ## Remove spaces and force lowercase
		args = [count.split("+") for count in args]    ## Split around "+"
		args = [[__numeric_conversion__(each) for each in count] for count in args] ## Deduce type


		## Parse individual count (each count is a list now of pallmoloids...)
		for count in args:
			processed_counts.append(deepcopy(result_template))
			
			## 1. Find integer/floats------------------------------
			numericals = []
			# Iterate in reverse to safely pop elements
			for i in range(len(count)-1, -1, -1):
				if isinstance(count[i], (int, float)):
					numericals.append(count.pop(i))

			## Raise havoc if multiple individuals are found.
			if len(numericals) > 1:
				print(f"Error:: multiple entries found for each group. 1:{numericals}. Aborting!")
				return None
			elif len(numericals) == 0:
				pass 
			else:
				processed_counts[-1][1] = numericals[0]

			### N.--------------------------------------------------

			split_groups = [each.split("pm") for each in count]

			split_groups = [[pair_val for pair_val in each if pair_val.strip()] for each in split_groups] ## Remove empty strings
			split_groups = [[1, each[0]] if len(each)==1 else each for each in split_groups] ## pm4 == 1pm4

			split_groups = [[__numeric_conversion__(pair_val) for pair_val in each] for each in split_groups] ## deduce type
			
			allowed_iterations = [2,4,8,16]
			for each in split_groups:
				processed_counts[-1][int(each[1])] = float(each[0])
				allowed_iterations.remove(int(each[1]))
			## Extra pops should raise exceptions

		return processed_counts

	def expanded_counts(dictionary):
		"""
		dictionary: of type {1:I; 2:L, 4:N, 8:M, 16:Q}
		returns: (1*I)+(2*L)+...
		"""
		return sum([key*val for key, val in dictionary.items()])

	def discard_pallmoloids(string):
		"""
		From a given string of counts, it discards the pallmoloids and only
		returns the single cells.
		"""
		return CellCounter.process_pallmoloids(string)[0][1]







