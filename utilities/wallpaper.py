from art import text2art
from rich.console import Console
from rich.terminal_theme import MONOKAI

import os
import ctypes
import platform




def generate_wallpaper(info):
	scopename=text2art(info["name"], font="tarty8")
	console = Console(record=True)
	console.print(scopename)
	console.print("\n\n\n")
	console.print(info)
	console.save_svg(os.path.join(os.path.expanduser('~'), "wallpaper.svg"), theme=MONOKAI)

def_wallpaper_path = os.path.join(os.path.expanduser('~'), "wallpaper.svg")


def set_wallpaper(path):
    #Check the operating system
    system_name = platform.system().lower()
    if system_name =='linux':
        path = os.getcwd()+path
        command = "gsettings set org.gnome.desktop.background picture-uri file:" + path
        os.system(command)
    elif system_name == 'windows':
        path = os.getcwd()+path
        ctypes.windll.user32.SystemParametersInfoW(20,0,path,0)