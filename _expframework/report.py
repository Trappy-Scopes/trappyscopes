import pandas as pd
import pypandoc
import yaml

from rich.pretty import Pretty



class Report:

	def __init__(self):
		self.report_str = ""
		self.df = pd.DataFrame(exp.logs["events"])
		self.dt["elapsed"] = df["dt"] - df.loc[0]["dt"]

		self.premble = ""


		self.summary = ""
		self.notes = ""

		self.appendix = ""
		self.events = ""


	def add_note(self):


	def __summary__(exp):
		self.summary += "## Summary\n\n"
		

		summarydict = {"measuement streams": exp.streams,
					   "sessions": self.df[self.df.type == "session"][["name", "user", "dt", "elapsed"]],
					   "notes"    : self.df[self.df.type == "user_note"][["note", " user"]]
					   #"peripherals": Scope.current.tree
					   }
		for key, value in summarydict:
			self.summary += f"Number of {key}: {len(value)}\n\n."

			string = ""
			for i in range(1, len(value)+1):
				ms = yaml.dump(dict(value), Dumper=yaml.SafeDumper, sort_keys=False, default_flow_style=False)
				string += f"{i}. {ms}"
			self.summary += string

	def __events__(self, exp):
		df = pd.DataFrame(exp.logs["events"], columns=["type", "dt", "elapsed"])
		df["dt"] = df["dt"] - df.loc[0]["dt"]
		return df.to_string()

	def __premble__(self, exp):
		keys = ["name", "eid", "exp_duration_s", "user"]
		dct = {key: exp.logs[key] for key in keys}
		return yaml.dump(dct, Dumper=yaml.SafeDumper, sort_keys=False,
						 default_flow_style=False).replace("\n", "\n\n")



	def generate(self, exp):
		
		self.report_str += f"# Experiment Report\n\n"
		#self.report_str += f"## {exp.name} :: {exp.eid}\n\n"

		self.report_str += self.__premble__(exp)
		self.report_str += "\n\n\n"

		self.__summary__(exp)
		self.report_str += "\n\n\n"


		self.report_str += "## All events\n\n"
		self.report_str += self.__events__(exp).replace("\n", "\n\n")
		
		output = pypandoc.convert_text(self.report_str, 'pdf', \
									   format='md', outputfile='expreport.pdf')
