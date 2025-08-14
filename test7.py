from raytracing import *
import matplotlib.pyplot as plt
# Define a Lambertian LED source (half-size 1 mm) with cosine angular emission
#inputRays = LambertianRays(yMin=-0.5, yMax=0.5, M=50, N=5, I=1.3)

inputRays = ObjectRays(2, halfAngle=0.436, H=1, T=10, z=0, rayColors=["r"]*1000, label="ThorLabs\nRGBE(red only)")
# Build optical path: source → space → lens → space
path = OpticalPath()
path.objectHeight=1
path.fanAngle=50
path.fanNumber=1
path.append(Space(d=200.2))
path.append(thorlabs.AC254_100_A_ML())
path.append(Space(d=200.1))

# Trace rays through the system
outputRays = path.traceManyThrough(inputRays)


# Visualize input (left) and output (right) rays
path.display(raysList=[inputRays], onlyPrincipalAndAxialRays=True)
