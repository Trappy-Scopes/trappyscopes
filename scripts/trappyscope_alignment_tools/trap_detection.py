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



def detect_circle_hough(image, min_radius=400, max_radius=700):
    """
    Detect circle using Hough transform.
    """
    from skimage.transform import hough_circle, hough_circle_peaks
    from skimage.feature import canny
    from skimage.draw import circle_perimeter
    from skimage.util import img_as_ubyte


    # Load picture and detect edges
    edges = canny(image, sigma=1, low_threshold=10, high_threshold=50)

    # Detect two radii
    hough_radii = np.arange(min_radius, max_radius, 2)
    hough_res = hough_circle(edges, hough_radii)

    # Select the most prominent 3 circles
    accums, cx, cy, radii = hough_circle_peaks(hough_res, hough_radii, total_num_peaks=1)

    # Draw them
    detection = np.ones(image.shape)
    fig, ax = plt.subplots(ncols=1, nrows=1, figsize=(10, 4))
    for center_y, center_x, radius in zip(cy, cx, radii):
        circy, circx = circle_perimeter(center_y, center_x, radius, shape=image.shape)
        detection[circy, circx] = 0
    ax.imshow(detection, cmap=plt.cm.gray)
    plt.show()

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
    



def trap_detection_plot(image, circles, regions, title=None):
    colors = ["r", "b", "g", "orange", "cyan"]
    
    fig, ax = plt.subplots(figsize=(10,10))
    
    ax.imshow(image, origin="lower", interpolation=None, cmap="gist_gray")
    ax.set_xlim([0, image.shape[0]])
    ax.set_ylim([0, image.shape[1]])
    
    ## Demarkate region bounding-boxes
    for i, props in enumerate(regions):
        minr, minc, maxr, maxc = props.bbox
        bx = (minc, maxc, maxc, minc, minc)
        by = (minr, minr, maxr, maxr, minr)
        ax.plot(bx, by, linestyle='-', linewidth=0.5, color=colors[i])
        
    for i, circle in enumerate(circles):
        cx, cy, radius = circle
        radius = np.round(max((maxr-minr)/2, (maxc-minc)/2))
        circle_patch = plt.Circle((cx, cy), radius, fill=True, 
                linewidth=0.01, alpha=0.2, color=colors[i])
        ax.add_patch(circle_patch)
    ax.set_title(title)
    return fig, ax

def iterate_thresholds(image, min_diameter, max_diameter=np.inf, 
                   guassian_blur_sigma_max=3, canny_sigma_max=3):
    """
    Iterate over thresholds to arrive at the best pairwise detections.
    """
    results = {}
    for guassian_blur_sigma in np.arange(1.0, guassian_blur_sigma_max+1, 1):
        for canny_sigma in np.arange(1.0, canny_sigma_max+1, 1):
            circles, regions = detect_circles(image, 2, min_diameter, guassian_blur_sigma=guassian_blur_sigma, canny_sigma=canny_sigma)
            if circles:
                delx = (circles[1][0] - circles[0][0])
                dely = (circles[1][1] - circles[0][1])
                delr = (circles[1][2] - circles[0][2])

                results[(int(guassian_blur_sigma), int(canny_sigma))] = np.abs(delx) + np.abs(dely) + np.abs(delr)
    min_deviation = min(results, key = results.get)
    return {"guassian_blur_sigma":min_deviation[0], "canny_sigma":min_deviation[1]}


def define_magnification(reff, trap_dia_mm=2.8, real_pix_size=1.55):
    trap_dia_um = trap_dia_mm*1000
    def pix_sizer(r):
        return trap_dia_um / (2*r)
    pix_size = pix_sizer(reff)
    one_x_size_um = (trap_dia_mm*1000)/real_pix_size
    return one_x_size_um/(reff*2.0)


def profile_trap_boundaries(fov_og, x,y,r, length=20, pad=25):
    """
    Fits guassian to line profiles of the trap at four places: topp-most, bottom-most, left-most, and 
    right-most points of the rectangle that inscribes the circular trap
    
    returns:
    fig, axes, packet
    packet: contains corrs (corrections) and sigmas of the fitted guassians.
    
    """
    from scipy.optimize import curve_fit
    from copy import deepcopy
    from skimage.draw import circle_perimeter

    fig, axes = plt.subplots(nrows=4, ncols=2, figsize=(16,10), 
                             gridspec_kw={"wspace":0.05, "hspace":0.5, 'width_ratios': [10, 1]},
                             sharey=True)
    
    fov = ~deepcopy(fov_og)
    
    ## Fake channels
    ch = np.zeros(shape=fov.shape, dtype=fov.dtype)
    
    rr, cc = circle_perimeter(x, y, r)
    ch[rr, cc] = 255
    
    
    def gaussian(x, mu, sigma):
        return  np.exp(-(x - mu)**2 / (2 * sigma**2))
    
    
    def guassian_fitter(profile):
        
        mu0 = np.argmax(profile)
        sigma0 = np.std(profile)*16
        
        # Fit Gaussian to profile
        popt, pcov = curve_fit(gaussian, np.arange(0, len(profile)), profile, p0=[mu0, sigma0])
        return popt
    
    ## Top
    top = fov[y+r-pad:y+r+pad, x-length:x+length]
    im1 = axes[0][0].imshow(top, aspect="auto", interpolation=None)
    axes[0][1].axhline(pad, linestyle="--", color="red")
    
    
    def profiler(profile, axis):
        profile = profile / 255
        profile = (profile - np.min(profile))
        profile = profile/np.max(profile)
        axis.plot(profile, np.arange(len(profile)))
        popt = guassian_fitter(profile)
        mu, sigma = popt
        fit_curve_left = gaussian(np.arange(len(profile)), mu, sigma) 
        axis.plot(fit_curve_left, np.arange(len(profile)), 'k--', linewidth=2, label='Gaussian Fit')  
        fit_text = f'μ = {mu:.1f}\nσ = {sigma:.1f}'
        axis.set_title(fit_text)
        return popt
    
    
    top_line_prof = top.mean(axis=1)
    top_fit = profiler(top_line_prof, axes[0][1])
    top_corr = int(np.round(top_fit[0]-pad))
    axes[0][0].set_title(fr"Top corner - $\delta={top_corr}$")
    
    
    
    ## Bottom
    bottom = fov[y-r-pad:y-r+pad, x-length:x+length]
    im2 = axes[1][0].imshow(bottom, aspect="auto", interpolation=None)
    axes[1][1].axhline(pad, linestyle="--", color="red")
    
    bottom_line_prof = bottom.mean(axis=1)
    #axes[1][1].plot(bottom_line_prof, np.arange(len(bottom_line_prof)))
    bottom_fit = profiler(bottom_line_prof, axes[1][1])
    bottom_corr = int(np.round(bottom_fit[0]-pad))
    axes[1][0].set_title(fr"Bottom corner - $\delta={bottom_corr}$")

    
    ## Left
    left = fov[y-length:y+length, x-r-pad:x-r+pad].T
    left_line_prof = left.mean(axis=1)
    #axes[2][1].plot(left_line_prof, np.arange(len(left_line_prof)))
    axes[2][1].axhline(pad, linestyle="--", color="red")
    left_fit = profiler(left_line_prof, axes[2][1])
    im3 = axes[2][0].imshow(left, aspect="auto", interpolation=None)
    
    left_corr = int(np.round(left_fit[0]-pad))
    axes[2][0].set_title(fr"Left corner - $\delta={left_corr}$")
    
    
    ## Right
    right = fov[y-length:y+length, x+r-pad:x+r+pad].T
    right_line_prof = right.mean(axis=1)
    #axes[3][1].plot(right_line_prof, np.arange(len(right_line_prof)))
    right_fit = profiler(right_line_prof, axes[3][1])
    axes[3][1].axhline(pad, linestyle="--", color="red")
        
    #print(right.shape)
    im4 = axes[3][0].imshow(right, aspect="auto", interpolation=None)
    
    right_corr = int(np.round(right_fit[0]-pad))
    axes[3][0].set_title(fr"Right corner - $\delta={right_corr}$")
    
    # left, right, bottom, top
    packet={"corrs":[left_corr, right_corr, bottom_corr, top_corr], 
            "sigmas":[left_fit[1], right_fit[1], bottom_fit[1], top_fit[1]]}
    
    plt.suptitle("Trap boundary profiles")
    return fig, axes, packet

if __name__ == "__main__":
    thresholds = iterate_thresholds(image, 400)
    circles, regions = detect_circles(image, 2, min_diameter=400, **thresholds)
    fig, ax = trap_detection_plot(image, circles, regions)
    radii = [circles[1][2], circles[0][2]]
    reff = (radii[0]+radii[1])/2
    xc = circles[0][0]
    yc = circles[0][1]
    ax.set_title(fr"Trap radii: {radii[0]}px to {radii[1]}px; $r_e$ : {reff:.1f}{'\n'}Thresholds: {str(thresholds)}")
    center_dev_x = np.abs(xc - image.shape[0]/2)
    center_dev_y = np.abs(yc - image.shape[1]/2)

    magnification = define_magnification(reff)
    
    ax.scatter([xc], [yc], marker="x", label="Trap center", color="red")
    ax.scatter([image.shape[0]/2], [image.shape[1]/2], marker="x", label="FOV center", color="blue")
    
    _, intensity_centroid = image_centroid(image)
    ax.scatter([intensity_centroid[1]], [intensity_centroid[0]], marker="x", label="Intensity center", color="yellow")
    
    ## Add the deviation circle
    deviation_threshold = 50
    dev_circle = plt.Circle((int(image.shape[0]/2), int(image.shape[1]/2)), deviation_threshold, color='blue', fill=False)
    ax.add_patch(dev_circle)

    ax.legend(loc='upper right')
    fig.suptitle(fr"Trap centring errors: $\Delta_x$:{center_dev_x}; $\Delta_y$:{center_dev_y}{'\n'}Magnification:{magnification:.2f}X;  Centering-threshold-radius:{deviation_threshold}px")
    fig.show()

    ## Trap boundary profiles
    fig, ax, packet = profile_trap_boundaries(image, int(xc), int(yc), int(reff))
    fig.show()


