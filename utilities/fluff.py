from colorama import Fore
from pprint import pprint

def intro():
  text = \
"""
..............................................................


Trappy Scopes Control Layer
===========================


Experiment(experiemnt_name) : to create/load an experiment.
exp = Experiment(experiemnt_name) : recommended.
exp.close() / close() : close the experiment.
close() / exp_close() are the recommended methods.

Standard Assignments:
--------------------
exp : Experiment object.
cam : Camera object.
lit : Illumination/Light object.
pico: Raspberry Pi Pico object.
..............................................................
"""
  print(text)
  #return text



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
	return "%s%s%s"%(Fore.CYAN, text, Fore.RESET)




if __name__ == "__main__":
	print(pageheader())