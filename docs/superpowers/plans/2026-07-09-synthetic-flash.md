# Synthetic Flash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a depth-aware synthetic flash effect (near-bright/far-dark falloff + vignette) to the splat 3D preview, toggleable via a new Tweakpane "Flash" folder, applied every render frame so it survives into GIF/MP4 export.

**Architecture:** `SplatDepthSource` (the class that owns the Three.js renderer/camera/viewer for splat mode) gains a small compositor: an offscreen `WebGLRenderTarget` with an attached `DepthTexture`, plus a one-triangle-quad `ShaderMaterial` pass that reads color+depth and writes the flash-lit result to the visible canvas. This replaces the two call sites that currently do `viewer.render()` straight to the screen.

**Tech Stack:** Vanilla JS in a single HTML file (`wigglegram.html`), Three.js (`three` ESM import), `@mkkellogg/gaussian-splats-3d`, Tweakpane 4. No build step, no test framework — verification is manual, in-browser.

## Global Constraints

- Single-file app: all changes go in `E:\projects\wigglegram\wigglegram.html`. No new files, no bundler.
- Follow existing code conventions in this file: 2-space indent, `PARAMS` object holds all tunables, Tweakpane folders named/capitalized like `Motion`, `Depth map`, `Splat`, `Optics`, `Output`.
- Flash only applies in splat (3D) mode — it must not affect `ImageDepthSource` (the 2D depth-map mode). The new Tweakpane folder must hide/show in lockstep with the existing `splatFolder`.
- No automated test suite exists in this repo. Verification is done by running the app in a browser (see `run` skill / manual steps in each task) and checking the console for errors plus visually confirming the effect.
- Do not touch the flash origin/position — fixed at camera per the approved spec (`docs/superpowers/specs/2026-07-09-synthetic-flash-design.md`). No XY offset control for v1.

---

### Task 1: Add flash PARAMS and Tweakpane "Flash" folder

**Files:**
- Modify: `wigglegram.html:430-447` (PARAMS object)
- Modify: `wigglegram.html:457-462` (Tweakpane folder ref declarations)
- Modify: `wigglegram.html:534-564` (splatFolder block — add flashFolder right after it)
- Modify: `wigglegram.html:1162-1163`, `1198-1199`, `1272-1273`, `1286-1287`, `1302-1303`, `1467`, `1486-1487` (every place `splatFolder.hidden` is toggled — mirror the same toggle for `flashFolder`)

**Interfaces:**
- Produces: `PARAMS.flashEnabled` (bool, default `false`), `PARAMS.flashIntensity` (number, default `1.0`), `PARAMS.flashFalloff` (number, default `4.0`), `PARAMS.flashWarmth` (number, default `0.3`). `flashFolder` (module-level `let`, mirrors `splatFolder` visibility).

- [ ] **Step 1: Add flash fields to PARAMS**

In `wigglegram.html`, in the `PARAMS` object (currently lines 430-447), add after `format: 'gif',`:

```js
    format: 'gif',
    flashEnabled: false,
    flashIntensity: 1.0,
    flashFalloff: 4.0,
    flashWarmth: 0.3,
```

- [ ] **Step 2: Declare the `flashFolder` module-level variable**

Next to the existing `let splatFolder = null;` (line 462), add:

```js
  let splatFolder = null;
  let flashFolder = null;
```

- [ ] **Step 3: Add the "Flash" Tweakpane folder**

Immediately after the closing of the `splatFolder` block (after the `splatOffsetY` binding's `.on('change', ...)` call ends, i.e. right after line 563's closing `});`), insert:

```js
    // ── Flash (hidden until a splat is loaded) ──
    flashFolder = pane.addFolder({ title: 'Flash' });
    flashFolder.hidden = true;

    flashFolder.addBinding(PARAMS, 'flashEnabled', { label: 'enabled' });

    flashFolder.addBinding(PARAMS, 'flashIntensity', {
      label: 'intensity',
      min: 0, max: 3.0, step: 0.05,
    });

    flashFolder.addBinding(PARAMS, 'flashFalloff', {
      label: 'falloff range',
      min: 0.5, max: 20.0, step: 0.1,
    });

    flashFolder.addBinding(PARAMS, 'flashWarmth', {
      label: 'warmth',
      min: -1.0, max: 1.0, step: 0.05,
    });
```

These bindings don't need `.on('change', ...)` handlers — the compositor reads `PARAMS.flash*` directly every frame (wired in Task 3), and the existing `pane.on('change', () => schedulePreviewRebuild())` at the bottom of `setupTweakpane` already covers UI refresh for other consumers.

- [ ] **Step 4: Mirror `splatFolder.hidden` toggles onto `flashFolder`**

Find every line that sets `splatFolder.hidden = <value>;` (as of this plan: lines 1162-1163, 1198-1199, 1272-1273, 1286-1287, 1302-1303, 1486-1487) and add an identical line for `flashFolder` right next to it, e.g. where you see:

```js
      if (splatFolder) splatFolder.hidden = false;
```

add directly below it:

```js
      if (flashFolder) flashFolder.hidden = false;
```

(and the same pairing for every `splatFolder.hidden = true;` occurrence). Also check line 1467 — that one only touches `depthFolder`, so no `flashFolder` change is needed there (it doesn't touch `splatFolder` either — confirm by reading the surrounding 5 lines before editing; only add the `flashFolder` mirror where `splatFolder` is also being set).

- [ ] **Step 5: Manual verification**

Open `wigglegram.html` in a browser (e.g. via a local static server or the `run` skill), upload a photo, generate a splat, and confirm:
- A "Flash" folder appears in the Tweakpane panel once the splat loads, positioned after "Splat".
- Toggling to 2D depth mode (if applicable in the UI) hides the "Flash" folder along with "Splat".
- No console errors.

- [ ] **Step 6: Commit**

```bash
git add wigglegram.html
git commit -m "feat: add Flash Tweakpane folder and PARAMS"
```

---

### Task 2: Build the depth-aware compositor inside `SplatDepthSource`

**Files:**
- Modify: `wigglegram.html:805-818` (constructor — add compositor state fields)
- Modify: `wigglegram.html:837-849` (`dispose()` — clean up compositor resources)
- Modify: `wigglegram.html` — add two new methods to `SplatDepthSource`: `_ensureCompositor(w, h)` and `_renderWithFlash()`, placed after `dispose()` (currently ending at line 849) and before `async load(...)` (currently starting at line 851).

**Interfaces:**
- Consumes: `PARAMS.flashEnabled`, `PARAMS.flashIntensity`, `PARAMS.flashFalloff`, `PARAMS.flashWarmth` (from Task 1). `this.renderer`, `this.camera`, `this.viewer` (already set by `load()`). The module-level `THREE` import already used throughout `SplatDepthSource` (imported dynamically inside `load()` at line 865 as a local `const THREE`, but also referenced by later methods like `positionCamera` via closures — confirm by checking that `THREE` is accessible; if not module-scoped, see Step 0 below).
- Produces: `this._compositor` (`{ width, height, renderTarget, material, scene, camera }` or `null`), `this._renderWithFlash()` — replaces raw `this.viewer.update(); this.viewer.render();` render calls in Task 3.

- [ ] **Step 0: Confirm `THREE` scoping**

Read `wigglegram.html` lines 805-1123 (the full `SplatDepthSource` class) and check whether `THREE` (imported via `const THREE = await import('three');` inside `load()`) is available to other methods like `positionCamera` and `captureFrame`. Since `positionCamera` uses `Math.sin`/`Math.cos` only (no `THREE.*` calls) and `captureFrame` doesn't reference `THREE` either, `THREE` is currently local to `load()`. Store it on the instance so the new compositor methods can use it: in `load()`, immediately after the existing line `THREE = await import('three');` succeeds (inside the `try` block around line 865), add:

```js
        this._THREE = THREE;
```

- [ ] **Step 1: Add compositor state to the constructor**

In the constructor (lines 806-818), add after `this._lastParams = null;`:

```js
      this._lastParams = null;
      this._compositor = null;
      this._THREE = null;
```

- [ ] **Step 2: Write `_ensureCompositor(w, h)`**

Insert this method in `SplatDepthSource`, after `dispose()` (after line 849) and before `async load(file, paneCanvas) {` (line 851):

```js
    _ensureCompositor(w, h) {
      const THREE = this._THREE;
      if (!THREE || !this.renderer) return;
      if (this._compositor && this._compositor.width === w && this._compositor.height === h) return;
      if (this._compositor) {
        this._compositor.renderTarget.dispose();
        this._compositor.material.dispose();
        this._compositor.scene.remove(this._compositor.scene.children[0]);
      }
      const depthTexture = new THREE.DepthTexture(w, h);
      depthTexture.type = THREE.UnsignedIntType;
      const renderTarget = new THREE.WebGLRenderTarget(w, h, { depthTexture, depthBuffer: true });
      const material = new THREE.ShaderMaterial({
        uniforms: {
          tDiffuse: { value: renderTarget.texture },
          tDepth: { value: depthTexture },
          cameraNear: { value: this.camera.near },
          cameraFar: { value: this.camera.far },
          flashEnabled: { value: false },
          flashIntensity: { value: 1.0 },
          flashFalloff: { value: 4.0 },
          flashWarmth: { value: 0.0 },
        },
        vertexShader: `
          varying vec2 vUv;
          void main() {
            vUv = uv;
            gl_Position = vec4(position.xy, 0.0, 1.0);
          }
        `,
        fragmentShader: `
          uniform sampler2D tDiffuse;
          uniform sampler2D tDepth;
          uniform float cameraNear;
          uniform float cameraFar;
          uniform bool flashEnabled;
          uniform float flashIntensity;
          uniform float flashFalloff;
          uniform float flashWarmth;
          varying vec2 vUv;

          float linearizeDepth(float z) {
            float zNdc = z * 2.0 - 1.0;
            return (2.0 * cameraNear * cameraFar) / (cameraFar + cameraNear - zNdc * (cameraFar - cameraNear));
          }

          void main() {
            vec4 color = texture2D(tDiffuse, vUv);
            if (!flashEnabled) {
              gl_FragColor = color;
              return;
            }
            float depth = texture2D(tDepth, vUv).x;
            float dist = linearizeDepth(depth);
            float falloff = clamp(1.0 - dist / max(flashFalloff, 0.001), 0.0, 1.0);
            falloff = pow(falloff, 1.5);
            vec2 centered = vUv - 0.5;
            float vignette = clamp(1.0 - dot(centered, centered) * 1.5, 0.0, 1.0);
            float light = falloff * vignette * flashIntensity;
            vec3 warm = vec3(1.0 + flashWarmth * 0.15, 1.0, 1.0 - flashWarmth * 0.15);
            vec3 lit = color.rgb * (1.0 + light) * warm;
            gl_FragColor = vec4(lit, color.a);
          }
        `,
      });
      const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
      const scene = new THREE.Scene();
      scene.add(quad);
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
      this._compositor = { width: w, height: h, renderTarget, material, scene, camera };
    }
```

- [ ] **Step 3: Write `_renderWithFlash()`**

Immediately after `_ensureCompositor`, add:

```js
    _renderWithFlash() {
      const w = this.renderer.domElement.width;
      const h = this.renderer.domElement.height;
      this._ensureCompositor(w, h);
      if (!this._compositor) {
        // Fallback: no compositor available, render straight to canvas.
        this.renderer.setRenderTarget(null);
        this.viewer.update();
        this.viewer.render();
        return;
      }
      const { renderTarget, material, scene, camera } = this._compositor;
      material.uniforms.flashEnabled.value = !!PARAMS.flashEnabled;
      material.uniforms.flashIntensity.value = PARAMS.flashIntensity;
      material.uniforms.flashFalloff.value = PARAMS.flashFalloff;
      material.uniforms.flashWarmth.value = PARAMS.flashWarmth;

      this.renderer.setRenderTarget(renderTarget);
      this.viewer.update();
      this.viewer.render();

      this.renderer.setRenderTarget(null);
      this.renderer.render(scene, camera);
    }
```

- [ ] **Step 4: Dispose compositor resources in `dispose()`**

In `dispose()` (lines 837-849), add before `if (this.viewer) { ... }`:

```js
      if (this._compositor) {
        this._compositor.renderTarget.dispose();
        this._compositor.material.dispose();
        this._compositor = null;
      }
```

- [ ] **Step 5: Manual verification**

Open the app in a browser, upload a photo, generate a splat. With no other changes yet (Task 3 wires this in), there should be zero behavior change — confirm the console has no new errors and the splat still renders and oscillates normally. This step only confirms the new code doesn't break on load (it's inert until Task 3 calls `_renderWithFlash`).

- [ ] **Step 6: Commit**

```bash
git add wigglegram.html
git commit -m "feat: add depth-aware flash compositor to SplatDepthSource"
```

---

### Task 3: Wire the compositor into the render loop and frame capture

**Files:**
- Modify: `wigglegram.html:1070-1078` (`startOscillation` tick — live preview render loop)
- Modify: `wigglegram.html:1100-1103` (`captureFrame` — export frame render)

**Interfaces:**
- Consumes: `this._renderWithFlash()` from Task 2.

- [ ] **Step 1: Replace the render call in the oscillation tick**

In `startOscillation`, the tick function currently reads (around lines 1070-1078):

```js
      const tick = () => {
        const t = (performance.now() - startTime) / 1000;
        const angle = Math.sin(t * Math.PI / 2) * (PARAMS.splatSwingAngle * Math.PI / 180);
        this.positionCamera(mode, angle, params);
        this.viewer.update();
        this.viewer.render();
        this.oscId = requestAnimationFrame(tick);
      };
```

Replace the `this.viewer.update(); this.viewer.render();` pair with:

```js
      const tick = () => {
        const t = (performance.now() - startTime) / 1000;
        const angle = Math.sin(t * Math.PI / 2) * (PARAMS.splatSwingAngle * Math.PI / 180);
        this.positionCamera(mode, angle, params);
        this._renderWithFlash();
        this.oscId = requestAnimationFrame(tick);
      };
```

- [ ] **Step 2: Replace the render call in `captureFrame`**

In `captureFrame` (around lines 1100-1103), currently:

```js
      // Render color to default framebuffer
      this.renderer.setRenderTarget(null);
      this.viewer.update();
      this.viewer.render();
```

Replace with:

```js
      // Render color (with flash compositing) to default framebuffer
      this._renderWithFlash();
```

- [ ] **Step 3: Manual verification — live preview**

Run the app, upload a photo, generate a splat. In the "Flash" folder, enable "enabled" and increase "intensity". Confirm:
- The live 3D preview visibly brightens near objects and darkens the background as the camera swings.
- Toggling "enabled" off returns to the original unlit look.
- Adjusting "falloff range" and "warmth" visibly changes the effect.
- No console errors, and frame rate still feels smooth (no visible stutter).

- [ ] **Step 4: Manual verification — export**

With flash enabled and tuned to a visible level, export a GIF (and/or MP4 if available) and confirm the flash effect is present in the exported frames — open the exported file and check that near/far falloff and vignette are visible, matching what was seen live.

- [ ] **Step 5: Commit**

```bash
git add wigglegram.html
git commit -m "feat: apply synthetic flash to live preview and exported frames"
```

---

### Task 4: Cross-check performance and idle behavior

**Files:**
- None (verification-only task, no code changes expected unless an issue is found).

- [ ] **Step 1: Confirm idle behavior**

With the app open and a splat loaded, pause/stop the oscillation (if the UI has a pause control) or navigate away from the splat view. Confirm via the browser's performance/GPU tab (or simply observing CPU/GPU usage) that no rendering — and therefore no flash compositing — happens while idle, matching the existing renderer's behavior (this should require no code change, since `_renderWithFlash` is only ever called from the same two call sites that already gated on active rendering).

- [ ] **Step 2: Confirm resize handling doesn't leak render targets**

If the app supports resizing the splat canvas (check whether `glCanvas.width`/`height` or `renderer.setSize` is ever called again after initial `load()`), reload a new photo a few times in a row and watch the console for WebGL context warnings (e.g. "too many active WebGL contexts", "out of memory"). `_ensureCompositor` disposes the old render target/material whenever size changes, and `dispose()`/`load()` (line 854, `if (this.renderer) { this.renderer.dispose(); ... }`) already tears down the whole renderer between loads, so the compositor should not leak across loads. Confirm no warnings appear after 3-4 reloads.

- [ ] **Step 3: Record findings**

No commit needed for this task unless Step 1 or 2 surfaces a bug — if so, fix it, then commit with an appropriate message describing the fix (e.g. `fix: dispose flash compositor render target on resize`).

---

## Post-plan check

After Task 3, the feature is complete and usable end-to-end. Task 4 is a safety/perf sanity pass, not new functionality — it's fine to stop after Task 3 if time-constrained, but Task 4 should be run at least once before considering this shippable.
