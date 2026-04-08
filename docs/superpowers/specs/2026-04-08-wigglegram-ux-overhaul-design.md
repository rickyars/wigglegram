# Wigglegram UX Overhaul — Design Spec
**Date:** 2026-04-08
**Status:** Approved

---

## Goal

Clean up the app and produce a realistic wigglegram effect. The core problem is that the current UI has two parallel workflows (depth-map and splat) that diverge in confusing ways — modes don't apply consistently, optics sliders do nothing in splat mode, and there is no way to preview the effect without generating a full GIF.

---

## Architecture

### Two abstractions

**DepthSource** — anything that provides color and depth information for frame generation. Three concrete types:

- `LuminanceDepthSource` — derives depth from the luminance of the source image (default, no upload required)
- `ImageDepthSource` — uses an uploaded grayscale depth map image
- `SplatDepthSource` — holds a loaded `.ply` Gaussian splat scene; renders via Three.js / `@mkkellogg/gaussian-splats-3d`; provides a color render and a depth buffer from any camera position

Each depth source implements:
- `renderToPane(canvas)` — draws itself into the depth pane (grayscale for depth maps, live color render for splat)
- `captureFrame(frameIndex, totalFrames, mode, params) → { colorImageData, depthArray }` — produces inputs for one GIF frame. For depth-map sources, the pixel-displacement algorithm (orbit/parallax/warp) is applied inside this call and `colorImageData` is the already-displaced result. For splat, `colorImageData` is the WebGL color render from the repositioned camera. In both cases `depthArray` is the per-pixel depth used by the post-processing chain.

**FrameRenderer** — the CPU pixel-displacement pipeline (orbit / parallax / warp algorithms). Isolated behind `captureFrame` so it can be swapped for a WebGL shader renderer in a future pass without touching any other code.

### Why splat is a depth source, not a mode

The splat is a means of obtaining high-quality per-frame color and depth, not a motion style. For each frame, the splat camera is positioned according to the active mode, rendered, and the resulting color + depth buffer are fed into the same post-processing chain as depth-map paths. All optics sliders apply equally to splat and depth-map outputs.

---

## Motion Modes

Three modes, applied consistently regardless of depth source:

| Mode | Depth-map path | Splat path |
|---|---|---|
| **orbit** | Perspective camera arc (existing `generateFrameOrbit`) | Camera sweeps horizontal arc, always looking at scene center |
| **parallax** | Forward pixel displacement by depth (existing `generateFrameParallax`) | Camera translates purely left-right, no rotation |
| **warp** | Pull-based inverse warp (existing `generateFrameWarp`) | Camera yaw-rotates in place, position fixed |

The `splat wiggle` entry is removed from the mode dropdown — it was a depth source, not a motion style.

---

## Frame Generation Pipeline

Both "Generate Preview" and "Generate GIF" use the same pipeline at different resolutions:

1. Determine active depth source
2. Scale source image to target width (400px for preview, `outputWidth` for GIF)
3. For each frame `i`:
   a. Call `depthSource.captureFrame(i, totalFrames, mode, params)` → `{ colorImageData, depthArray }`
   b. Apply post-processing chain: bokeh blur stack → light wrap → circular disc bokeh → chromatic aberration
   c. Add processed frame to gif.js encoder
4. On encode complete: display in output panel

For `SplatDepthSource`, step 3a positions the Three.js camera according to the mode trajectory, renders color + reads depth buffer from the WebGL renderer.

---

## UI Layout

### Left panel

**Top — two input panes (visible after image load):**
- Left pane: source image (unchanged)
- Right pane: active depth source
  - Depth map path: grayscale depth canvas (as today)
  - Splat path: live color render of splat, continuously oscillating so the wigglegram effect is visible in real-time
  - Pane label updates: "depth (luminance)" / "depth (custom: filename.png)" / "splat (live)"

**Bottom — output area:**
- Animated GIF preview appears here after Generate Preview or Generate GIF
- Small label shows resolution and frame count

### Right panel (controls)

**Uploads:**
- Source image upload (unchanged)
- Depth source upload: one button, accepts `.png`/`.jpg` depth maps OR `.ply` splat files. Loading either replaces the other. A `[clear]` link resets to luminance proxy.

**Tweakpane — Motion folder:**
- Mode: orbit / parallax / warp
- Baseline (relabeled per mode: "baseline", "parallax shift", "amplitude (°)")
- Frames
- Frame delay (ms)
- FOV (orbit only)

**Tweakpane — Optics folder:**
- Bokeh CoC
- Focus dist
- Light wrap
- Chromatic aberr

**Tweakpane — Output folder:**
- Output width
- Invert depth

**Actions (bottom of right panel):**
- **Generate Preview** — primary button; renders at 400px wide
- **Generate GIF** — secondary button; renders at `outputWidth`; enabled after a preview has been generated

Sliders do not trigger re-renders. Only button presses render output.

---

## Future: WebGL Renderer (Option B)

When migrating to a WebGL shader renderer:
- Replace `FrameRenderer.captureFrame()` for non-splat sources only
- The gif assembly loop, post-processing chain, and UI are untouched
- `SplatDepthSource.captureFrame()` is already GPU-accelerated and does not change
- The abstraction boundary is exactly `captureFrame(i, n, mode, params) → { colorImageData, depthArray }`

---

## Out of Scope

- Mobile / responsive layout changes
- New motion modes beyond orbit / parallax / warp
- WebGL post-processing (bokeh, CA remain CPU-side for now)
- Multi-image input (lenticular from multiple photos)
