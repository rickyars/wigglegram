# Splat UX Fixes Design

**Date:** 2026-04-15  
**Status:** Approved (amended: added Y offset)

## Overview

Three categories of fixes to how splat (.ply) files work in wigglegram.html:

1. Splat always shows as 3D — no depth map
2. Tweakpane reorganized into context-sensitive sections
3. Better motion controls: direct swing angle in degrees, manual X offset for centering

---

## Section 1: Splat Load Behavior

### What changes

- `SplatDepthSource` drops all depth baking: remove `_bakeDepth()`, `bakedDepth`, `bakedWidth`, `bakedHeight`, `depthTarget`, `depthReadTarget`, `depthMaterial`, and the `mode` field
- `load()` ends by starting the live 3D view directly — no mode switching, no canvas swap-back
- The `[depth]` / `[3D]` toggle in the depth pane label becomes a **read-only indicator**:
  - Depth map loaded → `[depth]` active, `[3D]` grayed and non-clickable
  - Splat loaded → `[3D]` active, `[depth]` grayed and non-clickable
  - Nothing loaded → toggle hidden
- `setSplatMode()` and related mode-switching logic is removed

### Why

Splat files carry their own 3D geometry — baking a 2D depth map from them was wasted work that also forced the user to manually click `[3D]` every time. Removing depth mode from splats simplifies the class significantly.

---

## Section 2: Tweakpane Reorganization

Five folders replace the current Motion / Optics / Output layout. Visibility is driven by what is currently loaded.

### Motion (always visible)
- `motion amount` — single binding, relabeled and range-adjusted by context:
  - Depth orbit: label "baseline", range 1–15, default 6.5
  - Depth parallax: label "parallax shift", range 3–60
  - Depth warp: label "amplitude °", range 1–15, default 3
  - Splat: label "swing angle °", range 1–20, default 5
- `fov` — always visible, range 20–80
- `frames` — always visible
- `frame delay` — always visible

### Depth map (visible only when a depth map is loaded)
- `effect mode` — orbit / parallax / warp selector
- `invert depth` — toggle

### Splat (visible only when a splat is loaded)
- `zoom` — camera distance multiplier, range 0.1–3.0, step 0.05
- `X offset` — horizontal shift of the look-at point, range -2.0–2.0, step 0.05, default 0
- `Y offset` — vertical shift of the look-at point, range -2.0–2.0, step 0.05, default 0

### Optics (always visible)
- `bokeh coc`, `focus dist`, `light wrap`, `chromatic aberr`

### Output (always visible)
- `output width`

### Implementation notes

- Tweakpane folders support `.hidden` toggling. Each of the two conditional folders (Depth map, Splat) has its visibility set when a file is loaded or cleared.
- The Motion folder's `motion amount` binding is disposed and recreated on context change (consistent with existing pattern for baseline relabeling).
- `PARAMS.baseline` is reused as the backing value for all motion amount contexts. When switching to splat mode, save the current depth baseline and restore it on switch back, so the user's depth settings are preserved.
- The `[depth]` / `[3D]` toggle buttons: when non-functional, add a CSS class (e.g. `disabled`) that sets `pointer-events: none; opacity: 0.35`. The active button keeps its green color.

---

## Section 3: Swing Angle Formula

### What changes

The oscillation angle for splat 3D mode changes from the indirect formula:

```
angle = baseline × tan(fov/2) / (canvas_width/2)
```

to a direct conversion:

```
angle = swingAngle × π/180
```

This applies in both `startOscillation()` (live preview) and `captureFrame()` (GIF export).

### Why

The old formula tied the angle to both `baseline` (in pixels) and `fov`, making the actual swing unpredictable. The new formula means "swing angle °" slider at 5° swings exactly 5° left and right — no hidden interactions.

---

## Section 4: Centering Fix (X Offset)

### What changes

Add `PARAMS.splatOffsetX = 0` and `PARAMS.splatOffsetY = 0` to the global params object.

In `repositionCamera()` and `positionCamera()`, shift the look-at point (not the camera position) by the offsets:

```js
const lookX = center.x + PARAMS.splatOffsetX;
const lookY = center.y + PARAMS.splatOffsetY;
camera.lookAt(lookX, lookY, center.z);
// camera.position is set by the orbiting math, unchanged
```

Both offset sliders call `repositionCamera()` on change (same pattern as zoom) so the live preview updates immediately.

The X offset slider in the Splat folder drives this value. Changing it during live preview immediately repositions the camera.

### Why

Automatic centering from the splat bbox can be off depending on the scene's COLMAP reconstruction. A manual offset lets the user correct it without needing to re-export the splat.

---

## Parameters Reference (after changes)

| Parameter | Section | Applies when |
|---|---|---|
| motion amount | Motion | always (label/range changes) |
| fov | Motion | always |
| frames | Motion | always |
| frame delay | Motion | always |
| effect mode | Depth map | depth map loaded |
| invert depth | Depth map | depth map loaded |
| zoom | Splat | splat loaded |
| X offset | Splat | splat loaded |
| Y offset | Splat | splat loaded |
| bokeh coc | Optics | always |
| focus dist | Optics | always |
| light wrap | Optics | always |
| chromatic aberr | Optics | always |
| output width | Output | always |
