

from raytracing import *
import numpy as np
import matplotlib.pyplot as plt

class LEDSource(Rays):
    """Custom LED light source with angular and spatial characteristics"""
    def __init__(self, position, direction, wavelength=450e-9, 
                 half_angle=30, size=1e-3, nRays=1000):
        """
        position: (x, y, z) coordinates [m]
        direction: (theta, phi) emission direction [radians]
        wavelength: Central wavelength [m]
        half_angle: Full width at half maximum angle [degrees]
        size: LED die size [m]
        nRays: Number of rays to generate
        """
        super().__init__()
        self.position = np.array(position)
        self.direction = np.array(direction)
        self.wavelength = wavelength
        self.half_angle = np.radians(half_angle)
        self.size = size
        self.nRays = nRays
        
    def angular_distribution(self, theta):
        """Lambertian (cosine) angular distribution"""
        return np.cos(theta)**4  # Typical LED emission profile
    
    def generateRays(self):
        rays = []
        for _ in range(self.nRays):
            # Spatial distribution (uniform over LED surface)
            x_offset = np.random.uniform(-self.size/2, self.size/2)
            y_offset = np.random.uniform(-self.size/2, self.size/2)
            position = self.position + [x_offset, y_offset, 0]
            
            # Angular distribution (Lambertian)
            theta = np.random.uniform(0, self.half_angle)
            phi = np.random.uniform(0, 2*np.pi)
            
            # Direction vector
            dx = np.sin(theta) * np.cos(phi)
            dy = np.sin(theta) * np.sin(phi)
            dz = np.cos(theta)
            
            # Rotate to match LED direction
            direction = self.rotate_vector([dx, dy, dz], self.direction)
            
            # Create ray with wavelength property
            ray = Ray(position, direction, self.wavelength)
            ray.intensity = self.angular_distribution(theta)
            rays.append(ray)
        return rays

    def rotate_vector(self, vector, direction):
        """Rotate vector to align with emission direction"""
        # Simplified rotation (full implementation requires rotation matrix)
        return vector  # For actual use, implement proper 3D rotation




# Create optical path
path = ImagingPath()

# Add LED source (450nm blue LED, 30° viewing angle)
led = LEDSource(
    position=(0, 0, 0),
    direction=(0, 0),  # +Z direction
    wavelength=450e-9,
    half_angle=30,
    size=1e-3  # 1mm die size
)

# Add optical elements
path.append(Space(d=50e-3))      # 50mm free space
path.append(Lens(f=50e-3))       # 50mm focal length lens
path.append(Space(d=100e-3))     # 100mm to detector

# Generate and trace rays
led_rays = led.generateRays()
#traced_rays = path.traceMany(led_rays)

# Analyze results
#spot_positions = [ray.position for ray in traced_rays]
#intensities = [ray.intensity for ray in traced_rays]

# Plot spot diagram
#plt.figure(figsize=(10, 8))
#plt.scatter(
#    [p[0]*1000 for p in spot_positions],
#    [p[1]*1000 for p in spot_positions],
#    c=intensities,
#    cmap='viridis',
#    s=5
#)
#plt.colorbar(label='Relative Intensity')
#plt.xlabel('X Position (mm)')
#plt.ylabel('Y Position (mm)')
#plt.title('LED Illumination Pattern at Detector Plane')
#plt.grid(True)
#plt.show()

## iCal test
raise KeyboardInterrupt
import requests

# Replace with the actual iCalendar public URL
ics_url = 'https://calendar.google.com/calendar/ical/0a1d3a95d78a666e49d2824aaf20156f25e6aa64f868eff8f737ede23a3eb247%40group.calendar.google.com/public/basic.ics'

import requests
from icalendar import Calendar
from datetime import datetime

# Fetch the public .ics file (can be from a URL or local file)
response = requests.get(ics_url)

# Parse the iCalendar data
calendar = Calendar.from_ical(response.content)

# Print the events
for component in calendar.walk():
    if component.name == "VEVENT":
        summary = component.get('summary')
        start_time = component.get('dtstart').dt
        end_time = component.get('dtend').dt
        print(f"Event: {summary}")
        print(f"Start: {start_time}")
        print(f"End: {end_time}")
        print('---')
