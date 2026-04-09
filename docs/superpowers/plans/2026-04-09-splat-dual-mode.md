# Splat Dual-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `SplatDepthSource` two modes — depth-extract (bakes a depth map from the splat, uses original photo + all effects) and 3D-render (live WebGL, existing behavior) — with a toggle in the depth pane label, a dynamic zoom slider, and fixes for bbox timing and parallax scale.

**Architecture:** `SplatDepthSource` gains a `mode` property (`'depth'`|`'3d'`), new constructor properties, a `_bakeDepth()` async method, and a `setMode()` method. The pipeline replaces the single `isSplat` boolean with `isSplat3D`/`isSplatDepth` checks. A new `scaleBakedDepth` helper resamples the baked Float32Array to pipeline dimensions. The zoom Tweakpane binding is moved from static setup to dynamic show/hide helpers.

**Tech Stack:** Vanilla HTML/CSS/JS, THREE.js (dynamic import), @mkkellogg/gaussian-splats-3d (dynamic import), Tweakpane v4

**CRITICAL:** All code edits go through Codex CLI. Run: `cd C:\Users\ricky\art\wigglegram && codex --approval-mode full-auto -q "PROMPT"`. If Codex sandbox blocks file writes, use the Edit tool as a fallback.

---

## File Map

All changes in `wigglegram.html`:
- ~line 575: add `scaleBakedDepth` helper before class definitions
- ~line 691–706: `SplatDepthSource` constructor — add new properties
- after constructor (~line 710): add `_bakeDepth(THREE)` and `setMode(mode)` methods
- ~line 800: `load()` — add `viewer.update()` timing fix + call `_bakeDepth` + set `mode = 'depth'`
- ~line 897: `renderToPane()` — add depth mode branch
- ~line 960: `captureFrame()` — add depth mode branch at top
- ~line 931: `positionCamera()` parallax line — fix scale formula
- ~line 1626: `runPipeline` — replace `isSplat` with `isSplat3D`/`isSplatDepth`
- ~line 1657: depth computation block — add splat-depth case
- ~line 131 (CSS): add `.splat-mode-toggle` and `.splat-mode-btn` rules
- ~line 314 (HTML): add toggle buttons inside depth pane label
- ~line 489 (Tweakpane setup): remove static `splatZoom` binding
- after `updateModeUI`: add `showSplatZoom` / `hideSplatZoom` helpers
- splat load handler (~line 1040): call `hideSplatZoom()` and show toggle buttons

---

## Task 1: `scaleBakedDepth` Helper

**Files:**
- Modify: `wigglegram.html` (before `class LuminanceDepthSource`, ~line 576)

- [ ] **Step 1: Run Codex to add the helper**

  Prompt:
  ```
  In wigglegram.html, immediately before the line `class LuminanceDepthSource {`, add this function:

    function scaleBakedDepth(depth, srcW, srcH, dstW, dstH) {
      const src = document.createElement('canvas');
      src.width = srcW; src.height = srcH;
      const sCtx = src.getContext('2d');
      const imgData = sCtx.createImageData(srcW, srcH);
      for (let i = 0; i < depth.length; i++) {
        const v = Math.round(depth[i] * 255);
        imgData.data[i * 4]     = v;
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

  Do not change anything else.
  ```

- [ ] **Step 2: Verify**

  Read that section of wigglegram.html and confirm `scaleBakedDepth` appears immediately before `class LuminanceDepthSource`.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: add scaleBakedDepth helper for splat depth resampling"
  ```

---

## Task 2: SplatDepthSource — New Properties + `_bakeDepth` + `setMode`

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource` constructor ~line 691, after `stopOscillation` ~line 710)

- [ ] **Step 1: Run Codex to add new constructor properties**

  Prompt:
  ```
  In wigglegram.html, inside the SplatDepthSource constructor (the block starting with
  `constructor() {` around line 691), add these three lines before the closing brace `}`:

      this.mode = 'depth';
      this.bakedDepth = null;
      this.bakedWidth = 0;
      this.bakedHeight = 0;

  Do not change anything else.
  ```

- [ ] **Step 2: Run Codex to add `_bakeDepth` and `setMode` methods**

  Prompt:
  ```
  In wigglegram.html, immediately after the `stopOscillation()` method (the method that
  reads `stopOscillation() { if (this.oscId) { cancelAnimationFrame(this.oscId); this.oscId = null; } }`),
  add these two methods:

      async _bakeDepth(THREE) {
        if (!this.renderer || !this.depthTarget || !this.depthReadTarget || !this.depthMaterial) return;
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

      setMode(mode) {
        this.mode = mode;
        if (mode === '3d') {
          this.startOscillation(this._lastMode, this._lastParams);
        } else {
          this.stopOscillation();
        }
      }

  Do not change anything else.
  ```

- [ ] **Step 3: Verify**

  Read the SplatDepthSource class (constructor + first two methods) and confirm:
  - Constructor has `mode`, `bakedDepth`, `bakedWidth`, `bakedHeight`
  - `_bakeDepth` and `setMode` methods exist after `stopOscillation`

- [ ] **Step 4: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: add SplatDepthSource mode, _bakeDepth, and setMode"
  ```

---

## Task 3: Bbox Timing Fix + Wire `_bakeDepth` Into `load()`

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.load()`)

- [ ] **Step 1: Run Codex for bbox timing fix**

  Prompt:
  ```
  In wigglegram.html, inside SplatDepthSource.load(), find the line:
      await viewer.addSplatScene(blobUrl, { format, splatAlphaRemovalThreshold: 5, rotation: [1, 0, 0, 0] });
  Immediately after that line (before `const splatMesh = viewer.getSplatMesh();`), add:
      viewer.update();
  Do not change anything else.
  ```

- [ ] **Step 2: Run Codex to wire `_bakeDepth` and set default mode**

  Prompt:
  ```
  In wigglegram.html, inside SplatDepthSource.load(), find the line:
      this.startOscillation(PARAMS.mode, PARAMS);
  Replace it with:
      await this._bakeDepth(THREE);
      this.mode = 'depth';
  Do not change anything else.
  ```

  Note: `startOscillation` is called by `setMode('3d')` when the user toggles to 3D mode. In depth mode, the oscillation preview is not needed — the static depth image is shown.

- [ ] **Step 3: Verify**

  Read `load()` from `await viewer.addSplatScene` to `setStatus('splat loaded')` and confirm:
  - `viewer.update()` appears immediately after `addSplatScene`
  - `await this._bakeDepth(THREE)` and `this.mode = 'depth'` appear where `startOscillation` was

- [ ] **Step 4: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "fix: flush GS3D worker before bbox query, bake depth on splat load"
  ```

---

## Task 4: `renderToPane()` Depth Mode Branch

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.renderToPane()`, currently a no-op)

- [ ] **Step 1: Run Codex**

  Prompt:
  ```
  In wigglegram.html, find the SplatDepthSource method:
      renderToPane(canvas) {
        // no-op: live render already running via rAF loop
      }
  Replace it with:
      renderToPane(canvas) {
        if (this.mode === '3d') return; // live render already running via rAF loop
        if (!this.bakedDepth) return;
        const w = this.bakedWidth;
        const h = this.bakedHeight;
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        const img = ctx.createImageData(w, h);
        for (let i = 0; i < this.bakedDepth.length; i++) {
          const v = Math.round(this.bakedDepth[i] * 255);
          img.data[i * 4]     = v;
          img.data[i * 4 + 1] = v;
          img.data[i * 4 + 2] = v;
          img.data[i * 4 + 3] = 255;
        }
        ctx.putImageData(img, 0, 0);
      }
  Do not change anything else.
  ```

- [ ] **Step 2: Verify**

  Read `renderToPane()` and confirm the depth mode branch is present.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: renderToPane draws baked depth grayscale in depth mode"
  ```

---

## Task 5: `captureFrame()` Depth Mode Branch

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.captureFrame()`, ~line 960)

- [ ] **Step 1: Run Codex**

  Prompt:
  ```
  In wigglegram.html, find the SplatDepthSource.captureFrame() method. It starts with:
      async captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth) {
        if (!this.viewer || !this.camera || !this.renderer) return null;
  Replace those two lines with:
      async captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth) {
        if (this.mode === 'depth') {
          const angle = (frameIndex / totalFrames) * 2 * Math.PI;
          const xOffset = params.baseline * Math.sin(angle);
          const width = scaledSrc.width;
          const height = scaledSrc.height;
          let colorData;
          if (mode === 'orbit') {
            colorData = generateFrameOrbit(scaledSrc.data, scaledDepth, xOffset, width, height);
          } else if (mode === 'parallax') {
            colorData = generateFrameParallax(scaledSrc.data, scaledDepth, xOffset, width, height);
          } else if (mode === 'warp') {
            colorData = generateFrameWarp(scaledSrc.data, scaledDepth, xOffset, width, height);
          } else {
            colorData = generateFrameParallax(scaledSrc.data, scaledDepth, xOffset, width, height);
          }
          return { colorData, depthArray: scaledDepth, width, height };
        }
        if (!this.viewer || !this.camera || !this.renderer) return null;
  Do not change anything else.
  ```

- [ ] **Step 2: Verify**

  Read the start of `captureFrame()` and confirm the depth mode branch is at the top.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: captureFrame uses original photo + baked depth in depth mode"
  ```

---

## Task 6: Parallax Fix in `positionCamera()`

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.positionCamera()`, parallax branch ~line 931)

- [ ] **Step 1: Run Codex**

  Prompt:
  ```
  In wigglegram.html, inside SplatDepthSource.positionCamera(), find the line:
      this.camera.position.x = this.basePos.x + Math.sin(angle) * params.baseline * 0.05;
  Replace it with:
      const shift = (this._autoFitDist || 3.0) * (params.baseline / 100);
      this.camera.position.x = this.basePos.x + Math.sin(angle) * shift;
  Do not change anything else.
  ```

- [ ] **Step 2: Verify**

  Read `positionCamera()` parallax branch and confirm the new two-line formula is there.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "fix: parallax camera shift scales with auto-fit distance in 3D mode"
  ```

---

## Task 7: Pipeline `isSplat3D` / `isSplatDepth`

**Files:**
- Modify: `wigglegram.html` (`runPipeline`, ~lines 1626–1695)

- [ ] **Step 1: Run Codex to replace `isSplat` checks and add depth-baked pipeline branch**

  Prompt:
  ```
  In wigglegram.html, inside the runPipeline function, find this block:

      // SplatDepthSource provides its own color+depth — skip image scaling and depth computation
      const isSplat = activeDepthSource instanceof SplatDepthSource;

      if (isSplat && !activeDepthSource.viewer) {
        setStatus('splat not fully loaded yet — please wait', 'error');
        generateBtn.disabled = false;
        return;
      }

      let width, height, scaledSrc, depth, blurredSrc;
      let origW = 800, origH = 480;

      if (!isSplat) {

  Replace it with:

      const isSplat3D = activeDepthSource instanceof SplatDepthSource && activeDepthSource.mode === '3d';
      const isSplatDepth = activeDepthSource instanceof SplatDepthSource && activeDepthSource.mode === 'depth';

      if (isSplat3D && !activeDepthSource.viewer) {
        setStatus('splat not fully loaded yet — please wait', 'error');
        generateBtn.disabled = false;
        return;
      }
      if (isSplatDepth && !activeDepthSource.bakedDepth) {
        setStatus('splat depth not ready yet — please wait', 'error');
        generateBtn.disabled = false;
        return;
      }

      let width, height, scaledSrc, depth, blurredSrc;
      let origW = 800, origH = 480;

      if (!isSplat3D) {

  Do not change anything else yet.
  ```

- [ ] **Step 2: Run Codex to add `isSplatDepth` depth computation case**

  Prompt:
  ```
  In wigglegram.html, inside runPipeline, find this block:

        if (activeDepthSource instanceof ImageDepthSource) {
          const rawCanvas = document.createElement('canvas');
          rawCanvas.width = activeDepthSource.depthImageData.width;
          rawCanvas.height = activeDepthSource.depthImageData.height;
          rawCanvas.getContext('2d').putImageData(activeDepthSource.depthImageData, 0, 0);
          const tmp = document.createElement('canvas');
          tmp.width = width; tmp.height = height;
          const ctx = tmp.getContext('2d');
          ctx.drawImage(rawCanvas, 0, 0, width, height);
          const scaledDepthData = ctx.getImageData(0, 0, width, height);
          depth = computeLuminanceDepth(scaledDepthData, invert);
        } else {
          // LuminanceDepthSource: compute from scaled source
          depth = computeLuminanceDepth(scaledSrc, invert);
        }

  Replace it with:

        if (activeDepthSource instanceof ImageDepthSource) {
          const rawCanvas = document.createElement('canvas');
          rawCanvas.width = activeDepthSource.depthImageData.width;
          rawCanvas.height = activeDepthSource.depthImageData.height;
          rawCanvas.getContext('2d').putImageData(activeDepthSource.depthImageData, 0, 0);
          const tmp = document.createElement('canvas');
          tmp.width = width; tmp.height = height;
          const ctx = tmp.getContext('2d');
          ctx.drawImage(rawCanvas, 0, 0, width, height);
          const scaledDepthData = ctx.getImageData(0, 0, width, height);
          depth = computeLuminanceDepth(scaledDepthData, invert);
        } else if (isSplatDepth) {
          depth = scaleBakedDepth(
            activeDepthSource.bakedDepth,
            activeDepthSource.bakedWidth,
            activeDepthSource.bakedHeight,
            width, height
          );
        } else {
          // LuminanceDepthSource: compute from scaled source
          depth = computeLuminanceDepth(scaledSrc, invert);
        }

  Do not change anything else.
  ```

- [ ] **Step 3: Run Codex to replace remaining `isSplat` references in the finished callback**

  Prompt:
  ```
  In wigglegram.html, inside runPipeline (in the gif.on('finished', ...) callback and
  the line `if (isSplat) activeDepthSource.stopOscillation();`), replace every remaining
  occurrence of `isSplat` that is NOT already `isSplat3D` or `isSplatDepth` with `isSplat3D`.
  These will be the splat-specific renderer resize and oscillation resume lines.
  Do not change anything else.
  ```

- [ ] **Step 4: Verify**

  Search wigglegram.html for `isSplat` (not `isSplat3D`/`isSplatDepth`). There should be zero matches.

- [ ] **Step 5: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "refactor: isSplat3D/isSplatDepth pipeline, add scaleBakedDepth depth path"
  ```

---

## Task 8: UX — Toggle Buttons + Dynamic Zoom Binding

**Files:**
- Modify: `wigglegram.html` (CSS ~line 131, HTML ~line 314, Tweakpane setup ~line 489, splat load handler ~line 1040)

- [ ] **Step 1: Run Codex to add CSS for toggle buttons**

  Prompt:
  ```
  In wigglegram.html, immediately after the `.gif-preview-panel img { ... }` CSS block
  (around line 151), add:

    /* ─── SPLAT MODE TOGGLE ──────────────────────────────── */
    .splat-mode-toggle {
      display: none;
      gap: 0.3rem;
      align-items: center;
    }
    .splat-mode-toggle.visible { display: flex; }
    .splat-mode-btn {
      background: none;
      border: none;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--text-dim);
      padding: 0 0.2rem;
    }
    .splat-mode-btn.active { color: var(--green); }
    .splat-mode-btn:hover:not(.active) { color: var(--text); }

  Do not change anything else.
  ```

- [ ] **Step 2: Run Codex to add toggle buttons to depth pane label HTML**

  Prompt:
  ```
  In wigglegram.html, find the depth preview panel label:
      <div class="preview-label">
        <span id="depthPaneLabel">depth (luminance)</span>
      </div>
  Replace it with:
      <div class="preview-label">
        <span id="depthPaneLabel">depth (luminance)</span>
        <div class="splat-mode-toggle" id="splatModeToggle">
          <button class="splat-mode-btn active" id="splatDepthBtn" onclick="setSplatMode('depth')">[depth]</button>
          <button class="splat-mode-btn" id="splat3DBtn" onclick="setSplatMode('3d')">[3D]</button>
        </div>
      </div>
  Do not change anything else.
  ```

- [ ] **Step 3: Run Codex to remove the static `splatZoom` Tweakpane binding**

  Prompt:
  ```
  In wigglegram.html, inside setupTweakpane(), find and remove the entire block:
      motion.addBinding(PARAMS, 'splatZoom', {
        label: 'zoom',
        min: 0.1, max: 3.0, step: 0.05,
      }).on('change', (ev) => {
        if (activeDepthSource instanceof SplatDepthSource) {
          activeDepthSource.repositionCamera(ev.value);
        }
      });
  Do not change anything else.
  ```

- [ ] **Step 4: Run Codex to add `showSplatZoom`, `hideSplatZoom`, and `setSplatMode` functions**

  Prompt:
  ```
  In wigglegram.html, immediately after the closing brace of the `updateModeUI` function
  (the function that handles 'orbit'/'warp'/'parallax' mode UI changes), add:

    let splatZoomBinding = null;

    function showSplatZoom() {
      if (splatZoomBinding) return;
      splatZoomBinding = motionFolder.addBinding(PARAMS, 'splatZoom', {
        label: 'zoom',
        min: 0.1, max: 3.0, step: 0.05,
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

    window.setSplatMode = function(mode) {
      if (!(activeDepthSource instanceof SplatDepthSource)) return;
      activeDepthSource.setMode(mode);
      const depthCanvas = document.getElementById('depthCanvas');
      activeDepthSource.renderToPane(depthCanvas);
      document.getElementById('splatDepthBtn').classList.toggle('active', mode === 'depth');
      document.getElementById('splat3DBtn').classList.toggle('active', mode === '3d');
      if (mode === '3d') {
        showSplatZoom();
        updateDepthPaneLabel('splat (3D)');
      } else {
        hideSplatZoom();
        updateDepthPaneLabel('splat (depth)');
      }
    };

  Do not change anything else.
  ```

- [ ] **Step 5: Run Codex to show toggle and update label on splat load success**

  Prompt:
  ```
  In wigglegram.html, find the line inside the depth source input change handler:
      updateDepthPaneLabel('splat (live)');
  Replace it with:
      updateDepthPaneLabel('splat (depth)');
      hideSplatZoom();
      document.getElementById('splatModeToggle').classList.add('visible');
      document.getElementById('splatDepthBtn').classList.add('active');
      document.getElementById('splat3DBtn').classList.remove('active');
      activeDepthSource.renderToPane(document.getElementById('depthCanvas'));
  Do not change anything else.
  ```

- [ ] **Step 6: Run Codex to hide toggle when non-splat depth source is loaded**

  Prompt:
  ```
  In wigglegram.html, find the block inside the depth source input change handler that
  handles non-PLY files (the `img.onload` callback that creates an ImageDepthSource).
  Inside that callback, after `activeDepthSource.renderToPane(depthPaneCanvas);`, add:
      hideSplatZoom();
      document.getElementById('splatModeToggle').classList.remove('visible');
  Do not change anything else.
  ```

- [ ] **Step 7: Verify end-to-end**

  Open `wigglegram.html` in a browser:
  1. Load a source image
  2. Load a .ply file — confirm depth pane shows a grayscale depth image (not black void), depth label reads "splat (depth)", toggle buttons appear, zoom slider is absent
  3. Click `[3D]` — confirm live 3D render starts, label changes to "splat (3D)", zoom slider appears in Tweakpane
  4. Drag zoom slider — confirm scene zooms smoothly
  5. Click `[depth]` — confirm grayscale depth returns, zoom slider disappears
  6. Generate a GIF in depth mode — confirm effects (bokeh, wrap, CA) apply to output
  7. Switch to 3D mode, generate GIF — confirm 3D render output with effects

- [ ] **Step 8: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: splat mode toggle (depth/3D) with dynamic zoom binding"
  ```
