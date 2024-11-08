import numpy as np
import pandas as pd
import os
import matplotlib.pyplot as plt

class FileLoader:

	def __init__(self, file):
		self.file = file
		self.df = None


	def process_csv(self):
		import numpy as np
		import pandas as pd
		import os
		import matplotlib.pyplot as plt

		self.df.append(pd.read_csv(file))
		count_columns = self.df.filter(like='count')

		## Calculate mean
		avg_count = count_columns.mean(skipna=True)

		## Calculate dilution
		df = self.df
		perml = [self. normalize_cells_per_ml(row[0], row[1], row[2]) \
             for row in zip(df['avg_count'], df['v_sample_ul'], df['v_etoh_ul'])]


