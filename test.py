import sys
from prompt_toolkit import prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from pygments.lexers import PythonLexer
from pygments.token import Token

class CustomCompleter(Completer):
    def get_completions(self, document, complete_event):
        try:
            import readline
        except ImportError:
            return

        line = document.current_line.lstrip()
        begidx, endidx = readline.get_begidx(), readline.get_endidx()

        before_cursor = line[:endidx]
        word_before_cursor = before_cursor.split()[-1]

        completions = []
        for obj in dir(__main__):
            if obj.startswith(word_before_cursor):
                completions.append(obj)

        for completion in completions:
            yield Completion(completion, start_position=-len(word_before_cursor))

def get_prompt_tokens(cli):
    return [
        (Token.Prompt, '>>> ' if cli.in_main_input else '... '),
    ]




def fn_(fn, *args, **kwargs):
    return f"{fn}({str(list(args)).strip('[').strip(']')} {','*(len(args)!=0 and len(kwargs) != 0)} {str([f'{key}={kwargs[key]}' for key in kwargs]).strip('[').strip(']')})"

import plotext as plt

from rich.layout import Layout
from rich.live import Live
from rich.ansi import AnsiDecoder
from rich.console import Group
from rich.jupyter import JupyterMixin
from rich.panel import Panel
from rich.text import Text

from time import sleep
import plotext as plt

def make_plot(width, height, phase = 0, title = ""):
    plt.clf()
    l, frames = 1000, 30
    x = range(1, l + 1)
    y = plt.sin(periods = 2, length = l, phase = 2 * phase  / frames)
    plt.scatter(x, y, marker = "fhd")
    plt.plotsize(width, height)
    plt.xaxes(1, 0)
    plt.yaxes(1, 0)
    plt.title(title)
    plt.theme('dark')
    plt.ylim(-1, 1)
    #plt.cls()
    return plt.build()

class plotextMixin(JupyterMixin):
    def __init__(self, phase = 0, title = ""):
        self.decoder = AnsiDecoder()
        self.phase = phase
        self.title = title

    def __rich_console__(self, console, options):
        self.width = options.max_width or console.width
        self.height = options.height or console.height
        canvas = make_plot(self.width, self.height, self.phase, self.title)
        self.rich_canvas = Group(*self.decoder.decode(canvas))
        yield self.rich_canvas

def make_layout():
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=1),
        Layout(name="main", ratio=1),
    )
    layout["main"].split_column(
        Layout(name="static", ratio = 1),
        Layout(name="dynamic"),
    )
    return layout




layout = make_layout()

header = layout['header']
title = plt.colorize("Pl✺ text ", "cyan+", "bold") + "integration with " + plt.colorize("rich_", style = "dim")
header.update(Text(title, justify = "left"))

static = layout["static"]
phase = 0
mixin_static = Panel(plotextMixin(title = "Static Plot"))
static.update(mixin_static)

dynamic = layout["dynamic"]

with Live(layout, refresh_per_second=0.0001) as live:
    while True:
        phase += 1
        mixin_dynamic = Panel(plotextMixin(phase, "Dynamic Plot")) 
        dynamic.update(mixin_dynamic)
        #sleep(0.001)
        live.refresh()

print(fn_("do", 1, 2, 3, kwg=123, sf="dsfs"))

    # try:
    #     user_input = prompt(
    #         lexer=PygmentsLexer(PythonLexer),
    #         style={Token.Prompt: '#ansiblue'},
    #         auto_suggest=get_prompt_tokens,
    #         completer=CustomCompleter(),
    #     )
    #     exec(user_input)
    # except KeyboardInterrupt:
    #     break
    # except Exception as e:
    #     print(e)
