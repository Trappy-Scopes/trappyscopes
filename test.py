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

    def calibrate_camera():
        """
        Slowly increase light and measure camera counts.
        """
        return
        # Fix resolution and framerate
        cmap = {'r':0, 'g':1, 'b':2}
        COLOR_CALIBRATION_RESOLUTION = 0.05
        color_calib_curve = {}
        color_calib_curve_std = {}
        total_pixels = camera.resolution[0]*camera.resolution[1]
        
        for color in ['r', 'g', 'b']:   
            self.lights.set_color(color)
            color_calib_curve[color] = {}
            color_calib_curve_std[color] = {}
            time.sleep(2)
            if self.mcu.completed(timeout_sec=2): #How would this work?
                for lux in range(0.0, 1.0, COLOR_CALIB_RESOLUTION):
                    
                    self.lights.set_lux(lux)
                    if self.mcu.completed(timeout_sec=2):
                        time.sleep(2) # Sleep fot 2 seconds
                        
                        frames = self.get_frames()
                        # frames[frame_no][row][column][color]
                        r_ch = []
                        g_ch = []
                        b_ch = []
                        for f in frames.shape[0]:
                            # TODO summation needs to happen over entire array: here axis is not specified. Fix
                            r_ch.append(np.sum(frames[f, :, :, 0], dtype=np.float64)/total_pixels)
                            g_ch.append(np.sum(frames[f, :, :, 1], dtype=np.float64)/total_pixels)
                            b_ch.append(np.sum(frames[f, :, :, 2], dtype=np.float64)/total_pixels)

                        # Sum over all channels
                        color_calib_curve[color][lux] = [np.mean(r_ch), np.mean(g_ch), np.mean(b_ch)]
                        color_calib_curve_std[color][lux] = [np.std(r_ch), np.std(g_ch), np.std(b_ch)]

        print(color_calib_curve)
        print(color_calib_curve_std)
