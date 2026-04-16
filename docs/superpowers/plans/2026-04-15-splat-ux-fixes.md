# Splat UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix splat (.ply) loading to auto-show 3D, remove depth baking, add direct swing angle control in degrees, add X/Y centering offsets, and reorganize Tweakpane into three context-sensitive sections.

**Architecture:** All logic lives in `wigglegram.html` (single-file app). `SplatDepthSource` is stripped to 3D-only — all depth baking code is removed. Tweakpane is rebuilt into 5 folders: Motion (always), Depth map (depth-only), Splat (splat-only), Optics (always), Output (always). The [depth]/[3D] toggle becomes a read-only visual indicator. **All code changes use Codex CLI.**

**Tech Stack:** Vanilla JS ES modules, Three.js, @mkkellogg/gaussian-splats-3d, Tweakpane 4

---

## File Structure

Only one file is modified: `wigglegram.html`

Key regions (by approximate line number at plan-write time):
- `PARAMS` object: ~line 418
- CSS for `.splat-mode-btn`: ~line 138
- HTML toggle buttons: ~line 337
- `setupTweakpane()`: ~line 469
- `updateModeUI()`: ~line 561
- `showSplatZoom()` / `hideSplatZoom()`: ~line 593
- `setSplatMode()`: ~line 613
- `SplatDepthSource` class: ~line 769
  - `_bakeDepth()`: ~line 795
  - `setMode()`: ~line 881
  - `dispose()`: ~line 896
  - `load()`: ~line 913
  - `renderToPane()`: ~line 1122
  - `repositionCamera()`: ~line 1141
  - `positionCamera()`: ~line 1153
  - `startOscillation()`: ~line 1167
  - `captureFrame()`: ~line 1187
- `depthSourceInput` change handler: ~line 1290

---

## Task 1: Add new PARAMS fields and disabled toggle CSS

**Files:**
- Modify: `wigglegram.html` (PARAMS object ~line 418, CSS ~line 138)

- [ ] **Step 1: Add new PARAMS fields via Codex**

```bash
codex "In wigglegram.html, in the PARAMS object (around line 418), add three new fields after splatZoom: splatSwingAngle: 5, splatOffsetX: 0, splatOffsetY: 0"
```

Expected: PARAMS object now has `splatSwingAngle: 5`, `splatOffsetX: 0`, `splatOffsetY: 0`

- [ ] **Step 2: Add disabled CSS for toggle buttons via Codex**

```bash
codex "In wigglegram.html, in the CSS section for .splat-mode-btn (around line 138), add a new rule: .splat-mode-btn.disabled { pointer-events: none; opacity: 0.35; } and remove the hover style from disabled buttons by adding :not(.disabled) to the existing hover selector"
```

Expected: `.splat-mode-btn.disabled` rule exists, hover rule reads `.splat-mode-btn:hover:not(.active):not(.disabled)`

- [ ] **Step 3: Verify by opening wigglegram.html in browser**

No functional changes yet — just check no JS errors in console.

- [ ] **Step 4: Commit**

```bash
git add wigglegram.html
git commit -m "feat: add splatSwingAngle/splatOffsetX/splatOffsetY params, disabled toggle CSS"
```

---

## Task 2: Strip SplatDepthSource to 3D-only

Remove all depth baking infrastructure. This is the largest change.

**Files:**
- Modify: `wigglegram.html` (SplatDepthSource class ~line 769)

- [ ] **Step 1: Remove depth baking state from constructor via Codex**

```bash
codex "In wigglegram.html, in the SplatDepthSource constructor (around line 769), remove these fields: this.depthTarget, this.depthReadTarget, this.depthMaterial, this.bakedDepth, this.bakedWidth, this.bakedHeight, and this.mode"
```

- [ ] **Step 2: Remove _bakeDepth() method via Codex**

```bash
codex "In wigglegram.html, remove the entire _bakeDepth() method from SplatDepthSource (around line 795 to 879). Remove all lines from 'async _bakeDepth(THREE) {' through its closing brace."
```

- [ ] **Step 3: Remove setMode() method via Codex**

```bash
codex "In wigglegram.html, remove the entire setMode() method from SplatDepthSource (around line 881). Remove all lines from 'setMode(mode) {' through its closing brace."
```

- [ ] **Step 4: Remove renderToPane() method via Codex**

```bash
codex "In wigglegram.html, remove the entire renderToPane() method from SplatDepthSource (around line 1122). Remove all lines from 'renderToPane(canvas) {' through its closing brace."
```

- [ ] **Step 5: Clean up dispose() via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.dispose() (around line 896), remove the three lines that dispose depthTarget, depthReadTarget, and depthMaterial (the lines containing 'this.depthTarget.dispose()', 'this.depthReadTarget.dispose()', and 'this.depthMaterial.dispose()'). Also remove the lines that set them to null."
```

- [ ] **Step 6: Clean up load() — remove depth render target setup via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.load() (around line 913), remove the block that creates this.depthTarget (a WebGLRenderTarget with depthBuffer/depthTexture), this.depthReadTarget, and this.depthMaterial (the ShaderMaterial with vertexShader/fragmentShader). Remove approximately lines 1078-1113."
```

- [ ] **Step 7: Clean up load() — remove depth bake call and mode reset via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.load(), remove the final three lines: 'await this._bakeDepth(THREE);', 'this.mode = \"depth\";', and the two lines that hide glCanvas and show originalCanvas (the lines with 'this._glCanvas.style.display = \"none\"' and 'this._originalCanvas.style.display = \"\"'). The load() method should end with 'setStatus(\"splat loaded\", \"done\");'"
```

- [ ] **Step 8: Verify in browser**

Open `wigglegram.html`. Console should show no errors on page load. No splat loaded yet so no visible change.

- [ ] **Step 9: Commit**

```bash
git add wigglegram.html
git commit -m "refactor: strip SplatDepthSource to 3D-only, remove all depth baking code"
```

---

## Task 3: Auto-start 3D view on splat load + update toggle to read-only indicator

**Files:**
- Modify: `wigglegram.html` (load() ~line 913, depthSourceInput handler ~line 1290, HTML toggle ~line 337)

- [ ] **Step 1: Auto-start oscillation at end of load() via Codex**

```bash
codex "In wigglegram.html, at the end of SplatDepthSource.load(), after 'setStatus(\"splat loaded\", \"done\");', add two lines: make the glCanvas visible ('this._glCanvas.style.display = \"\";') and start oscillation ('this.startOscillation(PARAMS.mode, PARAMS);')"
```

- [ ] **Step 2: Update depthSourceInput handler for splat to show read-only [3D] indicator via Codex**

```bash
codex "In wigglegram.html, in the depthSourceInput change handler (around line 1290), find the .then() callback after splatSrc.load(). Replace its entire body with: updateDepthPaneLabel('splat (3D)'); document.getElementById('splatModeToggle').classList.add('visible'); document.getElementById('splatDepthBtn').classList.remove('active'); document.getElementById('splatDepthBtn').classList.add('disabled'); document.getElementById('splat3DBtn').classList.add('active'); document.getElementById('splat3DBtn').classList.remove('disabled'); activeDepthSource.renderToPane is not needed — remove that call. Also remove the calls to hideSplatZoom() and the splatDepthBtn/splat3DBtn active class manipulations that were there before."
```

- [ ] **Step 3: Update depthSourceInput handler for image depth to show read-only [depth] indicator via Codex**

```bash
codex "In wigglegram.html, in the depthSourceInput change handler, in the else branch that handles non-.ply image files (around line 1320), after setting activeDepthSource and calling renderToPane, update the toggle: document.getElementById('splatModeToggle').classList.add('visible'); document.getElementById('splatDepthBtn').classList.add('active'); document.getElementById('splatDepthBtn').classList.remove('disabled'); document.getElementById('splat3DBtn').classList.remove('active'); document.getElementById('splat3DBtn').classList.add('disabled'); Remove the existing splatModeToggle.classList.remove('visible') call."
```

- [ ] **Step 4: Remove onclick handlers from HTML toggle buttons via Codex**

```bash
codex "In wigglegram.html, in the HTML for the splat mode toggle buttons (around line 337), remove the onclick attributes from both splatDepthBtn and splat3DBtn. They are now read-only indicators, not interactive buttons."
```

- [ ] **Step 5: Remove setSplatMode() function via Codex**

```bash
codex "In wigglegram.html, remove the entire setSplatMode() window function (around line 613). It is no longer needed."
```

- [ ] **Step 6: Verify in browser**

Load `wigglegram.html`, load a source image, then load a .ply splat. The depth pane should immediately show the live 3D render (GL canvas visible). The toggle should show `[3D]` active and `[depth]` grayed. The toggle buttons should not respond to clicks.

- [ ] **Step 7: Commit**

```bash
git add wigglegram.html
git commit -m "feat: auto-start 3D view on splat load, toggle becomes read-only indicator"
```

---

## Task 4: Update oscillation and captureFrame to use direct swing angle in degrees

**Files:**
- Modify: `wigglegram.html` (startOscillation ~line 1167, captureFrame ~line 1187)

- [ ] **Step 1: Update startOscillation formula via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.startOscillation() (around line 1167), replace the angle calculation line that reads 'const angle = Math.sin(t * Math.PI / 2) * params.baseline * Math.tan(oscFovRad / 2) / (rendW / 2);' with 'const angle = Math.sin(t * Math.PI / 2) * (PARAMS.splatSwingAngle * Math.PI / 180);'. Remove the oscFovRad and rendW variables if they are no longer used."
```

- [ ] **Step 2: Update captureFrame formula via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.captureFrame() for the 3D branch (around line 1207), replace the angle calculation lines. Remove 'const fovRad = (Math.PI / 180) * 60;' and replace 'const angle = Math.sin(rawAngle) * params.baseline * Math.tan(fovRad / 2) / (w / 2);' with 'const angle = Math.sin(rawAngle) * (PARAMS.splatSwingAngle * Math.PI / 180);'"
```

- [ ] **Step 3: Remove depth mode branch from captureFrame via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.captureFrame() (around line 1187), remove the entire first if-block: 'if (this.mode === \"depth\") { ... }' including all its contents. SplatDepthSource is now always 3D."
```

- [ ] **Step 4: Verify in browser**

Load a splat. The preview should oscillate. Changing splatSwingAngle (via console: `PARAMS.splatSwingAngle = 15`) should make the swing noticeably wider.

- [ ] **Step 5: Commit**

```bash
git add wigglegram.html
git commit -m "feat: splat oscillation uses direct swing angle in degrees"
```

---

## Task 5: Add X/Y offset to positionCamera and repositionCamera

**Files:**
- Modify: `wigglegram.html` (positionCamera ~line 1153, repositionCamera ~line 1141)

- [ ] **Step 1: Update positionCamera to use offsets via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.positionCamera() (around line 1153), update the camera.lookAt call to apply PARAMS.splatOffsetX and PARAMS.splatOffsetY: change 'this.camera.lookAt(cx, cy, cz)' to 'this.camera.lookAt(cx + PARAMS.splatOffsetX, cy + PARAMS.splatOffsetY, cz)'"
```

- [ ] **Step 2: Update repositionCamera to use offsets via Codex**

```bash
codex "In wigglegram.html, in SplatDepthSource.repositionCamera() (around line 1141), update the camera setup to apply offsets. Change 'this.camera.position.set(center.x, center.y, center.z + distance)' to 'this.camera.position.set(center.x + PARAMS.splatOffsetX, center.y + PARAMS.splatOffsetY, center.z + distance)' and change 'this.camera.lookAt(center.x, center.y, center.z)' to 'this.camera.lookAt(center.x + PARAMS.splatOffsetX, center.y + PARAMS.splatOffsetY, center.z)'"
```

- [ ] **Step 3: Verify via console**

In browser console: `PARAMS.splatOffsetX = 0.5; activeDepthSource.repositionCamera(PARAMS.splatZoom)` — the 3D view should shift horizontally.

- [ ] **Step 4: Commit**

```bash
git add wigglegram.html
git commit -m "feat: apply splatOffsetX/Y to splat camera look-at point"
```

---

## Task 6: Reorganize Tweakpane into 5 folders

Replace the current Motion / Optics / Output folders with the new 5-folder structure. This is a rewrite of `setupTweakpane()` and removal of `updateModeUI()`, `showSplatZoom()`, `hideSplatZoom()`.

**Files:**
- Modify: `wigglegram.html` (setupTweakpane ~line 469, updateModeUI ~line 561, showSplatZoom ~line 593)

- [ ] **Step 1: Rewrite setupTweakpane() via Codex**

```bash
codex "In wigglegram.html, completely replace the setupTweakpane() function with the following implementation:

function setupTweakpane() {
  const pane = new Tweakpane.Pane({
    container: document.getElementById('tweakpane-container'),
    title: 'parameters',
  });

  // ── Motion (always visible) ──
  const motionFolder = pane.addFolder({ title: 'Motion' });
  window._motionFolder = motionFolder;

  // motion amount binding — disposed and recreated on context change
  window._motionBinding = motionFolder.addBinding(PARAMS, 'baseline', {
    label: 'baseline',
    min: 1, max: 15, step: 0.5,
  });

  motionFolder.addBinding(PARAMS, 'fov', {
    label: 'fov',
    min: 20, max: 80, step: 1,
  });

  motionFolder.addBinding(PARAMS, 'frames', {
    label: 'frames',
    min: 4, max: 20, step: 2,
  });

  motionFolder.addBinding(PARAMS, 'frameDelay', {
    label: 'frame delay (ms)',
    min: 30, max: 200, step: 10,
  });

  // ── Depth map (hidden until a depth image is loaded) ──
  const depthFolder = pane.addFolder({ title: 'Depth map' });
  depthFolder.hidden = true;
  window._depthFolder = depthFolder;

  depthFolder.addBinding(PARAMS, 'mode', {
    label: 'effect mode',
    options: { orbit: 'orbit', parallax: 'parallax', warp: 'warp' },
  }).on('change', (ev) => {
    updateMotionBinding(ev.value, false);
  });

  depthFolder.addBinding(PARAMS, 'invertDepth', { label: 'invert depth' })
    .on('change', () => {
      if (activeDepthSource && !(activeDepthSource instanceof SplatDepthSource)) {
        activeDepthSource.renderToPane(document.getElementById('depthCanvas'));
      }
    });

  // ── Splat (hidden until a splat is loaded) ──
  const splatFolder = pane.addFolder({ title: 'Splat' });
  splatFolder.hidden = true;
  window._splatFolder = splatFolder;

  splatFolder.addBinding(PARAMS, 'splatZoom', {
    label: 'zoom',
    min: 0.1, max: 3.0, step: 0.05,
  }).on('change', (ev) => {
    if (activeDepthSource instanceof SplatDepthSource) {
      activeDepthSource.repositionCamera(ev.value);
    }
  });

  splatFolder.addBinding(PARAMS, 'splatOffsetX', {
    label: 'X offset',
    min: -2.0, max: 2.0, step: 0.05,
  }).on('change', () => {
    if (activeDepthSource instanceof SplatDepthSource) {
      activeDepthSource.repositionCamera(PARAMS.splatZoom);
    }
  });

  splatFolder.addBinding(PARAMS, 'splatOffsetY', {
    label: 'Y offset',
    min: -2.0, max: 2.0, step: 0.05,
  }).on('change', () => {
    if (activeDepthSource instanceof SplatDepthSource) {
      activeDepthSource.repositionCamera(PARAMS.splatZoom);
    }
  });

  // ── Optics (always visible) ──
  const opticsFolder = pane.addFolder({ title: 'Optics' });

  opticsFolder.addBinding(PARAMS, 'bokehCoc', {
    label: 'bokeh coc',
    min: 0, max: 40, step: 1,
  }).on('change', () => {
    if (activeDepthSource && !(activeDepthSource instanceof SplatDepthSource)) {
      activeDepthSource.renderToPane(document.getElementById('depthCanvas'));
    }
  });

  opticsFolder.addBinding(PARAMS, 'focusDist', {
    label: 'focus dist',
    min: 0, max: 1, step: 0.01,
  });

  opticsFolder.addBinding(PARAMS, 'lightWrap', {
    label: 'light wrap',
    min: 0, max: 5, step: 0.5,
  });

  opticsFolder.addBinding(PARAMS, 'chromaticAberr', {
    label: 'chromatic aberr',
    min: 0, max: 1.5, step: 0.1,
  });

  // ── Output (always visible) ──
  const outputFolder = pane.addFolder({ title: 'Output' });

  outputFolder.addBinding(PARAMS, 'outputWidth', {
    label: 'output width',
    min: 200, max: 3000, step: 100,
  });
}"
```

- [ ] **Step 2: Add updateMotionBinding() helper via Codex**

Note: Tweakpane appends bindings in insertion order. Since the motion amount binding is disposed/recreated, it will re-appear at the bottom of the Motion folder after the first context switch. This is acceptable — if position matters, the folder can be rebuilt entirely, but for now appending is fine.


```bash
codex "In wigglegram.html, after the setupTweakpane() function, add a new helper function:

function updateMotionBinding(effectMode, isSplat) {
  if (window._motionBinding) {
    window._motionBinding.dispose();
    window._motionBinding = null;
  }
  const folder = window._motionFolder;
  if (isSplat) {
    window._motionBinding = folder.addBinding(PARAMS, 'splatSwingAngle', {
      label: 'swing angle °',
      min: 1, max: 20, step: 0.5,
    });
  } else if (effectMode === 'orbit') {
    window._motionBinding = folder.addBinding(PARAMS, 'baseline', {
      label: 'baseline',
      min: 1, max: 15, step: 0.5,
    });
  } else if (effectMode === 'parallax') {
    window._motionBinding = folder.addBinding(PARAMS, 'baseline', {
      label: 'parallax shift',
      min: 3, max: 60, step: 1,
    });
  } else if (effectMode === 'warp') {
    window._motionBinding = folder.addBinding(PARAMS, 'baseline', {
      label: 'amplitude °',
      min: 1, max: 15, step: 0.5,
    });
  }
}"
```

- [ ] **Step 3: Remove updateModeUI(), showSplatZoom(), hideSplatZoom() via Codex**

```bash
codex "In wigglegram.html, remove the following functions entirely as they are replaced by updateMotionBinding() and the new folder structure: updateModeUI(), showSplatZoom(), hideSplatZoom(). Also remove the savedParallaxShift variable declaration and the splatZoomBinding variable declaration."
```

- [ ] **Step 4: Update depthSourceInput handler to toggle folder visibility via Codex**

```bash
codex "In wigglegram.html, in the depthSourceInput change handler:

1. In the splat (.ply) branch .then() callback, after the existing toggle indicator updates, add:
   if (window._depthFolder) window._depthFolder.hidden = true;
   if (window._splatFolder) window._splatFolder.hidden = false;
   updateMotionBinding(null, true);

2. In the image depth (non-.ply) branch, after setting activeDepthSource and rendering to pane, add:
   if (window._depthFolder) window._depthFolder.hidden = false;
   if (window._splatFolder) window._splatFolder.hidden = true;
   updateMotionBinding(PARAMS.mode, false);

3. Remove any remaining calls to updateModeUI(), showSplatZoom(), hideSplatZoom() in this handler."
```

- [ ] **Step 5: Fix any remaining references to old variables via Codex**

```bash
codex "In wigglegram.html, search for any remaining references to the variables fovBinding, baselineBinding, motionFolder, splatZoomBinding, savedParallaxShift that may have been left over from the old setupTweakpane(). Remove or replace them as appropriate — these variables no longer exist."
```

- [ ] **Step 6: Verify in browser**

Open `wigglegram.html`. Should see 3 folders on load: Motion, Optics, Output. Load a source image. Load a depth image — Depth map and Motion folders should update; Depth map folder appears. Load a .ply splat — Depth map folder hides, Splat folder appears, Motion folder shows "swing angle °" slider.

- [ ] **Step 7: Commit**

```bash
git add wigglegram.html
git commit -m "feat: reorganize Tweakpane into 5 context-sensitive folders"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full flow test — depth map**

1. Open `wigglegram.html` in browser
2. Load a source image
3. Load a depth image (PNG/JPG)
4. Verify: Depth map folder visible, Splat folder hidden
5. Verify: [depth] toggle active, [3D] grayed
6. Verify: effect mode / invert depth in Depth map folder
7. Change effect mode — verify motion amount slider relabels correctly
8. Generate GIF — verify it works

- [ ] **Step 2: Full flow test — splat**

1. Load a .ply splat file
2. Verify: depth pane immediately shows live 3D render (no manual [3D] click needed)
3. Verify: [3D] toggle active, [depth] grayed, neither button responds to clicks
4. Verify: Splat folder visible with zoom, X offset, Y offset
5. Verify: Motion folder shows "swing angle °" slider
6. Adjust swing angle — verify preview oscillation changes width
7. Adjust X offset — verify scene shifts horizontally
8. Adjust Y offset — verify scene shifts vertically
9. Generate GIF in 3D mode — verify it exports correctly

- [ ] **Step 3: Commit if any minor fixes needed**

```bash
git add wigglegram.html
git commit -m "fix: <description of any minor fixes>"
```
