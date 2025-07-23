"""
Module uses skimage to detect circles reliably.

Pipeline:
1. Receive a grayscale image.
2. Perform a guassian blur and a canny edge detection transform -> edges.
3. Perform image segmentation on the edges and filter the list for a min-radius.
4. Return the list of circles, fits, etc.
"""

import numpy as np
from skimage.feature import canny
from scipy.ndimage import gaussian_filter
from skimage.measure import label, regionprops, regionprops_table
import matplotlib.pyplot as plt


import numpy as np
from skimage.measure import regionprops

import numpy as np
from skimage.measure import regionprops


def merge_regionprops_list(region_list):
    """
    Merge a list of RegionProperties objects into one combined region.
    Written by deepseek
    
    Parameters:
    region_list (list of RegionProperties): Objects to merge.
    
    Returns:
    RegionProperties: Merged region (coordinates relative to union bounding box).
                     Returns None for empty input or invalid regions.
    """
    if not region_list:
        return None
        
    # Find the union bounding box covering all regions
    min_row = min(r.bbox[0] for r in region_list)
    min_col = min(r.bbox[1] for r in region_list)
    max_row = max(r.bbox[2] for r in region_list)
    max_col = max(r.bbox[3] for r in region_list)
    
    # Handle degenerate case
    if max_row <= min_row or max_col <= min_col:
        return None
        
    # Create empty mask for the union bounding box
    height = max_row - min_row
    width = max_col - min_col
    combined_mask = np.zeros((height, width), dtype=bool)
    
    # Place each region's mask in the combined mask
    for region in region_list:
        r_start = region.bbox[0] - min_row
        r_end = r_start + (region.bbox[2] - region.bbox[0])
        c_start = region.bbox[1] - min_col
        c_end = c_start + (region.bbox[3] - region.bbox[1])
        
        # Ensure the region mask fits in the combined mask
        combined_mask[r_start:r_end, c_start:c_end] |= region.image
    
    # Compute properties of the merged region
    label_image = combined_mask.astype(np.int32)
    props = regionprops(label_image)
    return props[0] if props else None




def detect_circles(image, no_circles, min_diameter, max_diameter=np.inf, 
                   guassian_blur_sigma=1, canny_sigma=1):
    
    """
    Perform accurate circle detection using canny and skimage.label and skimage.measure.regionprops.
    Works for concentric circles.
    
    Returns:
    1. A list of circles (x, y, r) in descending order of size of the circle.
    2. List of corresponding RegionProperties.
    """
    
    ## Process image
    blurred = gaussian_filter(image, guassian_blur_sigma)
    edges = canny(blurred, sigma=canny_sigma)
    #plt.imshow(edges)
    #plt.show()
    ## Segment image
    label_img = label(edges)
    regions = regionprops(label_img)
    
    ## Filter region
    regions = [prop for prop in regions if (prop.axis_minor_length*2 > min_diameter and \
                                            prop.axis_minor_length*2 <= max_diameter)]
    regions = sorted(regions, key=lambda props: props.area, reverse=True)
    
    if len(regions)>2:
        regions = [regions[0], merge_regionprops_list(regions[1:])]
        
    
    circles = []
    regionprops_ = []
    
    ## Calculate circles for each boundingbox
    for i, props in enumerate(regions):
        
        minr, minc, maxr, maxc = props.bbox
        cx = int(np.round((maxc + minc)/2))
        cy = int(np.round((maxr + minr)/2))
        
        
        ## Radius is the maximum of the two axes.
        #radius = int(np.round(max((maxr-minr)/2, (maxc-minc)/2)))
        
        ## Radius of the enclosed circle
        #radius = int(np.round(np.sqrt((maxr - minr)**2 + (maxc - minc)**2)))
        diameter = np.mean([(maxr - minr), (maxc - minc)])
        radius = int(np.round(diameter/2))

        circles.append([cx, cy, radius])
        regionprops_.append(props)
        
    return circles[:2], regionprops_[:2]
    
    

