import githubfiles as gitf
from experiment import Experiment

from markdown_it import MarkdownIt
from bs4 import BeautifulSoup
import logging as log

from rich import print
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.console import Console


class Protocol:

	console = Console()
	def __init__(self, protocol):
		self.name = protocol
		self.text = gitf.get_file("protocols", protocol)

		split = self.text.split("## Procedure")

		self.premble = split[0]
		self.procedure = split[1]



		md = MarkdownIt()
		html = md.render(self.procedure)
		self.soup = BeautifulSoup(html, 'html.parser')

		print(Markdown(self.premble))

	def execute(self):
		Experiment.current.log("protocol_executed", attribs={"name": self.name})
		print(Markdown("## Procedure"))

		#lists = self.soup.find_all(['ul', 'ol'])
		lists = self.soup.find_all('li')
		lists = [li.get_text(strip=True) for li in lists]
		

		for i in range(len(lists)):
			Protocol.console.clear()
			print(Markdown(f"# Procedure Step :: {i}"))
			print(Panel(lists[i]))
			tag = f"procedure_{self.name}_step_{i}"
			Experiment.current.user_prompt("done", label=lists[i])
			print("\n"*10)

		print(Rule(title="Protocol Finsihed", style="yellow", characters="="))


