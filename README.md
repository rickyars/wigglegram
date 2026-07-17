# wiggle gram

A browser-based tool that turns a single photo into a wigglegram GIF — those wobbly, eye-catching 3D animations you see on social media and in lenticular prints.

## What is a wigglegram?

A wigglegram (or "wiggle stereoscopy") is an animated GIF that rapidly alternates between slightly different viewpoints of the same scene, creating a convincing illusion of depth on a flat screen. Traditional wigglegrams require multiple photos taken from different positions. This tool synthesizes all those viewpoints from a **single image** using a depth map.

## Quick Start

1. Open `wigglegram.html` in any modern browser (Chrome, Firefox, Edge, Safari)
2. Click **Upload Source Image** and pick a photo
3. Click **Generate Depth**: if the companion server is running (see below) it uses **Depth Anything 3** on your GPU (best quality, ~2s); otherwise it falls back to **Depth Anything V2 Small** in your browser (~25MB model downloads once, then is cached). Depth no longer runs automatically on upload, and the old luminance-as-depth placeholder is gone — until a depth source exists, the generate button stays disabled.
4. (Optional) Click **Upload Depth Source** to supply your own grayscale depth map or a `.ply` gaussian splat instead — or use the companion server for one-click splats (see [Gaussian splats](#gaussian-splats-best-quality) below)
5. Adjust parameters in the right-hand panel — the **live preview** loops the wiggle as you tune, no encoding needed
6. Pick an output **format** (gif, or video — mp4/webm, typically ~10× smaller) and click **Generate**
7. Preview the result, then click **Download** to save

Note: video export records in real time; keep the tab visible while it encodes or the timing will stretch.

No server, no install — everything runs in your browser. (AI depth uses WebGPU when available, WASM otherwise.)

## Companion server (best quality depth + splats)

The companion server runs the big models on your GPU and gives the app two upgrades:

- **Depth Anything 3** depth maps, used automatically on image upload (much better than the in-browser model) — you'll see `depth (DA3)` in the depth pane
- A **Generate Splat (ml-sharp)** button for one-click gaussian splats — the best wiggle quality of all

### Starting the companion server

1. Open a terminal in this project folder
2. Activate the Python environment that has ml-sharp installed. On this machine that's the `comfyui` conda env:

   ```
   conda activate comfyui
   ```

3. Start the server:

   ```
   python wigglegram-companion.py
   ```

4. Wait for `Model ready. Listening on http://127.0.0.1:8765` (the very first start downloads the ~2.6GB SHARP checkpoint; after that it starts in seconds)
5. Open (or reload) `wigglegram.html` — a **Generate Splat (ml-sharp)** button now appears under the upload buttons
6. Load a photo, click the button, wait ~10-60 seconds — the splat loads automatically

Leave the terminal running while you use the app; the model stays warm so repeat generations are fast. Close it with Ctrl+C when you're done. If the button doesn't appear, the server isn't running (or wasn't up when the page loaded — reload the page).

**First-time setup on a new machine** (already done on this one):

```
pip install --no-deps -e ./ml-sharp
pip install --no-deps -e ./Depth-Anything-3
pip install plyfile pillow-heif "moviepy<2" pycolmap trimesh evo typer
```

The SHARP checkpoint (~2.6GB) downloads on first companion start; the DA3 model (~1.4GB) downloads on the first depth request. Both are cached afterwards.

**Manual alternative:** run `sharp predict -i your_image.jpg -o output/` and upload the resulting `.ply` via the Depth Source button.

ml-sharp PLYs embed the source camera pose; the app uses it to center the wiggle on the photo's optical axis, so at zoom 1.0 the framing matches your photo exactly.

## Relighting (shadows & reflections fix)

Baked-in shadows and specular reflections break the wiggle illusion: the depth
map assigns those pixels to the surface they appear on, so they move rigidly
with the surface instead of behaving like light. The Relight system fixes this
by removing the photo's lighting and re-adding synthetic lighting whose
direction is driven by the same view offset that drives the camera — lighting
and parallax are synced by construction.

### How it works

```
photo ──► companion /intrinsic ──► albedo (shading-free colors) + specular map
                                   + surface normal map (Marigold-Normals)
photo ──► Generate Depth        ──► depth (parallax/warp geometry only)
each frame t ∈ [-1,1]:  camera offset = f(t)   AND   light azimuth = offset + swing·t
                        frame = blend(photo, albedo) × shading(normals, light) + specular glint
```

The decomposition uses **Marigold-IID (Lighting)** (`prs-eth/
marigold-iid-lighting-v1-1`, CreativeML OpenRAIL++-M license) via the
diffusers pipeline: it splits a photo as `I = Albedo × Shading + Residual`,
which maps exactly onto this pipeline — the albedo feeds the relit render,
the non-diffuse residual is the specular map, and the shading is discarded
(the shader synthesizes new shading). ~0.7s warm per photo at 768px; the
~2GB weights auto-download on first use. Albedo gets high-frequency detail
re-injected from the original photo (multiplicative `orig / blur(orig)`
transfer), since the diffusion itself works at 768px.

Shading normals come from **Marigold-Normals** (`prs-eth/marigold-normals-v1-1`,
same license/pipeline family, ~2GB, runs in the same Decompose click): a
predicted per-pixel surface normal map with real orientation detail (noses,
fabric folds, hair). The earlier approach — normals from depth-map gradients —
terraced on 8-bit depth quantization ("tiered cake" contours) and only knew
coarse geometry, so shading flattened all surface detail. Depth-gradient
normals remain only as a fallback when no decomposition has been run.

(History: the first backend was IntrinsicAnything (ECCV 2024) — scene-level
but 256px, minutes per map, 30GB of weights, and its best-quality
competitor (Careaga & Aksoy) is academic-license-only. Marigold replaced it
wholesale; the vendored `IntrinsicAnythingSpace/` folder has been deleted.)

### Using it

1. Start the companion server
2. Load a photo, click **Generate Depth**, then **Decompose Lighting (Marigold)** (~10s warm, first click loads models)
3. The **Relight** folder unlocks in the panel, enabled by default — tune in the live preview. In splat mode, regenerate the splat afterwards so it's built from the albedo.

### Relight parameters

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **light swing °** | How much the light direction sweeps during the wiggle. 0 = static light. | Azimuth range: `az = offset + swing · t`, t is the view offset in [-1,1]. |
| **light offset °** | Where the light sits at center frame. | Constant azimuth term. |
| **light elevation °** | Light height: positive = from above. | Elevation angle of the light vector. |
| **ambient** | Shadow depth floor — higher = flatter, softer lighting. | Constant term in `shade = ambient + (1-ambient)·max(n·l, 0)`. |
| **relief** | How strongly surfaces respond to the light angle. | Gain on the predicted normal's x/y before renormalizing (default 3 = neutral); for the depth-gradient fallback, scale on the gradients. |
| **specular** / **shininess** | Glint strength and tightness on shiny surfaces. | Blinn-Phong term masked by the Marigold specular (residual) map. |
| **albedo blend** | 0 = original photo (original shadows kept), 1 = full albedo (shadows fully removed). ~0.8 keeps some photographic texture. | Linear mix of source and albedo before shading. |

Relight and Flash **stack** in both 2D and splat modes: relight shapes the
surfaces per-frame, then the flash blowout/vignette applies on top like a
real strobe.

### Companion setup for relighting

Nothing beyond the base companion setup — Marigold ships inside `diffusers`
(already required) and its ~2GB fp16 checkpoint auto-downloads from the HF
hub on the first Decompose. `/health` reports `"intrinsic": true` when
diffusers ≥ 0.34 is present.

The endpoint is `POST /intrinsic` (query param `?hq=1` for 10 steps + an
ensemble of 3 instead of the default 4 steps), returning
`{"albedo", "specular", "shading", "normals"}` as base64 PNGs (normals
encoded `rgb = (n+1)/2`, camera frame, X right / Y up / Z toward camera).
The VRAM used by both pipelines is released after each request so the
browser's WebGL splat viewer has room. ~1-2s warm total at 2048×1536.

### Current limitations

- **Splat-mode normals are screen-aligned** — the normal map is sampled in
  screen space like the specular map, which is approximately correct for the
  small camera swings a wigglegram uses but ignores parallax within the map.
- **Mirror-content reflections are not fixed** — intrinsic decomposition removes
  specular sheen and shading, but a scene reflected in a mirror/window is
  content, not shading. That needs a layered renderer with mirrored depth
  (future milestone).
- The first Decompose click after companion start loads both diffusion models
  (~30s extra).

## Parameters Reference

### Motion

| Parameter | What you'll see | Technical |
|-----------|----------------|-----------|
| **Effect Mode** | Four flavors of 3D motion. See Effect Modes below. | Routes to one of four rendering pipelines. |
| **Baseline** (orbit / ml-sharp) | How much the viewpoint shifts side-to-side. Higher = more dramatic 3D, but edges may tear. 5-8cm mimics real lenticular camera spacing. | Lateral camera translation in cm. Disparity = `f_px * baseline * (1/Z_converge - 1/Z)`. |
| **Parallax Shift** (parallax/warp) | Same idea as baseline but in pixels. Controls how far objects move between frames. | Max per-frame pixel displacement, scaled by normalized depth. |
| **Views** | Number of distinct viewpoints (2-8). Classic wigglegrams use 2-4. Played ping-pong (1-2-3-2-...) for a seamless loop. | Viewpoints evenly spaced across the baseline; the output contains 2×views−2 frames. |
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

The tool needs a proper depth map — a grayscale PNG where **bright = near, dark = far** — either generated in-app (Generate Depth) or supplied via the Depth Source button.

### Depth Anything V2

Follow the setup and usage instructions in the [Depth Anything V2 repo](https://github.com/DepthAnything/Depth-Anything-V2). Run with `--pred-only --grayscale` to get a grayscale PNG ready to upload. If the wiggle looks inverted, tick **Invert Depth**.

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
