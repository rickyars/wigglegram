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
| **Effect Mode** | Four flavors of 3D motion. See Effect Modes below. | Routes to one of four rendering pipelines. |
| **Baseline** (orbit / ml-sharp) | How much the viewpoint shifts side-to-side. Higher = more dramatic 3D, but edges may tear. 5-8cm mimics real lenticular camera spacing. | Lateral camera translation in cm. Disparity = `f_px * baseline * (1/Z_converge - 1/Z)`. |
| **Parallax Shift** (parallax/warp) | Same idea as baseline but in pixels. Controls how far objects move between frames. | Max per-frame pixel displacement, scaled by normalized depth. |
| **Frames** | More frames = smoother wiggle, bigger file. 8 is a good default. | Number of synthetic viewpoints sampled along a sinusoidal oscillation. |
| **Frame Delay** | Speed of the wiggle. Lower = faster. 60-100ms feels natural. | GIF frame delay in milliseconds. |
| **FOV** (orbit / ml-sharp only) | Wider angle = less depth pop at the same baseline. Narrower = more telephoto compression. | Horizontal field of view in degrees. Sets pinhole focal length as `width / (2 * tan(fov/2))`. |

### Optics

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **Bokeh CoC** | Makes the background go soft and dreamy while the subject stays sharp. 0 = everything sharp. Higher = stronger blur. | Controls both the pre-warp depth blur stack (background blurs proportional to depth) and the per-frame circle-of-confusion disc kernel. |
| **Focus Dist** | Which depth plane stays perfectly sharp. 0 = far background, 1 = nearest foreground, 0.5 = middle. | Normalized depth value of the in-focus plane for the per-frame bokeh pass. |
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
A simpler, punchier effect. Each pixel is shifted horizontally by an amount proportional to its depth. Nearer pixels shift more. Uses back-to-front compositing so foreground objects naturally occlude the background. Occlusion gaps are filled with an edge-aware neighbor search that picks the nearest-depth available pixel, reducing seam smearing. Good for quick results without a depth map.

### Warp
The most stylized mode. Uses backward (inverse) mapping — for each output pixel, it looks up a shifted source pixel. Creates a smooth, liquid distortion rather than a sharp parallax cut. Fun for artistic effects.

### Splat Wiggle
Accepts a `.ply` Gaussian splat file and renders it using `@mkkellogg/gaussian-splats-3d`. The camera oscillates laterally on a sine curve (amplitude controlled by the baseline parameter) to produce the wiggle effect. Use the **Record GIF** button to capture and encode the loop — the existing gif.js pipeline handles encoding.

## Processing Pipeline

Each frame (modes 1–4) goes through these stages in order:

1. **Pre-blur** — Source image blurred per-pixel proportional to depth: background blurs up to `bokehCoc` radius, foreground stays sharp
2. **Shift** — Parallax, warp, or orbit displacement based on depth
3. **Light wrap** — Background color bleeds onto foreground edges
4. **Bokeh** — Circular disc blur scaled by distance from focus plane
5. **Chromatic aberration** — R/B channel lateral shift
6. **Encode** — Frame added to GIF encoder

Mode 5 (Splat Wiggle) uses a WebGL renderer and captures frames directly from the splat canvas.

---

## Producing Depth Maps

By default the tool uses image luminance as a rough depth proxy (bright = near). For much better results, supply a proper depth map — a grayscale PNG where **bright = near, dark = far**.

### Option A: ARAG (Any-Resolution-Any-Geometry)

Highest quality. Chains Depth Anything V2 + Metric3D V2 + a URGT refiner. Requires CUDA 12.4.

**Setup (one time)**

```bash
git clone https://github.com/Dreamaker-MrC/Any-Resolution-Any-Geometry
cd Any-Resolution-Any-Geometry
pip install -r requirements.txt

mkdir -p work_dir/ckpts
huggingface-cli download Kingslanding/Any-Resolution-Any-Geometry \
  ckpt_best.pth ckpt_promask_best.pth --local-dir work_dir/ckpts
```

**Run**

```bash
cd Any-Resolution-Any-Geometry

python tools/infer.py \
    --image /path/to/photo.jpg \
    --checkpoint work_dir/ckpts/ckpt_promask_best.pth \
    --output-dir ./output
```

Use `ckpt_promask_best.pth` for arbitrary photos (zero-shot).

**Convert to grayscale**

ARAG outputs a turbo-colormapped PNG and a raw `.npy`. Convert to grayscale with:

```bash
python npy2gray.py output/photo_depth_pred.npy output/photo_depth_gray.png
```

`npy2gray.py` is in the wigglegram project root. Upload `photo_depth_gray.png` via the depth map button.

| Output file | What it is |
|-------------|------------|
| `photo_depth_pred.png` | Turbo-colormapped depth (for viewing) |
| `photo_depth_pred.npy` | Raw depth array (for processing) |
| `photo_normal_pred.png` | Surface normals |
| `photo_depth_gray.png` | Grayscale depth after conversion (for wigglegram) |

---

### Option B: Depth Anything V2

Simpler, no normals, works on CPU.

**Setup (one time)**

```bash
git clone https://github.com/DepthAnything/Depth-Anything-V2
cd Depth-Anything-V2
pip install -r requirements.txt

mkdir checkpoints
# small (fast, 25M params):
huggingface-cli download depth-anything/Depth-Anything-V2-Small \
  --include "*.pth" --local-dir checkpoints
# OR large (best quality, 335M params):
huggingface-cli download depth-anything/Depth-Anything-V2-Large \
  --include "*.pth" --local-dir checkpoints
```

**Run**

```bash
cd Depth-Anything-V2

python run.py --encoder vits --img-path /path/to/photo.jpg \
  --outdir ./output --pred-only --grayscale
#              ^^^^^ use vitl if you downloaded Large
```

Output is a grayscale PNG in `./output/`. Upload directly. If the wiggle looks inverted, tick **Invert Depth**.

---

### Option C: MiDaS (zero clone, just pip)

No git clone needed — loads from PyTorch Hub. Works on CPU.

**Setup (one time)**

```bash
pip install torch torchvision timm opencv-python
```

**Run** — save as `depth.py` and run:

```python
import cv2, torch, numpy as np, sys
img = cv2.imread(sys.argv[1])
midas = torch.hub.load("intel-isl/MiDaS", "DPT_Large").to(
    "cuda" if torch.cuda.is_available() else "cpu").eval()
transform = torch.hub.load("intel-isl/MiDaS", "transforms").dpt_transform
with torch.no_grad():
    pred = midas(transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).to(
        next(midas.parameters()).device))
    pred = torch.nn.functional.interpolate(
        pred.unsqueeze(1), size=img.shape[:2], mode="bicubic").squeeze().cpu().numpy()
pred = ((pred - pred.min()) / (pred.max() - pred.min()) * 255).astype(np.uint8)
cv2.imwrite("depth.png", pred)
```

```bash
python depth.py /path/to/photo.jpg
```

MiDaS outputs inverse depth (bright = near), matching the wigglegram default convention.

---

## Producing Gaussian Splats (for Splat Wiggle mode)

### Apple ml-sharp

Produces a `.ply` Gaussian splat file from a single image using Apple's monocular reconstruction model.

**Setup (one time)**

```bash
git clone https://github.com/apple/ml-sharp
cd ml-sharp
pip install -e .
```

**Run**

```bash
sharp predict -i your_image.jpg -o output/
```

Output: `output/your_image.ply` — upload this to **Splat Wiggle** mode.

Optional flags:

| Flag | What it does |
|------|-------------|
| `--render` | Also render a trajectory video (CUDA only) |
| `-c path/to/model.pt` | Use a local checkpoint instead of downloading |
| `--device cpu\|mps\|cuda` | Override device selection |

The model downloads automatically on first run (~500MB). For 2D orbit-based wigglegrams (ml-sharp mode), use one of the depth map tools above (ARAG, Depth Anything V2, MiDaS) to produce a grayscale PNG — ml-sharp predict does not export a depth PNG.

---

## Assets

The `assets/` directory is for the blue noise texture used to improve bokeh quality:

1. Download `LDR_LLL1_0.png` from [free-blue-noise-textures](https://github.com/Calinou/free-blue-noise-textures/tree/master/64_64)
2. Place it at `assets/LDR_LLL1_0.png`

If the file is not found, the tool falls back to white noise (bokeh edges will look slightly grainier).

## Utilities

- **`npy2gray.py`** — Converts `.npy` depth arrays (e.g. from ARAG) to grayscale PNG images suitable for upload.
