import csv
import os
import datetime
from rich import print
from rich.pretty import Pretty
from rich.panel import Panel
from rich.rule import Rule
from rich.console import Console
from rich.table import Table
import logging as log
import pandas as pd


class Reg:
	registry = None
	def load():
		# Create a table
		csv_file = os.path.join(os.path.expanduser("~"), ".trappyscope_registry")

		# Load the CSV into a DataFrame
		Reg.registry = pd.read_csv(csv_file)		



	def search():
		from prompt_toolkit import prompt
		from prompt_toolkit.completion import WordCompleter
		from prompt_toolkit.shortcuts import CompleteStyle
		from prompt_toolkit.validation import Validator
		from colorama import Fore
		escape_validation = False
		def is_valid_uid(text):
			if text == "":
				## return true
				escape_validation = True
				return True
			return text in Reg.registry.name.to_numpy() 

		validator = Validator.from_callable(
			is_valid_uid,
			error_message='Object id is not present in the registry!',
			move_cursor_to_end=False)

		all_objects = WordCompleter(Reg.registry.name)
		print("[red](press enter to abort search)[default]")
		obj_name = prompt('Enter registry id -> ', completer=all_objects, \
						  complete_style=CompleteStyle.MULTI_COLUMN, validator=validator)
		if obj_name != None and obj_name != "":
			print(Rule("Search successfull!", style="green"))
			partial_df = Reg.registry[Reg.registry['name'] == obj_name]
			result = partial_df.iloc[0]
			print(Panel(Pretty(result.to_dict()), title=obj_name))
			return str(obj_name)
		else:
			print(Rule("Search un-successfull!", style="red"))
			return None
		


def Registry(name, kind, tag=None):

	# Registry path
	csv_file = os.path.join(os.path.expanduser("~"), ".trappyscope_registry")

	if not os.path.exists(csv_file):
		log.info(f"Creating registry file: {csv_file}")
		with open(csv_file, mode="w", newline="") as file:
			writer = csv.DictWriter(file, fieldnames=["name", "kind", "dt", "tag"])
			writer.writeheader()  # Write column headers

	
	# Load CSV data into a list of dictionaries
	data_list = []
	with open(csv_file, mode="r") as file:
		reader = csv.DictReader(file)  # Assumes the first row contains column headers
		for row in reader:
			data_list.append(row)

	# Add a new line to the "database"
	new_row = {"name": name, "kind": kind, "dt": datetime.datetime.now(), "tag":tag}
	data_list.append(new_row)

	# Write updated data back to the CSV file
	with open(csv_file, mode="w", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=new_row.keys())
		writer.writeheader()  # Write column headers
		writer.writerows(data_list)  # Write rows

	print(Panel(Pretty(new_row), title="TrappyScope Registry"))

def ShowRegistry():
	console = Console()

	# Create a table
	csv_file = os.path.join(os.path.expanduser("~"), ".trappyscope_registry")
	table = Table(title="TrappyScope Registry")

	# Read the CSV file
	with open(csv_file, mode="r") as file:
		reader = csv.reader(file)
		headers = next(reader)  # Extract headers

		# Add columns to the table
		for header in headers:
			table.add_column(header)

		# Add rows to the table
		for row in reader:
			table.add_row(*row)
	# Print the table
	console.print(table)
