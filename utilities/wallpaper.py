from art import text2art
from rich.console import Console
from rich.terminal_theme import MONOKAI
from rich.layout import Layout
from rich.panel import Panel
from rich.pretty import Pretty


import os
import ctypes
import platform
import io
#import matplotlib.pyplot as plt

from .fluff import pageheader
from bookeeping.session import Session

def_wallpaper_path = os.path.join(os.path.expanduser('~'), "wallpaper.svg")


def generate_wallpaper(info):
	stream = io.StringIO() ## Temporary dump
	scopename=text2art(info["name"], font="tarty8")
	console = Console(record=True, file=stream, width=int(1920/8), height=int(1080/8))
	
	layout = Layout()
	layout.split_row(
		Layout(name="left"),
		Layout(name="right"),
	)
	layout["left"].size = int(1920/8*(1/2))
	lpanel = "\n"*10 + pageheader() + "\n"*3 + f'Control layer version: {Session.current.commitid()}{" "}{scopename}'
	p1 = Panel(lpanel)
	p2 = Panel(Pretty(info), title="Scope parameters")

	layout["left"].update(p1)
	layout["right"].update(p2)

	console.print(layout)
	console.save_svg(os.path.join(os.path.expanduser('~'), "wallpaper.svg"), theme=MONOKAI, title="Trappy-Scope")

def generate_wallpaper2(info):
	
	from PIL import ImageFont, ImageDraw, Image
	import numpy as np
	import cv2
	image = np.ones((1080, 1920, 3), dtype=np.uint8)
	# Convert to PIL Image
	cv2_im_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
	pil_im = Image.fromarray(image)
	draw = ImageDraw.Draw(pil_im)

	# Choose a font
	font = ImageFont.truetype("Adumu.ttf", 50)

	### Print -> Trappy Scopes
	draw.text((0, 5), text=pageheader(), font=font)

	### Print -> Scope name
	scopename=text2art(info["name"], font="tarty8")
	draw.text((0, 1), text=scopename, font=font)



	# Save the image
	cv2_im_processed = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
	cv2.imwrite(os.path.join(os.path.expanduser('~'), "wallpaper.png"), cv2_im_processed)


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


def stl_render(path):
	## Little help from chatgpt		 
	import trimesh                                                              
	import matplotlib.pyplot as plt                                             
	from mpl_toolkits.mplot3d.art3d import Poly3DCollection                     
																				  
	# Load the STL file                                                         
	mesh = trimesh.load(path)                                                   
																				  
	# Extract vertices and faces                                                
	vertices = mesh.vertices                                                    
	faces = mesh.faces                                                          
																				  
	# Set up Matplotlib figure and 3D axis with high DPI                        
	fig = plt.figure(figsize=(10, 10), dpi=150)  # Increased size and DPI       
	ax = fig.add_subplot(111, projection='3d')                                  
																				  
	# Create a Poly3DCollection for the faces of the mesh with improved aestheti
	poly3d = [[vertices[vertex] for vertex in face] for face in faces]          
	mesh_collection = Poly3DCollection(poly3d, alpha=0.8, edgecolor='k', linewidths=0.1, facecolor='gray')
	# Add the collection to the axis                                            
	ax.add_collection3d(mesh_collection)                                        
																				  
	# Set limits for better visualization                                       
	scale = vertices.flatten()                                                  
	ax.auto_scale_xyz(scale, scale, scale)                                      
																				  
	# Label axes                                                                
	ax.set_xlabel("X")                                                          
	ax.set_ylabel("Y")
	ax.set_zlabel("Z")
	 
	plt.show()      