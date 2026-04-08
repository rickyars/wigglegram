# Wigglegram UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the depth-map and splat workflows into a single coherent pipeline where modes (orbit/parallax/warp) and all optics sliders apply regardless of depth source.

**Architecture:** Three `DepthSource` classes (`LuminanceDepthSource`, `ImageDepthSource`, `SplatDepthSource`) share a common interface (`renderToPane`, `captureFrame`). A shared `runPipeline(targetWidth)` function uses the active depth source to produce GIF frames, always applying the full post-processing chain. The splat canvas moves into the existing depth pane slot, eliminating the third container.

**Tech Stack:** Single-file HTML app (`wigglegram.html`). Three.js + `@mkkellogg/gaussian-splats-3d` for splat rendering. gif.js for encoding. Tweakpane for controls. **All code changes via Codex CLI.**

---

## File Map

| File | Changes |
|---|---|
| `wigglegram.html` | All changes — HTML structure, CSS, JS logic |

---

## Important Technical Notes

**Splat depth buffer extraction:** Three.js does not expose the WebGL depth buffer directly. To read depth per-pixel, create a `THREE.WebGLRenderTarget` with a `THREE.DepthTexture`, render the splat scene to it, then use a full-screen shader pass to linearize and output depth values to a color render target. Read that color target back to CPU via `renderer.readRenderTargetPixels`. Linearize NDC depth with: `linearDepth = (2 * near * far) / (far + near - ndcDepth * (far - near))` then normalize to [0,1] by dividing by `far`.

**Splat camera trajectories per mode:**
- `orbit`: `camera.position.x = sin(angle) * dist; camera.position.z = cos(angle) * dist; camera.lookAt(0,0,0)` — current behavior
- `parallax`: `camera.position.x = basePos.x + lateralShift; camera.position.z = basePos.z` — no rotation, strafe only, `camera.lookAt(0, 0, 0)` using a fixed target
- `warp`: camera position stays at `basePos`, camera is rotated by `angle` radians around Y axis in place (no lookAt — set quaternion directly)

**Frame angle:** For all modes, frame `i` of `n` uses `angle = Math.sin((i / n) * 2 * Math.PI) * amplitude` — producing smooth oscillation. This is unchanged from the current orbit mode.

---

## Task 1: HTML/CSS — UI Restructure

**Files:**
- Modify: `wigglegram.html` (HTML + CSS sections only)

Remove the separate splat container, consolidate uploads to one depth source button, split the generate button into two.

- [ ] **Step 1: Remove `splatContainer` and `splatUploadRow` from HTML**

Run:
```bash
codex "In wigglegram.html, remove the div with id='splatContainer' and its contents entirely. Remove the div with id='splatUploadRow' and its contents entirely. Do not change any JavaScript yet."
```

Verify: Open `wigglegram.html` in browser. No splat container or upload row visible. Source image upload and depth map upload remain.

- [ ] **Step 2: Merge depth source uploads into one button**

Run:
```bash
codex "In wigglegram.html, replace the two upload buttons (id='depthUploadBtn' and the splatUploadBtn that was just removed) with a single upload button. The new button: id='depthSourceBtn', label text 'Upload Depth Source (optional)', accepts both image/* and .ply files via a single file input with id='depthSourceInput' and accept='image/*,.ply'. Keep id='sourceUploadBtn' unchanged. Add a [clear] link with id='clearDepthSource' next to the button label, initially hidden (display:none). Do not change any JavaScript yet."
```

Verify: Right panel shows two upload buttons: source image + depth source. File picker for depth source accepts both images and .ply files.

- [ ] **Step 3: Replace Generate GIF with Generate Preview + Generate GIF**

Run:
```bash
codex "In wigglegram.html, replace the single button id='generateBtn' with two buttons stacked vertically. First button: id='previewBtn', text 'generate preview', styled identically to the current generateBtn (transparent bg, green border/text, full width, uppercase mono). Second button: id='generateBtn', text 'generate gif', same style but initially disabled (disabled attribute). Both buttons are in a flex column container with gap 0.5rem. Do not change any JavaScript yet."
```

Verify: Right panel bottom shows "generate preview" (enabled after image load) and "generate gif" (always disabled for now) buttons stacked.

- [ ] **Step 4: Remove the 'record gif' button from the depth pane label area**

The splatContainer was already removed in Step 1, so this is just verifying there is no orphaned record button. Check that no button with id `recordSplatBtn` exists in the HTML.

Run:
```bash
codex "In wigglegram.html, verify and ensure there is no element with id='recordSplatBtn' remaining in the HTML. Remove it if found. Do not change any JavaScript yet."
```

- [ ] **Step 5: Update depth pane label to use a dynamic `<span>`**

Run:
```bash
codex "In wigglegram.html, in the depth preview panel (the right pane of the previews grid), change the static label text to: <span id='depthPaneLabel'>depth (luminance)</span>. Keep the existing id='clearDepth' clear link next to it. Do not change any JavaScript yet."
```

Verify: Depth pane label reads "depth (luminance)" on load.

- [ ] **Step 6: Commit**

```bash
git add wigglegram.html
git commit -m "refactor: restructure UI — unified depth upload, split preview/gif buttons, remove splat container"
```

---

## Task 2: LuminanceDepthSource and ImageDepthSource Classes

**Files:**
- Modify: `wigglegram.html` (JavaScript section)

Introduce the DepthSource abstraction and wire the two non-splat sources. The existing pixel-displacement functions (`generateFrameOrbit`, `generateFrameParallax`, `generateFrameWarp`, `getDepthMap`, `computeLuminanceDepth`, etc.) stay untouched — they are called from inside `captureFrame`.

- [ ] **Step 1: Add LuminanceDepthSource class**

Run:
```bash
codex "In wigglegram.html's script section, add a class LuminanceDepthSource before the setupTweakpane() call. It holds a reference to the source ImageData. Constructor: constructor(srcImageData). Methods:

renderToPane(canvas): compute depth using the existing getDepthMap(srcImageData) function, render it grayscale to canvas (same logic as existing updateDepthPreview but targeting the given canvas argument instead of getElementById('depthCanvas')).

async captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth): accepts pre-scaled source ImageData and pre-computed depth Float32Array (passed in by the pipeline to avoid recomputation). Calls the appropriate existing frame generator based on mode ('orbit' → generateFrameOrbit, 'parallax' → generateFrameParallax, 'warp' → generateFrameWarp). Returns { colorData: Uint8ClampedArray, depthArray: Float32Array, width: number, height: number }.

Do not remove or change any existing functions."
```

Verify: Class is present in source. No existing functions changed.

- [ ] **Step 2: Add ImageDepthSource class**

Run:
```bash
codex "In wigglegram.html's script section, add a class ImageDepthSource after LuminanceDepthSource. Constructor: constructor(depthImageData) — holds the uploaded depth ImageData. Methods:

renderToPane(canvas): scale depthImageData to canvas dimensions, compute luminance depth from it, render grayscale (same as LuminanceDepthSource.renderToPane but using this.depthImageData as source).

async captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth): identical signature and body to LuminanceDepthSource.captureFrame — the scaledDepth passed in is already derived from this depth image by the pipeline. Returns { colorData, depthArray, width, height }.

Do not remove or change any existing functions."
```

- [ ] **Step 3: Add activeDepthSource global state and wire depth source upload**

Run:
```bash
codex "In wigglegram.html's script section:

1. Add a global variable: let activeDepthSource = null;

2. Update loadSourceImage() to set activeDepthSource = new LuminanceDepthSource(srcImageData) after setting srcImageData, then call activeDepthSource.renderToPane(document.getElementById('depthCanvas')).

3. Add an event listener for id='depthSourceInput' (the new unified depth source file input). On change:
   - If file extension is '.ply': store the file in a global let pendingSplatFile = null (set pendingSplatFile = file, set activeDepthSource = null for now, update pane label to 'splat (loading...)', update depthSourceBtn label text to file.name and add 'loaded' class).
   - Otherwise (image): run the existing loadCustomDepth logic but adapted: load the image, create ImageDepthSource, set activeDepthSource = new ImageDepthSource(imageData), call activeDepthSource.renderToPane(depthCanvas), update pane label to 'depth (custom: ' + file.name + ')', update depthSourceBtn label and class.

4. Wire the id='clearDepthSource' link: on click, reset activeDepthSource = new LuminanceDepthSource(srcImageData), re-render pane, reset label to 'depth (luminance)', reset depthSourceBtn text and class.

5. Update the existing id='clearDepth' onclick (clearCustomDepth) to do the same reset as step 4 — or remove it if it no longer exists in the HTML.

Keep existing loadCustomDepth and related functions in place — they can stay unused for now."
```

Verify: Load an image — depth pane shows luminance depth. Upload a .jpg depth map — pane updates to grayscale depth map, label shows filename. Clear — reverts to luminance.

- [ ] **Step 4: Update depthPaneLabel dynamically**

Run:
```bash
codex "In wigglegram.html, add a helper function updateDepthPaneLabel(text) that sets document.getElementById('depthPaneLabel').textContent = text. Call it from: loadSourceImage (text: 'depth (luminance)'), the depthSourceInput image handler (text: 'depth (custom: ' + filename + ')'), the depthSourceInput .ply handler (text: 'splat (loading...)'), and the clear handler (text: 'depth (luminance)'). Do not change existing label update logic elsewhere yet."
```

- [ ] **Step 5: Commit**

```bash
git add wigglegram.html
git commit -m "feat: add LuminanceDepthSource and ImageDepthSource, wire unified depth upload"
```

---

## Task 3: Refactored Frame Pipeline

**Files:**
- Modify: `wigglegram.html` (JavaScript section)

Extract a shared `runPipeline(targetWidth)` function. Wire Generate Preview and Generate GIF buttons. Generate GIF enables after first preview.

- [ ] **Step 1: Extract runPipeline(targetWidth) from the existing generate() function**

Run:
```bash
codex "In wigglegram.html, refactor the existing window.generate function into a new async function runPipeline(targetWidth). runPipeline:

1. Reads PARAMS (frames, frameDelay, bokehCoc, focusDist, lightWrap, chromaticAberr, invertDepth, mode).
2. Scales source image to targetWidth (same scaling logic as existing generate()).
3. Computes scaled depth from activeDepthSource: if activeDepthSource is a LuminanceDepthSource, use computeLuminanceDepth on the scaled source; if ImageDepthSource, scale its depthImageData to targetWidth and computeLuminanceDepth on that. (SplatDepthSource handles its own depth internally — pass null for scaledDepth in that case.)
4. Applies boxBlur twice as before.
5. Calls buildDepthBlurredSrc as before.
6. For each frame i:
   a. Calls activeDepthSource.captureFrame(i, numFrames, PARAMS.mode, PARAMS, scaledSrc, depth) → { colorData, depthArray, width, height }
   b. Applies applyLightWrap(colorData, depthArray, wrapRadius, width, height)
   c. Applies circularDiscBokeh(colorData, depthArray, focusDist, cocScale, width, height)
   d. Applies applyChromaticAberration(colorData, caStrength, angle, width, height)
   e. Adds frame to gif
7. Returns the gif blob via the existing on('finished') handler → showGifPreview(blob).

Keep the existing generate() function as a thin wrapper: window.generate = async function() { await runPipeline(PARAMS.outputWidth); }

Add window.generatePreview = async function() { await runPipeline(400); }

The previewBtn calls generatePreview, the generateBtn calls generate. Wire onclick for both buttons."
```

Verify: "generate preview" button produces a small fast GIF. "generate gif" button produces full-res GIF.

- [ ] **Step 2: Enable Generate GIF only after a preview exists**

Run:
```bash
codex "In wigglegram.html, in the showGifPreview(blob) function, after displaying the GIF, also enable the Generate GIF button: document.getElementById('generateBtn').disabled = false. In loadSourceImage(), disable generateBtn again: document.getElementById('generateBtn').disabled = true. This ensures Generate GIF is only available after Generate Preview has been run for the current image."
```

Verify: On load — "generate gif" is disabled. After clicking "generate preview" — "generate gif" becomes enabled. Loading a new image — "generate gif" disables again.

- [ ] **Step 3: Disable previewBtn during generation, re-enable on complete**

Run:
```bash
codex "In wigglegram.html, in the runPipeline function, at the start disable both previewBtn and generateBtn. In the gif on('finished') callback, re-enable previewBtn and (if a preview has been shown) enable generateBtn. Also disable generateBtn during generation to prevent double-clicks."
```

- [ ] **Step 4: Commit**

```bash
git add wigglegram.html
git commit -m "feat: split generate into runPipeline, wire Generate Preview (400px) and Generate GIF buttons"
```

---

## Task 4: SplatDepthSource

**Files:**
- Modify: `wigglegram.html` (JavaScript section)

The most complex task. SplatDepthSource renders live in the depth pane, positions its camera per mode for each frame, and extracts both color and depth data from the WebGL renderer.

- [ ] **Step 1: Add SplatDepthSource class skeleton**

Run:
```bash
codex "In wigglegram.html, add a class SplatDepthSource after ImageDepthSource. Constructor takes no arguments. Properties: this.file = null; this.viewer = null; this.camera = null; this.renderer = null; this.basePos = null; this.oscId = null; this.depthTarget = null; this.depthReadTarget = null; this.depthMaterial = null;

Add stub methods (empty, return null):
- async load(file, paneCanvas): loads the .ply file into a Three.js/GS3D viewer rendering to paneCanvas
- renderToPane(canvas): no-op (live render already running via rAF loop)
- startOscillation(mode, params): starts rAF loop that repositions camera by mode and renders
- stopOscillation(): cancels rAF loop
- async captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth): returns null for now
- dispose(): cleans up viewer, renderer, rAF

Do not implement the methods yet."
```

- [ ] **Step 2: Implement SplatDepthSource.load()**

Run:
```bash
codex "In wigglegram.html, implement SplatDepthSource.load(file, paneCanvas). This method should:

1. Call this.stopOscillation() and dispose any existing viewer.
2. Import THREE and GS3D dynamically (same as existing loadSplatFile function).
3. Size paneCanvas to its container width × (containerWidth * 0.6), minimum height 300px.
4. Create THREE.WebGLRenderer with { canvas: paneCanvas, antialias: true, preserveDrawingBuffer: true }.
5. Create THREE.PerspectiveCamera(60, w/h, 0.1, 500) at position (0, 0, 5).
6. Create GS3D.Viewer with { selfDrivenMode: false, useBuiltInControls: false, sharedMemoryForWorkers: false, renderer, camera }.
7. Load the .ply blob URL with viewer.addSplatScene(blobUrl, { format: GS3D.SceneFormat?.Ply ?? 2, splatAlphaRemovalThreshold: 5 }).
8. Set this.viewer, this.camera, this.renderer, this.basePos = camera.position.clone().
9. Create a depth extraction render target: this.depthTarget = new THREE.WebGLRenderTarget(w, h, { depthBuffer: true, depthTexture: new THREE.DepthTexture(w, h, THREE.FloatType) }).
10. Create this.depthReadTarget = new THREE.WebGLRenderTarget(w, h, { type: THREE.FloatType }) for reading linearized depth as color.
11. Create a full-screen quad material (THREE.ShaderMaterial) for linearizing depth. Store as this.depthMaterial. Vertex shader: standard full-screen quad (gl_Position = vec4(position, 1.0)). Fragment shader reads depthTexture, linearizes using near=0.1 far=500, outputs to r channel: float z = texture2D(depthTex, vUv).r; float linear = (2.0 * 0.1 * 500.0) / (500.0 + 0.1 - (z * 2.0 - 1.0) * (500.0 - 0.1)); gl_FragColor = vec4(linear / 500.0, 0.0, 0.0, 1.0);
12. Call this.startOscillation('orbit', PARAMS).
13. Set status to 'splat loaded'.

Reuse imports from the existing module-level scope where possible."
```

- [ ] **Step 3: Implement SplatDepthSource.startOscillation() and camera positioning helpers**

Run:
```bash
codex "In wigglegram.html, implement SplatDepthSource.startOscillation(mode, params) and a helper positionCamera(mode, angle, params):

positionCamera(mode, angle, params):
  const dist = this.basePos.length() || 5;
  const amplitude = params.baseline;
  if (mode === 'orbit'):
    this.camera.position.x = Math.sin(angle) * dist;
    this.camera.position.y = this.basePos.y;
    this.camera.position.z = Math.cos(angle) * dist;
    this.camera.lookAt(0, 0, 0);
  else if (mode === 'parallax'):
    this.camera.position.copy(this.basePos);
    this.camera.position.x = this.basePos.x + Math.sin(angle) * amplitude * 0.05;
    this.camera.lookAt(0, this.basePos.y, 0);
  else if (mode === 'warp'):
    this.camera.position.copy(this.basePos);
    this.camera.rotation.set(0, angle * 0.05, 0);

startOscillation(mode, params):
  const startTime = performance.now();
  const tick = () => {
    const t = (performance.now() - startTime) / 1000;
    const angle = Math.sin(t * 2 * Math.PI) * (params.baseline * Math.PI / 180);
    this.positionCamera(mode, angle, params);
    this.viewer.update();
    this.viewer.render();
    this.oscId = requestAnimationFrame(tick);
  };
  this.oscId = requestAnimationFrame(tick);

stopOscillation():
  if (this.oscId) { cancelAnimationFrame(this.oscId); this.oscId = null; }"
```

- [ ] **Step 4: Implement SplatDepthSource.captureFrame()**

Run:
```bash
codex "In wigglegram.html, implement SplatDepthSource.captureFrame(frameIndex, totalFrames, mode, params, scaledSrc, scaledDepth):

1. Compute angle: const rawAngle = (frameIndex / totalFrames) * 2 * Math.PI; const angle = Math.sin(rawAngle) * (params.baseline * Math.PI / 180);
2. Call this.positionCamera(mode, angle, params).
3. Render color: this.viewer.update(); this.viewer.render(); — color is now in the renderer's default framebuffer (preserveDrawingBuffer: true).
4. Read color pixels: const colorPixels = new Uint8ClampedArray(w * h * 4); this.renderer.readRenderTargetPixels is not available for the default framebuffer — instead use: const gl = this.renderer.getContext(); gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, colorPixels); Note: WebGL readPixels reads bottom-to-top, so flip vertically.
5. Render depth: render the splat scene again to this.depthTarget (set renderer.setRenderTarget(this.depthTarget), call this.viewer.render(), renderer.setRenderTarget(null)).
6. Render linearized depth: use a full-screen quad scene with this.depthMaterial sampling this.depthTarget.depthTexture, render to this.depthReadTarget.
7. Read depth pixels: const depthPixels = new Float32Array(w * h * 4); this.renderer.readRenderTargetPixels(this.depthReadTarget, 0, 0, w, h, depthPixels);
8. Extract depthArray: const depthArray = new Float32Array(w * h); for each pixel, depthArray[i] = depthPixels[i * 4] (red channel = linearized depth). Flip vertically to match color.
9. Return { colorData: colorPixels, depthArray, width: w, height: h }.

w and h are this.renderer.domElement.width and height."
```

- [ ] **Step 5: Wire SplatDepthSource into the upload handler and pipeline**

Run:
```bash
codex "In wigglegram.html:

1. In the depthSourceInput change handler, when file extension is '.ply': instead of just storing pendingSplatFile, do: const splatSrc = new SplatDepthSource(); activeDepthSource = splatSrc; await splatSrc.load(file, document.getElementById('depthCanvas')); updateDepthPaneLabel('splat (live)');

2. In runPipeline(targetWidth), add a branch for SplatDepthSource: if activeDepthSource is instanceof SplatDepthSource, skip the scaledSrc/depth computation and pass null for scaledSrc and scaledDepth to captureFrame. SplatDepthSource.captureFrame provides its own color and depth.

3. After SplatDepthSource.captureFrame returns { colorData, depthArray, width, height }, the pipeline continues with the same post-processing chain (applyLightWrap, circularDiscBokeh, applyChromaticAberration) using the returned colorData and depthArray.

4. On clear (clearDepthSource): call activeDepthSource.dispose() if it is a SplatDepthSource before resetting to LuminanceDepthSource.

5. Add SplatDepthSource.dispose(): stopOscillation(); try { this.viewer.dispose(); } catch(e) {} this.renderer.dispose(); this.depthTarget.dispose(); this.depthReadTarget.dispose();"
```

- [ ] **Step 6: Verify splat end-to-end**

Manual verification steps:
1. Load a source image — depth pane shows luminance depth map
2. Upload a `.ply` file — depth pane switches to live oscillating 3D splat render
3. Click "generate preview" — GIF encodes using splat color + depth, post-processing applies (check for bokeh/CA effect)
4. GIF preview shows in output panel
5. "generate gif" button enables — click it, full-res GIF generates

- [ ] **Step 7: Commit**

```bash
git add wigglegram.html
git commit -m "feat: add SplatDepthSource with live depth pane, mode-driven camera, depth buffer extraction"
```

---

## Task 5: Tweakpane Cleanup and Mode Relabeling

**Files:**
- Modify: `wigglegram.html` (JavaScript section — Tweakpane setup)

- [ ] **Step 1: Remove 'splat wiggle' from mode dropdown**

Run:
```bash
codex "In wigglegram.html, in the setupTweakpane() function, remove the 'splat': 'splat wiggle' entry from the mode binding options object. The options should only be: 'orbit': 'orbit', 'parallax': 'parallax', 'warp': 'warp'."
```

- [ ] **Step 2: Simplify updateModeUI — remove splat branch**

Run:
```bash
codex "In wigglegram.html, in the updateModeUI(mode) function, remove the 'splat' branch entirely (the block starting with 'if (mode === splat)'). Also remove the code that shows/hides splatContainer since it no longer exists. Keep only the orbit, parallax (currently the else branch), and add an explicit warp branch if needed. The function should only manage: fovBinding visibility (hidden unless orbit), and the baselineBinding label/range (orbit: label='baseline' min=1 max=15; parallax: label='parallax shift' min=3 max=60; warp: label='amplitude (°)' min=1 max=15)."
```

- [ ] **Step 3: Update startOscillation call when mode changes**

Run:
```bash
codex "In wigglegram.html, in the mode binding's on('change') handler (inside setupTweakpane), after calling updateModeUI(ev.value), if activeDepthSource instanceof SplatDepthSource: call activeDepthSource.stopOscillation() then activeDepthSource.startOscillation(ev.value, PARAMS). This ensures the live splat preview switches camera trajectory immediately when the mode dropdown changes."
```

- [ ] **Step 4: Verify mode switching**

Manual verification:
1. Load image + .ply splat
2. Switch mode dropdown orbit → parallax → warp — splat pane camera motion changes visibly each time
3. Switch mode with depth map loaded — no errors, mode still applies to GIF generation

- [ ] **Step 5: Commit**

```bash
git add wigglegram.html
git commit -m "refactor: remove splat mode from dropdown, clean up updateModeUI, wire mode change to splat oscillation"
```

---

## Self-Review Checklist

- [x] **Spec: Unified depth source upload (one button, image or .ply)** → Task 1 Step 2
- [x] **Spec: Two input panes only (source + depth/splat)** → Task 1 Step 1 (splatContainer removed)
- [x] **Spec: Depth pane label updates dynamically** → Task 1 Step 5, Task 2 Step 4
- [x] **Spec: Splat auto-oscillates in depth pane** → Task 4 Steps 2-3
- [x] **Spec: Modes orbit/parallax/warp apply to splat camera** → Task 4 Step 3, Task 5 Step 3
- [x] **Spec: All optics sliders apply to splat frames** → Task 4 Step 5 (post-processing chain runs on splat colorData)
- [x] **Spec: Generate Preview (400px) + Generate GIF (outputWidth)** → Task 3 Steps 1-3
- [x] **Spec: Generate GIF disabled until preview generated** → Task 3 Step 2
- [x] **Spec: Sliders don't trigger re-renders** → No slider onChange calls to runPipeline
- [x] **Spec: splat mode removed from dropdown** → Task 5 Step 1
- [x] **Spec: B-compatibility — captureFrame is the isolation boundary** → All tasks route through captureFrame
- [x] **Depth buffer linearization formula documented** → Technical Notes section
