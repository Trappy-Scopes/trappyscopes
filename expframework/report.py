import pandas as pd
import pypandoc
import yaml

from rich.pretty import Pretty
from rich import print


class Report:

	def __init__(self):
		self.report_str = ""

		self.premble = ""
		self.summary = ""
		self.notes = ""

		self.appendix = ""
		self.events = ""

		#self.df = pd.DataFrame(exp.logs["events"])
		#self.df["elapsed"] = self.df["dt"] - self.df.loc[0]["dt"]


	def __summary__(self, exp):
		self.summary += "## Summary\n\n"
		

		summarydict = {"measurement streams": self.df[self.df.type == "measurement_stream"][["name",  "dt", "elapsed"]]
					   #"sessions": self.df[self.df.type == "session"][["name",  "dt", "elapsed"]],
					   #"notes"    : self.df[self.df.type == "user_note"][["note"]]
					   #"peripherals": Scope.current.tree
					   }

		for key, value in summarydict.items():
			self.summary += f"Number of {key}: {len(value)}.\n\n"

			string = ""
			valued = list(value)
			for i in range(len(value)):
				#ms = yaml.dump(value, Dumper=yaml.SafeDumper, sort_keys=False, default_flow_style=False)
				string += f"{i+1}. {value}"
			self.summary += string
		return self.summary

	def __events__(self, exp):
		df = pd.DataFrame(exp.logs["events"], columns=["type", "dt", "elapsed"])
		return df.to_markdown(index=False)

	def __premble__(self, exp):
		keys = ["name", "eid"]#, "exp_duration_s"
		dct = {key: exp.logs[key] for key in keys}
		return yaml.dump(dct, Dumper=yaml.SafeDumper, sort_keys=False,
						 default_flow_style=False).replace("\n", "\n\n")



	def generate(self, exp):
		self.df = pd.DataFrame(exp.logs["events"])
		self.df["elapsed"] = self.df["dt"] - self.df.loc[0]["dt"]
		self.df["elapsed"] = self.df["elapsed"].apply(lambda x: str(x))

		self.report_str += f"# Experiment Report\n\n"
		#self.report_str += f"## {exp.name} :: {exp.eid}\n\n"

		self.report_str += self.__premble__(exp)
		self.report_str += "\n\n\n"

		self.report_str += self.__summary__(exp)
		self.report_str += "\n\n\n"


		self.report_str += "## All events\n\n"
		self.report_str += self.__events__(exp)
		
		output = pypandoc.convert_text(self.report_str, 'pdf', \
									   format='md', outputfile=exp.newfile('expreport.pdf'))
