# wiggle gram

A browser-based tool that turns a single photo into a wigglegram GIF — those wobbly, eye-catching 3D animations you see on social media and in lenticular prints.

## What is a wigglegram?

A wigglegram (or "wiggle stereoscopy") is an animated GIF that rapidly alternates between slightly different viewpoints of the same scene, creating a convincing illusion of depth on a flat screen. Traditional wigglegrams require multiple photos taken from different positions. This tool synthesizes all those viewpoints from a **single image** using a depth map.

## Quick Start

1. Open `wigglegram.html` in any modern browser (Chrome, Firefox, Edge, Safari)
2. Click **Upload Source Image** and pick a photo
3. (Optional) Click **Upload Depth Map** to supply a custom grayscale depth map
4. Adjust parameters in the right-hand panel
5. Click **Generate GIF**
6. Preview the result, then click **Download** to save

No server, no install, no dependencies — everything runs in your browser.

## Parameters Reference

### Motion

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **Effect Mode** | Three flavors of 3D motion. *Orbit* gives a natural "looking around" feel. *Parallax* has a punchy pop-out effect. *Warp* creates a liquid, stretchy look. | `orbit`: stereo disparity via pinhole camera model with parallel optical axes. `parallax`: forward-mapped depth-proportional horizontal shift, back-to-front compositing. `warp`: backward-mapped displacement, inverse sampling. |
| **Baseline** (orbit) | How much the viewpoint shifts side-to-side. Higher = more dramatic 3D, but edges may tear. 5-8cm mimics real lenticular camera spacing. | Lateral camera translation in cm. Disparity = `f_px * baseline * (1/Z_converge - 1/Z)`. |
| **Parallax Shift** (parallax/warp) | Same idea as baseline but in pixels. Controls how far objects move between frames. | Max per-frame pixel displacement, scaled by normalized depth. |
| **Frames** | More frames = smoother wiggle, bigger file. 8 is a good default. | Number of synthetic viewpoints sampled along a sinusoidal oscillation. |
| **Frame Delay** | Speed of the wiggle. Lower = faster. 60-100ms feels natural. | GIF frame delay in milliseconds. |
| **FOV** (orbit only) | Wider angle = less depth pop at the same baseline. Narrower = more telephoto compression. | Horizontal field of view in degrees. Sets pinhole focal length as `width / (2 * tan(fov/2))`. |

### Optics

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **Bokeh CoC** | Makes the background go soft and dreamy while the subject stays sharp. 0 = everything sharp. Higher = stronger blur. | Circle-of-confusion radius scaled by `|depth - focusDist|`, sampled with blue-noise-jittered disc kernel. |
| **Focus Dist** | Which depth plane stays perfectly sharp. 0 = far background, 1 = nearest foreground, 0.5 = middle. | Normalized depth value of the in-focus plane. Pixels at this depth get zero CoC. |
| **Light Wrap** | Adds a subtle glow where the subject meets the background, like light spilling around edges. | Sobel gradient on the depth map detects edges; background color is blended into foreground pixels with distance-weighted falloff. |
| **Chromatic Aberr** | Adds color fringing at the edges, simulating a cheap lens. Shifts with the wiggle for extra realism. | Per-frame lateral shift of R and B channels by `k * sin(angle)` with sub-pixel bilinear interpolation. G channel stays put. |

### Output

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **Output Width** | Final GIF width in pixels. Smaller = faster encode, smaller file. Height scales proportionally. | Source image is downsampled to this width before frame generation. |
| **Invert Depth** | Flip what's "near" and "far." Check this if your depth map uses the opposite convention. | Applies `depth = 1 - depth` to the normalized depth map before all processing. |

## Effect Modes

### Orbit
The most physically accurate mode. Simulates a row of cameras all pointed forward (parallel optical axes), like a real lenticular camera. Objects at the convergence plane stay still; near objects swing wide, far objects barely move. Best results with a proper depth map.

### Parallax
A simpler, punchier effect. Each pixel is shifted horizontally by an amount proportional to its depth. Nearer pixels shift more. Uses back-to-front compositing so foreground objects naturally occlude the background. Good for quick results without a depth map.

### Warp
The most stylized mode. Uses backward (inverse) mapping — for each output pixel, it looks up a shifted source pixel. Creates a smooth, liquid distortion rather than a sharp parallax cut. Fun for artistic effects.

## Depth Maps

By default, the tool uses the image's own luminance as a rough depth proxy (bright = near). For much better results, supply a proper depth map:

1. Run [ARAG](https://github.com/Dreamaker-MrC/Any-Resolution-Any-Geometry) or [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) on your image
2. Save the output as a grayscale PNG (must match source dimensions)
3. Upload it via the **Upload Depth Map** button

Convention: **bright = near, dark = far** (check "Invert Depth" if your map is reversed).

## Assets

The `assets/` directory is for the blue noise texture used to improve bokeh quality:

1. Download `LDR_LLL1_0.png` from [free-blue-noise-textures](https://github.com/Calinou/free-blue-noise-textures/tree/master/64_64)
2. Place it in `assets/LDR_LLL1_0.png`

If the file is not found, the tool falls back to white noise (still works, but bokeh edges will look slightly grainier).

## Utilities

- **`npy2gray.py`** — Converts `.npy` depth arrays (e.g. from ARAG) to grayscale PNG images suitable for upload.

## Processing Pipeline

Each frame goes through these stages in order:

1. **Shift** — Parallax, warp, or orbit displacement based on depth
2. **Light wrap** — Background color bleeds onto foreground edges
3. **Bokeh** — Circular disc blur scaled by distance from focus plane
4. **Chromatic aberration** — R/B channel lateral shift
5. **Encode** — Frame added to GIF encoder
