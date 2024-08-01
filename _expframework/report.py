import pandas as pd
import pypandoc
import yaml



class Report:

	def __init__(self):
		self.report_str = ""

	def events(self, exp):
		df = pd.DataFrame(exp.logs["events"], columns=["type", "dt"])
		df["dt"] = df["dt"] - df.loc[0]["dt"]
		return df.to_string()

	def premble(self, exp):
		keys = ["name", "eid", "exp_duration_s", "user"]
		dct = {key: exp.logs[key] for key in keys}
		return yaml.dump(dct, Dumper=yaml.SafeDumper, sort_keys=False,
						 default_flow_style=False).replace("\n", "\n\n")



	def generate(self, exp):
		
		self.report_str += f"# Experiment Report\n\n"
		#self.report_str += f"## {exp.name} :: {exp.eid}\n\n"

		self.report_str += self.premble(exp)
		self.report_str += "\n\n\n"

		self.report_str += "## Events\n\n"
		self.report_str += self.events(exp).replace("\n", "\n\n")
		
		output = pypandoc.convert_text(self.report_str, 'pdf', \
									   format='md', outputfile='expreport.pdf')
