import githubfiles as gitf
#from experiment import Experiment

from markdown_it import MarkdownIt
import logging as log

from rich import print
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.align import Align

class Protocol:
	"""
	Scientific Protocol System
	--------------------------
	+ parse
	+ track user time and includes annotation
	+ execute inline code.

	The protocol is split into two parts: `preamble` and `procedure`.
	The `procedure` is selected by looking for the `##Procedure tag`.

	The `execute` method sequentially runs all the items in the ordered list:

	1. Step 1 of scientific protocol: set the beacons to blink.
	   ```python
	   scope.beacon.blink() ## This code will be run automatically.
	   ```
	   ||> !done ## To mark the step as "done".
	2. Step 2 Pipette Reagent A in cell-culture C.
	   ```python
	   exp.delay("Pipette stuff", "10mins")
	   scope.buzzer.pulse(n=3)
	   ```
	   ||> !done ## To mark the step as "done".
	3. Step 3 Simple step with no executable code.
	   ...
	"""
	
	def __init__(self, protocol):
		"""
		Name of the protocol server.
		"""
		self.name = protocol
		self.text = gitf.get_file("protocols", protocol)

		split = self.text.split("## Procedure")

		self.premble = split[0]
		self.procedure = split[1]

		self.nodes = None   ## Parsed HTML blocks 

		## Print the Preamble
		print(Markdown(self.premble))

	def execute(self, exp, globals_):
		"""
		exp: Experiment class object.
		globals_: pass global variables to execute code.

		Start execution of the protocol.
		Execute runs a blocking call.
		"""
		exp.log("protocol_executed", attribs={"name": self.name})
		print(Panel(Align.center("Procedure"), style="bold yellow on blue"))
		self.__parse__()

		for i in range(len(self.nodes)):
			print(Markdown(f"# Procedure Step :: {i}"))
			m = Markdown("") ## Local markdown render
			tlist = self.nodes[i].to_tokens()
			m.parsed = [t for t in tlist if t.type not in ("list_item_open", "list_item_close")]
			print(Panel(m, style="bold white on blue"))			
			
			walk = self.nodes[i].walk()
			tags, contents = zip(*[(item.tag, item.content) for item in walk])

			## Execute all present code
			for idx, t in enumerate(tags):
				if t == "code":
					exec(contents[idx].strip(), globals_)
			
			tag = f"protocol_{self.name}_step_{i}"
			
			## Ask for user prompt
			exp.user_prompt("done", label=self.nodes[i])


		print(Panel(Align.center("Protocol Finsihed"), style="bold black  on green"))

	def __parse__(self):
		"""
		Markdown --> HTML --> Tokenize --> SyntaxTreeNode --> Parse one by one.
		"""
		from markdown_it import MarkdownIt
		from markdown_it.tree import SyntaxTreeNode

		md = MarkdownIt("commonmark").enable("strikethrough").enable("table")
		tokens = md.parse(self.procedure)
		node = SyntaxTreeNode(tokens)
		print(f"Parsed Protocol block has {len(node.children)} blocks.")
		self.nodes = node.children[0].children
		print(f"Processing Protocol steps:  {len(self.nodes)}.")


