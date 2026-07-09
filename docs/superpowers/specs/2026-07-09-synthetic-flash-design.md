# Synthetic Flash — Design

## Goal

Wigglegrams often look best with harsh, direct on-camera flash lighting that
exaggerates 3D depth through falloff (near = bright, far = dark). Add a
"Flash" effect that simulates this using the depth data already available
from the splat scene, applied live in the preview and carried through to
GIF/MP4 export.

## Approach

Depth-aware falloff + vignette, computed as a screen-space post-process pass,
applied every render frame (not baked once).

Rejected alternatives:
- **Directional relighting with estimated normals** — more dramatic but
  requires deriving usable normals from noisy monocular depth; too fragile
  for a v1.
- **Uniform stylistic filter (vignette + contrast, depth-blind)** — cheapest,
  but ignores the depth data the app already has, so it wouldn't produce the
  "near lit / far falls to black" look that's the actual goal.

## Architecture

1. Change the splat render target from directly-to-canvas to an offscreen
   `THREE.WebGLRenderTarget` with a `depthTexture` attached.
2. Add a fullscreen composite shader pass that runs after the splat render
   each frame:
   - Samples the color and depth textures.
   - Computes per-pixel flash falloff from linearized depth (near bright,
     far dark, inverse-square-ish curve).
   - Applies an additional radial vignette/hotspot centered at the flash
     origin (on-camera, i.e. screen center by default).
   - Writes the composited result to the visible canvas.
3. This pass re-runs every frame of the existing render loop — it does not
   introduce a new loop. It's live while the wiggle preview is
   playing/animating, and runs once per frame during GIF/MP4 export. It does
   not run when the app is idle (matches current renderer behavior).

## Controls

New "Flash" Tweakpane folder, following the existing pattern (Motion / Depth
map / Splat / Optics / Output):
- **Enable** toggle (off by default, opt-in per photo)
- **Intensity** slider
- **Falloff range** slider (distance over which brightness drops off)
- **Warmth** slider (color temperature tint, since real flashes often read
  slightly cool/blue-white)

Flash origin position is fixed at the virtual camera (on-camera flash
assumption) for v1 — no separate XY offset control.

## Performance

Fullscreen post-process cost scales with canvas resolution, not splat count;
expected to be a small addition on top of existing splat rasterization cost,
which is the dominant per-frame cost already. Render-target/depth-texture
setup is a one-time allocation (recreated only on resize). No expected
noticeable impact on interactive preview framerate; export cost scales
linearly with resolution × frame count as it already does today.

## Out of scope (v1)

- Directional/shadow-casting relighting from estimated surface normals.
- Adjustable flash position independent of camera.
- Multiple/colored flash sources.
