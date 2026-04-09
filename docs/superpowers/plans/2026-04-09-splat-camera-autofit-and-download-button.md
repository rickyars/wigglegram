# Splat Camera Auto-Fit + Download Button Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the download button to match the app's green-box button style, and replace the broken raw-distance splat camera slider with an auto-fit-on-load + zoom-multiplier approach.

**Architecture:** All changes are in `wigglegram.html` (single-file app). Task 1 is a pure CSS addition. Task 2 is a PARAMS + Tweakpane change. Task 3 updates the `SplatDepthSource.load()` bounding-box block. Task 4 updates `repositionCamera()`. All code edits go through Codex CLI — Claude orchestrates, Codex writes.

**Tech Stack:** Vanilla HTML/CSS/JS, THREE.js (dynamic import), @mkkellogg/gaussian-splats-3d (dynamic import), Tweakpane v4

---

## File Map

- Modify: `wigglegram.html` (all tasks)
  - CSS block ~line 202: add `button#downloadBtn` rule after `button#generateBtn` block
  - PARAMS object ~line 387: replace `splatDistance: 3` with `splatZoom: 1.0`
  - Tweakpane binding ~line 471: replace `splatDistance` binding with `splatZoom` binding
  - `SplatDepthSource.load()` ~line 804: compute and store `_autoFitDist` from bounding sphere
  - `repositionCamera()` ~line 883: accept zoom multiplier, compute distance from `_autoFitDist`

---

## Task 1: Download Button CSS

**Files:**
- Modify: `wigglegram.html` (~line 225, after `button#generateBtn:disabled` block)

This task has no testable behavior beyond visual inspection, so there's no failing test to write first. Make the change, verify visually in the browser, commit.

- [ ] **Step 1: Run Codex to add `button#downloadBtn` CSS rule**

  Prompt Codex with:
  ```
  In wigglegram.html, after the `button#generateBtn:disabled` CSS block (around line 224),
  add a new CSS rule for `button#downloadBtn` that gives it the same visual style as
  `button#generateBtn`: transparent background, `1px solid var(--green)` border, green text,
  same font-family/font-size/letter-spacing/text-transform/padding/transition/cursor.
  Width should be `auto` (not 100%) so it fits inline next to the "output" label.
  Also add a hover rule: `button#downloadBtn:hover` with `background: var(--green); color: #000;`.
  Do not change anything else.
  ```

- [ ] **Step 2: Verify in browser**

  Open `wigglegram.html` in a browser. Generate a GIF. Confirm the "download" button in the output panel header looks identical to the "generate gif" button: green outline, green text, fills green on hover.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "fix: style download button to match generate button"
  ```

---

## Task 2: Replace `splatDistance` with `splatZoom` in PARAMS and Tweakpane

**Files:**
- Modify: `wigglegram.html` (~line 387 PARAMS, ~line 471 Tweakpane binding)

- [ ] **Step 1: Run Codex to update PARAMS and Tweakpane binding**

  Prompt Codex with:
  ```
  In wigglegram.html, make two changes:

  1. In the PARAMS object (around line 387), replace:
       splatDistance: 3,
     with:
       splatZoom: 1.0,

  2. Replace the entire `motion.addBinding(PARAMS, 'splatDistance', ...)` block including
     its `.on('change', ...)` handler (lines ~471-478) with:

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

- [ ] **Step 2: Verify no JS errors**

  Open `wigglegram.html` in browser. Open DevTools console. Confirm no errors on load. Confirm the Tweakpane "Motion" folder now shows a "zoom" slider (0.1–3.0) instead of "splat distance".

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "refactor: replace splatDistance param with splatZoom multiplier"
  ```

---

## Task 3: Auto-Fit Camera Distance on Splat Load

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.load()`, ~lines 804-816)

- [ ] **Step 1: Run Codex to compute and store `_autoFitDist`**

  Prompt Codex with:
  ```
  In wigglegram.html, inside `SplatDepthSource.load()`, find the block that reads:

      if (bbox && !bbox.isEmpty()) {
        bbox.getCenter(center);
        distance = PARAMS.splatDistance;
      } else {
        console.warn(`SplatDepthSource: using fixed fallback distance=${PARAMS.splatDistance}`);
        distance = PARAMS.splatDistance;
      }

      camera.position.set(center.x, center.y, center.z + distance);
      camera.lookAt(center.x, center.y, center.z);
      this.basePos = camera.position.clone();
      this._sceneCenter = center.clone();
      console.log('[SplatDepthSource] camera auto-fit:', { center, distance });

  Replace it with:

      let autoFitDist = 3.0; // fallback if bbox unavailable
      if (bbox && !bbox.isEmpty()) {
        bbox.getCenter(center);
        const sphere = new THREE.Sphere();
        bbox.getBoundingSphere(sphere);
        if (sphere.radius > 0) {
          const fovRad = (Math.PI / 180) * 60;
          autoFitDist = sphere.radius / Math.sin(fovRad / 2);
        }
      } else {
        console.warn('SplatDepthSource: bbox unavailable, using fallback autoFitDist=3.0');
      }
      this._autoFitDist = autoFitDist;
      const distance = autoFitDist * PARAMS.splatZoom;
      camera.position.set(center.x, center.y, center.z + distance);
      camera.lookAt(center.x, center.y, center.z);
      this.basePos = camera.position.clone();
      this._sceneCenter = center.clone();
      console.log('[SplatDepthSource] camera auto-fit:', { center, autoFitDist, distance });

  Also remove the `let distance = PARAMS.splatDistance;` line near the top of that try block
  (around line 785) since distance is now computed inside the block above.

  Do not change anything else.
  ```

- [ ] **Step 2: Verify in browser**

  Load a .ply splat file. Confirm the splat fills the frame at zoom=1.0 without excessive black space. Check the console log: `[SplatDepthSource] camera auto-fit:` should show a sensible `autoFitDist` value (not 3.0 for a normally-sized splat) and `distance` = `autoFitDist * 1.0`.

- [ ] **Step 3: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "feat: auto-fit splat camera from bounding sphere on load"
  ```

---

## Task 4: Update `repositionCamera()` to Use Zoom Multiplier

**Files:**
- Modify: `wigglegram.html` (`SplatDepthSource.repositionCamera()`, ~lines 883-892)

- [ ] **Step 1: Run Codex to update `repositionCamera`**

  Prompt Codex with:
  ```
  In wigglegram.html, find the `repositionCamera(distance)` method of `SplatDepthSource`
  (around line 883). It currently reads:

      repositionCamera(distance) {
        if (!this.camera) return;
        const center = this._sceneCenter || { x: 0, y: 0, z: 0 };
        this.camera.position.set(center.x, center.y, center.z + distance);
        this.camera.lookAt(center.x, center.y, center.z);
        this.basePos = this.camera.position.clone();
        if (this._lastMode && this._lastParams) {
          this.startOscillation(this._lastMode, this._lastParams);
        }
      }

  Replace it with:

      repositionCamera(zoomMultiplier) {
        if (!this.camera) return;
        const center = this._sceneCenter || { x: 0, y: 0, z: 0 };
        const distance = (this._autoFitDist || 3.0) * zoomMultiplier;
        this.camera.position.set(center.x, center.y, center.z + distance);
        this.camera.lookAt(center.x, center.y, center.z);
        this.basePos = this.camera.position.clone();
        if (this._lastMode && this._lastParams) {
          this.startOscillation(this._lastMode, this._lastParams);
        }
      }

  Do not change anything else.
  ```

- [ ] **Step 2: Verify zoom slider works**

  Load a .ply splat. Drag the "zoom" slider. Confirm the camera moves closer/farther relative to the auto-fit position. At `0.5` the splat should appear 2x larger; at `2.0` it should appear half as large.

- [ ] **Step 3: Final end-to-end check**

  - Load a source image
  - Load a .ply splat as the depth source
  - Confirm splat fills the frame at zoom=1.0
  - Adjust zoom slider to confirm it works
  - Generate a GIF
  - Click download — confirm button is styled correctly and download works

- [ ] **Step 4: Commit**

  ```bash
  git add wigglegram.html
  git commit -m "fix: repositionCamera uses zoom multiplier relative to auto-fit distance"
  ```
