# -*- coding: utf-8 -*-
from colorama import Fore
from pprint import pprint
from rich import print

def getintro():
  text = \
"""
# Trappy Scopes Control Layer

+ Experiment(experiemnt_name) : to create/load an experiment.
+ exp = Experiment(experiemnt_name) : recommended.
+ exp.close() / close() : close the experiment.
+ close() / exp_close() are the recommended methods.

## Standard Assignments

+ exp : Experiment object.
+ cam : Camera object.
+ lit : Illumination/Light object.
+ pico: Raspberry Pi Pico object.
"""
  #print(text)
  return text

def intro():
  from rich.markdown import Markdown
  from rich.panel import Panel
  print(Panel(Markdown(getintro()), title="Introduction"))



def pageheader():
	text = """
  *     ████████╗    ██████╗      █████╗     ██████╗     ██████╗     ██╗   ██╗
  _     ╚══██╔══╝    ██╔══██╗    ██╔══██╗    ██╔══██╗    ██╔══██╗    ╚██╗ ██╔╝
 | |       ██║       ██████╔╝    ███████║    ██████╔╝    ██████╔╝     ╚████╔╝ 
 | |       ██║       ██╔══██╗    ██╔══██║    ██╔═══╝     ██╔═══╝       ╚██╔╝  
 |_|       ██║       ██║  ██║    ██║  ██║    ██║         ██║            ██║   
 |_|       ╚═╝       ╚═╝  ╚═╝    ╚═╝  ╚═╝    ╚═╝         ╚═╝            ╚═╝   
_____                                                                         
-----   ███████╗     ██████╗     ██████╗     ██████╗     ███████╗    ███████╗ 
  ^.    ██╔════╝    ██╔════╝    ██╔═══██╗    ██╔══██╗    ██╔════╝    ██╔════╝ 
 | |    ███████╗    ██║         ██║   ██║    ██████╔╝    █████╗      ███████╗ 
 ---    ╚════██║    ██║         ██║   ██║    ██╔═══╝     ██╔══╝      ╚════██║ 
        ███████║    ╚██████╗    ╚██████╔╝    ██║         ███████╗    ███████║ 
 ===    ╚══════╝     ╚═════╝     ╚═════╝     ╚═╝         ╚══════╝    ╚══════╝

        Living Physics Group, Instituto Gulbenkian de Ciência, Oeiras, PT

"""
	return f"[cyan]{text}[default]"
	#return f"{}{text}{""}"

def pageheader_plain():
  text = """
  *     ████████╗    ██████╗      █████╗     ██████╗     ██████╗     ██╗   ██╗
  _     ╚══██╔══╝    ██╔══██╗    ██╔══██╗    ██╔══██╗    ██╔══██╗    ╚██╗ ██╔╝
 | |       ██║       ██████╔╝    ███████║    ██████╔╝    ██████╔╝     ╚████╔╝ 
 | |       ██║       ██╔══██╗    ██╔══██║    ██╔═══╝     ██╔═══╝       ╚██╔╝  
 |_|       ██║       ██║  ██║    ██║  ██║    ██║         ██║            ██║   
 |_|       ╚═╝       ╚═╝  ╚═╝    ╚═╝  ╚═╝    ╚═╝         ╚═╝            ╚═╝   
_____                                                                         
-----   ███████╗     ██████╗     ██████╗     ██████╗     ███████╗    ███████╗ 
  ^.    ██╔════╝    ██╔════╝    ██╔═══██╗    ██╔══██╗    ██╔════╝    ██╔════╝ 
 | |    ███████╗    ██║         ██║   ██║    ██████╔╝    █████╗      ███████╗ 
 ---    ╚════██║    ██║         ██║   ██║    ██╔═══╝     ██╔══╝      ╚════██║ 
        ███████║    ╚██████╗    ╚██████╔╝    ██║         ███████╗    ███████║ 
 ===    ╚══════╝     ╚═════╝     ╚═════╝     ╚═╝         ╚══════╝    ╚══════╝

        Living Physics Group, Instituto Gulbenkian de Ciência, Oeiras, PT

"""
  return text


if __name__ == "__main__":
	print(pageheader())