# Project Blueprint: Depth-Aware Wigglegram Processor

This app uses depth-map-based parallax with optical "perfection-breaking" to eliminate the "cardboard cutout" effect.

## 1. Technical Requirements

* **Input:** Source Image, Depth Map (Depth Anything V2/Lotus).
* **Motion:** $\pm 2^{\circ}$ camera-swing interpolation.
* **Texture:** Blue Noise for dithering.

## 2. Core Implementation Modules

### A. Circular Disc Bokeh (Optical Parallax)

* **Objective:** Blur the background during the "wiggle" to simulate a wide-aperture lens.
* **Instruction:** Replace Gaussian blur with a Circular Disc Kernel.
* **Implementation:**
* Kernel radius $R$ is a function of the depth map: $R = CoC \times |Z - Focus\_Distance|$.
* Use Blue Noise to jitter the sampling points within the disc to hide banding artifacts.



### B. Light Wrap (Edge Blending)

* **Objective:** Integrate the foreground subject into the background movement.
* **Instruction:** Calculate the edge gradient of the Depth Map.
* **Implementation:** At the edges of the foreground mask, perform a soft "dilate" and sample the background color, blending it onto the foreground edge by 2–3 pixels. As the image "wiggles," the background light will appear to "spill" around the subject.

### C. Chromatic Aberration Jitter

* **Objective:** Mimic vintage lens misalignment.
* **Instruction:** During the wiggle swing, shift the R and B channels by a factor of $k \times \sin(t)$, where $t$ is the animation frame.
* **Requirement:** $k$ should be small (max 1.5 pixels) to maintain sharpness while adding "glassy" artifacts.
