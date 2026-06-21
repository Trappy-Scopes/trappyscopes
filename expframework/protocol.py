# Modified by Claude. Refactoring and addition of features.

import re

import githubfiles as gitf
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from rich import print
from rich.align import Align
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .experiment import Experiment

_MD = MarkdownIt("commonmark").enable("strikethrough").enable("table")


def _split_frontmatter(text):
    """Separate a leading ``--- ... ---`` frontmatter block from the body.

    Returns ``(meta, body)`` where ``meta`` is a dict of ``key: value`` pairs.
    If no frontmatter is present, ``meta`` is empty and ``body`` is the input.
    """
    match = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    block, body = match.groups()
    meta = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, body


def _headings(text):
    """Yield ``(level, title, start_line)`` for every ATX heading.

    Parsing through markdown-it means ``#`` characters inside fenced code
    blocks are correctly ignored.
    """
    tokens = _MD.parse(text)
    out = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            out.append((int(tok.tag[1]), tokens[i + 1].content, tok.map[0]))
    return out


def _split_sections(body):
    """Split a markdown body by its ``#``/``##`` headings.

    Returns ``(title, sections)`` where ``title`` is the ``#`` heading and
    ``sections`` maps each ``##`` heading to its raw markdown. Content between
    the title and the first ``##`` is stored under ``"Preamble"``. ``###``
    headings stay inside their parent section.
    """
    lines = body.split("\n")
    title = ""
    sections = {}
    current = "Preamble"
    start = 0

    for level, text, line_no in _headings(body):
        if level > 2:
            continue
        sections[current] = "\n".join(lines[start:line_no]).strip()
        current = text if level == 2 else "Preamble"
        if level == 1:
            title = text
        start = line_no + 1

    sections[current] = "\n".join(lines[start:]).strip()
    return title, sections


def _split_macro_steps(steps_text):
    """Split the Steps section into ``(title, body)`` pairs by ``###`` headings."""
    if not steps_text:
        return []

    lines = steps_text.split("\n")
    headings = [h for h in _headings(steps_text) if h[0] == 3]
    steps = []
    for idx, (_, title, line_no) in enumerate(headings):
        end = headings[idx + 1][2] if idx + 1 < len(headings) else len(lines)
        steps.append((title, "\n".join(lines[line_no + 1:end]).strip()))
    return steps


def _python_blocks(md_text):
    """Return the source of every ```python fenced block in ``md_text``."""
    return [
        tok.content
        for tok in _MD.parse(md_text)
        if tok.type == "fence" and tok.info.strip().lower().startswith("python")
    ]


def _split_substeps(body):
    """Split a macro-step body into its numbered sub-steps.

    Returns a list of ``(raw_markdown, [python_sources])`` — one entry per
    top-level ordered-list item. Returns ``[]`` when the macro step has no
    numbered list, in which case the caller treats the whole body as one step.
    """
    if not body.strip():
        return []

    tree = SyntaxTreeNode(_MD.parse(body))
    lines = body.split("\n")
    substeps = []
    for node in tree.children:
        if node.type != "ordered_list":
            continue
        for item in node.children:
            start, end = item.map
            raw = "\n".join(lines[start:end]).strip()
            code = [
                n.content
                for n in item.walk()
                if n.type == "fence" and n.info.strip().lower().startswith("python")
            ]
            substeps.append((raw, code))
    return substeps


class Protocol:
    """Parse, render and execute a scientific protocol written in markdown.

    Expected document layout::

        ---
        author: TrappyUser
        editor: Another TrappyUser
        description: ...
        references: ...
        ---
        # Title of the protocol
        1. Preamble line
        ## Requirements
        1. Requirement
        ## Steps
        ### Macro step 1
        1. Sub-step (optional)
           ```python
           scope.beacon.blink()   # run automatically
           ```
        ## Additional Information
        Optional closing notes.

    Each ``### Macro step`` is executed in order: its ```python blocks run in
    the supplied namespace, then the user is prompted to confirm it is done.
    """

    def __init__(self, protocol):
        self.name = protocol
        self.text = gitf.get_file("protocols", protocol)

        self.meta, body = _split_frontmatter(self.text)
        self.title, sections = _split_sections(body)

        self.preamble = sections.get("Preamble", "")
        self.requirements = sections.get("Requirements", "")
        self.additional = sections.get("Additional Information", "")
        self.steps = _split_macro_steps(sections.get("Steps", ""))
        self.done = [False] * len(self.steps)
        self.responses = [[] for _ in self.steps]  # one list of responses per macro step

    def _render(self):
        """Serialise the protocol back to its markdown source.

        Completed steps (``self.done[i]`` is True) get a ``✓`` on their heading.
        """
        parts = []
        if self.meta:
            body = "\n".join(f"{key}: {value}" for key, value in self.meta.items())
            parts.append(f"---\n{body}\n---")

        parts.append(f"# {self.title}")
        if self.preamble:
            parts.append(self.preamble)
        if self.requirements:
            parts.append(f"## Requirements\n{self.requirements}")

        if self.steps:
            chunk = ["## Steps"]
            for (title, body), done in zip(self.steps, self.done):
                title = title[:-2] if title.endswith(" ✓") else title  # idempotent
                chunk.append(f"### {title} ✓" if done else f"### {title}")
                if body:
                    chunk.append(body)
            parts.append("\n".join(chunk))

        if self.additional:
            parts.append(f"## Additional Information\n{self.additional}")

        return "\n\n".join(parts) + "\n"

    def write(self, path, mark_done=False):
        """Write the protocol to ``path`` as markdown.

        mark_done: if True, flag every step as done before writing. Otherwise
                   the file reflects whatever was completed during ``execute``.
        """
        if mark_done:
            self.done = [True] * len(self.steps)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self._render())
        return path

    def show(self):
        """Render the static part of the protocol (metadata, preamble, requirements)."""
        print(Rule(self.title or self.name, style="bold"))

        if self.meta:
            table = Table.grid(padding=(0, 1))
            table.add_column(style="bold cyan", justify="right")
            table.add_column()
            for key, value in self.meta.items():
                table.add_row(f"{key}:", value)
            print(Panel(table, title="Metadata", border_style="cyan"))

        if self.preamble:
            print(Markdown(self.preamble))
        if self.requirements:
            print(Panel(Markdown(self.requirements), title="Requirements", border_style="yellow"))


    
    def execute(self, globals_=globals()):
        """Run the protocol step by step (blocking on user prompts).
 
        exp:      Experiment object (needs ``.log`` and ``.user_prompt``).
        globals_: namespace in which inline ```python blocks are executed.
        """
        exp = Experiment.current
        exp.log("protocol_executed", attribs={"name": self.name})
        self.show()
 
        print(Panel(Align.center("Procedure"), style="bold yellow on blue"))
        for index, (title, body) in enumerate(self.steps, start=1):
            print(Markdown(f"## Step {index}: {title}"))
 
            # Each numbered sub-step runs and is confirmed on its own. A macro
            # step with no numbered list is treated as a single sub-step.
            substeps = _split_substeps(body) or [(body, _python_blocks(body))]
            replies = []
            for sub, (raw, code) in enumerate(substeps, start=1):
                if raw:
                    print(Panel(Markdown(raw), style="bold white on blue"))
                for source in code:
                    exec(source.strip(), globals_)
                label = f"{self.name}: {title} ({sub}/{len(substeps)})"
                replies.append(exp.user_prompt("done", label=label))
 
            self.responses[index - 1] = replies
            self.done[index - 1] = True
 
        if self.additional:
            print(Panel(Markdown(self.additional), title="Additional Information", border_style="green"))
        print(Panel(Align.center("Protocol Finished"), style="bold black on green"))