# Design: Splat Dual-Mode (Depth Extract + 3D Render)

**Date:** 2026-04-09
**File:** `wigglegram.html` (single-file app)

---

## Problem Summary

Three compounding issues make splat mode unreliable:

1. **Bbox timing** — GS3D's `splatBuffer` isn't populated when we query bounds immediately after `addSplatScene()` resolves. We always fall back to `autoFitDist = 3.0`, so zoom is always wrong.
2. **Parallax scale** — the parallax camera shift uses a fixed world-unit multiplier (`baseline * 0.05`) with no awareness of scene scale, causing wild oscillation.
3. **No depth-extract path** — splat always renders live 3D, bypassing all effects (bokeh, blur, chromatic aberration). Users expect these to work.

---

## Solution: Dual-Mode SplatDepthSource

`SplatDepthSource` gains a `mode` property (`'depth'` | `'3d'`). On load it always bakes a depth map so depth mode is immediately available. The user can toggle between modes via two buttons in the depth pane label.

---

## SplatDepthSource Changes

### New properties

```js
this.mode = 'depth';           // 'depth' | '3d'
this.bakedDepth = null;        // Float32Array, normalized 0-1, length = w*h
this.bakedWidth = 0;
this.bakedHeight = 0;
```

### Bbox timing fix

After `await viewer.addSplatScene(...)`, call `viewer.update()` once before querying the splat mesh bounds. This flushes the worker pipeline and populates `splatBuffer`.

```js
await viewer.addSplatScene(blobUrl, { ... });
viewer.update();               // ← add this line
const splatMesh = viewer.getSplatMesh();
// ... existing bbox logic unchanged
```

### Auto-bake depth on load

After camera is positioned (existing auto-fit logic), render one frame to `depthReadTarget` and read it back:

```js
async _bakeDepth(THREE) {
  const w = this.renderer.domElement.width;
  const h = this.renderer.domElement.height;

  this.renderer.setRenderTarget(this.depthTarget);
  this.viewer.update();
  this.viewer.render();
  this.renderer.setRenderTarget(null);

  const quadGeo = new THREE.PlaneGeometry(2, 2);
  const quadMesh = new THREE.Mesh(quadGeo, this.depthMaterial);
  const depthScene = new THREE.Scene();
  depthScene.add(quadMesh);
  const orthoCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1, 1);

  this.renderer.setRenderTarget(this.depthReadTarget);
  this.renderer.render(depthScene, orthoCamera);
  this.renderer.setRenderTarget(null);
  quadGeo.dispose();

  const raw = new Float32Array(w * h * 4);
  this.renderer.readRenderTargetPixels(this.depthReadTarget, 0, 0, w, h, raw);

  // Extract red channel, flip vertically, invert (near=1, far=0)
  const depth = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const srcRow = (h - 1 - y) * w;
    const dstRow = y * w;
    for (let x = 0; x < w; x++) {
      depth[dstRow + x] = 1.0 - raw[(srcRow + x) * 4];
    }
  }

  this.bakedDepth = depth;
  this.bakedWidth = w;
  this.bakedHeight = h;
}
```

Called at the end of `load()`, before `setStatus('splat loaded')`.

### `setMode(mode)`

```js
setMode(mode) {
  this.mode = mode;
  if (mode === '3d') {
    this.startOscillation(this._lastMode, this._lastParams);
  } else {
    this.stopOscillation();
  }
}
```

### `renderToPane(canvas)`

- **Depth mode**: draw `bakedDepth` as a grayscale image onto `canvas`
- **3D mode**: no-op (live render already running via rAF) — current behavior

### `captureFrame()` — depth mode branch

In depth mode, behave like `ImageDepthSource`: use `scaledSrc` (original photo) and a scaled version of `bakedDepth` as the depth map. Apply the same pixel-shift algorithms (`generateFrameOrbit`, `generateFrameParallax`, `generateFrameWarp`).

```js
if (this.mode === 'depth') {
  // Scale bakedDepth to match scaledSrc dimensions
  const scaledDepth = scaleBakedDepth(
    this.bakedDepth, this.bakedWidth, this.bakedHeight,
    scaledSrc.width, scaledSrc.height
  );
  const xOffset = params.baseline * Math.sin(angle);
  let colorData;
  if (mode === 'orbit') {
    colorData = generateFrameOrbit(scaledSrc.data, scaledDepth, xOffset, scaledSrc.width, scaledSrc.height);
  } else if (mode === 'parallax') {
    colorData = generateFrameParallax(scaledSrc.data, scaledDepth, xOffset, scaledSrc.width, scaledSrc.height);
  } else {
    colorData = generateFrameWarp(scaledSrc.data, scaledDepth, xOffset, scaledSrc.width, scaledSrc.height);
  }
  return { colorData, depthArray: scaledDepth, width: scaledSrc.width, height: scaledSrc.height };
}
```

`scaleBakedDepth` bilinearly (or nearest-neighbour) resamples the `bakedDepth` Float32Array to the target dimensions using a temporary canvas.

### `captureFrame()` — 3D mode branch

Unchanged from current implementation.

### Parallax fix in `positionCamera()` (3D mode)

Change the parallax camera shift from a fixed world-unit formula to one proportional to `_autoFitDist`:

```js
// Before:
this.camera.position.x = this.basePos.x + Math.sin(angle) * params.baseline * 0.05;

// After:
const shift = (this._autoFitDist || 3.0) * (params.baseline / 100);
this.camera.position.x = this.basePos.x + Math.sin(angle) * shift;
```

`baseline = 10` now means "shift camera by 10% of auto-fit distance." This is scene-scale-independent.

---

## Pipeline Changes (`runPipeline`)

Change the `isSplat` check to `isSplat3D`:

```js
const isSplat3D = activeDepthSource instanceof SplatDepthSource && activeDepthSource.mode === '3d';
```

Replace all `isSplat` references with `isSplat3D`. In depth mode, the splat is treated identically to `ImageDepthSource` — the pipeline scales `srcImageData`, computes depth from `activeDepthSource` (which now returns the baked depth via `captureFrame`), and applies all effects.

---

## UX Changes

### Depth pane label toggle

When a splat is loaded, the depth pane label changes to show two toggle buttons:

```
splat (depth)  [depth] [3D]
```

The active mode button is highlighted (green text). Clicking the inactive button calls `activeDepthSource.setMode(newMode)` and:
- Updates button highlight state
- Calls `activeDepthSource.renderToPane(depthCanvas)` to refresh the pane
- Adds or removes the zoom Tweakpane binding

When no splat is loaded (or a different depth source is active), the toggle buttons are not shown.

### Zoom slider visibility

The `splatZoom` Tweakpane binding is dynamically added when mode switches to `'3d'` and removed when mode switches to `'depth'`. It is also removed when any non-splat depth source is loaded.

A helper function manages this:

```js
let splatZoomBinding = null;

function showSplatZoom() {
  if (splatZoomBinding) return;
  splatZoomBinding = motionFolder.addBinding(PARAMS, 'splatZoom', {
    label: 'zoom', min: 0.1, max: 3.0, step: 0.05,
  }).on('change', (ev) => {
    if (activeDepthSource instanceof SplatDepthSource) {
      activeDepthSource.repositionCamera(ev.value);
    }
  });
}

function hideSplatZoom() {
  if (!splatZoomBinding) return;
  splatZoomBinding.dispose();
  splatZoomBinding = null;
}
```

---

## `scaleBakedDepth` Helper

Resamples a `Float32Array` depth map to new dimensions using a temporary canvas (nearest-neighbour via ImageData round-trip):

```js
function scaleBakedDepth(depth, srcW, srcH, dstW, dstH) {
  const src = document.createElement('canvas');
  src.width = srcW; src.height = srcH;
  const sCtx = src.getContext('2d');
  const imgData = sCtx.createImageData(srcW, srcH);
  for (let i = 0; i < depth.length; i++) {
    const v = Math.round(depth[i] * 255);
    imgData.data[i * 4] = v;
    imgData.data[i * 4 + 1] = v;
    imgData.data[i * 4 + 2] = v;
    imgData.data[i * 4 + 3] = 255;
  }
  sCtx.putImageData(imgData, 0, 0);

  const dst = document.createElement('canvas');
  dst.width = dstW; dst.height = dstH;
  dst.getContext('2d').drawImage(src, 0, 0, dstW, dstH);
  const scaled = dst.getContext('2d').getImageData(0, 0, dstW, dstH);

  const out = new Float32Array(dstW * dstH);
  for (let i = 0; i < out.length; i++) {
    out[i] = scaled.data[i * 4] / 255;
  }
  return out;
}
```

---

## What Is Not Changing

- All three motion modes (orbit, parallax, warp) work in both splat modes
- All effects (bokeh, light wrap, chromatic aberration) apply in both modes
- Non-splat depth sources are unaffected
- The download button fix and previous auto-fit work remain as-is
- All code changes go through Codex CLI (Claude orchestrates)
