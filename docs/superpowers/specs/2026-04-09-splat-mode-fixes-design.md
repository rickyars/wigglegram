# Design: Splat Mode Fixes

**Date:** 2026-04-09
**File:** `wigglegram.html` (single-file app)

---

## Problem Summary

Four bugs in splat mode, all observable after loading a `.ply` file:

1. **Depth preview invisible** — the depth pane stays blank after splat loads in depth mode.
2. **Flat side-to-side motion in depth mode** — the wigglegram slides left/right with no parallax depth effect.
3. **Tiny splat in 3D mode** — the rendered splat appears as a small object in a large black canvas.
4. **Jittery GIF in 3D mode** — captured frames flicker/pop between them.

Issues 1–3 share a single root cause. Issue 4 is independent.

---

## Root Causes

### Issues 1–3: Bbox poll exits too early

After `addSplatScene()` resolves, the code polls until `getSplatCount() > 0` before querying the splat scene's bounding box. However, the internal `splatBuffers[0]` structure (required by `getSplatCenter`) is populated slightly later than `getSplatCount`. The poll exits too early, `getSplatCenter` throws, and the camera falls back to looking at `(0, 0, 0)` from `z = 3` regardless of where the actual scene is.

Consequences:
- **Issue 2**: Camera at wrong position → baked depth map is flat (all pixels at same depth) → no parallax differential → pure lateral slide.
- **Issue 3**: 3D mode orbits the wrong center → scene appears at edge of canvas or as a tiny dot.
- **Issue 1**: When depth mode is active, the GL canvas is visible and `depthCanvas` is hidden. `renderToPane` draws to the hidden canvas. Canvas visibility is never swapped when toggling between modes.

### Issue 4: Splat sort not settled at GIF capture time

GS3D sorts splats back-to-front in a web worker. `captureFrame` (3D mode) calls `viewer.update() → viewer.render()` synchronously after repositioning the camera. The sort worker hasn't finished for the new angle yet, so consecutive frames have inconsistent splat ordering → visible popping between frames.

---

## Changes

### 1. Extend bbox poll condition (`SplatDepthSource.load`)

**Current:**
```js
while (splatMesh.getSplatCount() === 0 && pollMs < 5000) {
```

**New:**
```js
while ((splatMesh.getSplatCount() === 0 || !splatMesh.splatBuffers?.[0]) && pollMs < 5000) {
```

No other changes to the bbox logic. Once `splatBuffers[0]` is present, `getSplatCenter` succeeds and produces a real scene center, enabling correct `_autoFitDist` and camera position.

### 2. Swap canvas visibility on mode change

When switching to **depth mode**:
- Show `_originalCanvas` (depthCanvas)
- Hide `_glCanvas`
- Draw bakedDepth to depthCanvas via `renderToPane`

When switching to **3D mode**:
- Hide `_originalCanvas`
- Show `_glCanvas`

This swap happens in two places:
- `SplatDepthSource.setMode(mode)` — internal state change
- `setSplatMode(mode)` — already calls `setMode` and `renderToPane`, just needs the visibility swap added

After load completes (at the end of `SplatDepthSource.load`), also swap: hide `_glCanvas`, show `_originalCanvas`, then call `renderToPane`.

### 3. Settle sort before GIF frame capture (`captureFrame`, 3D branch)

After `positionCamera` and before reading pixels, yield to the event loop with a short delay to let the sort worker complete:

```js
this.positionCamera(mode, angle, params);
// Let sort worker settle
for (let i = 0; i < 3; i++) {
  this.viewer.update();
  await new Promise(r => requestAnimationFrame(r));
}
this.viewer.render();
// ... read pixels as before
```

Three rAF ticks is sufficient for the sort to complete at typical splat sizes. The extra time per frame is negligible compared to pixel readback.

---

## What Is Not Changing

- The depth extraction shader, `_bakeDepth`, `scaleBakedDepth`, and `renderToPane` logic are unchanged.
- All motion modes (orbit, parallax, warp) and all effects (bokeh, light wrap, chromatic aberration) are unchanged.
- Non-splat depth sources (`LuminanceDepthSource`, `ImageDepthSource`) are unaffected.
- The GIF pipeline (`runPipeline`) is unchanged except that `captureFrame` now settles before capture in 3D mode.
- All code changes go through Codex CLI.
