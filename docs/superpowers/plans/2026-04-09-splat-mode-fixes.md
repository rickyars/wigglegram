# Splat Mode Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four splat mode bugs: invisible depth preview, flat side-to-side motion, tiny splat in 3D mode, and jittery GIF frames.

**Architecture:** Three surgical edits to `wigglegram.html`. The bbox poll exits too early causing wrong camera placement (fixes 1–3). Canvas visibility is never swapped between depth/3D modes (fix 1). The GS3D sort worker needs time to settle before GIF frame capture (fix 4).

**Tech Stack:** Single-file vanilla JS app. GS3D (Gaussian splats), Three.js, gif.js. All code changes via Codex CLI — never edit the file directly.

---

## Task 1: Fix bbox poll so camera lands on the actual scene

**Files:**
- Modify: `wigglegram.html:934`

The poll loop currently exits as soon as `getSplatCount() > 0`, but `splatMesh.splatBuffers[0]` (required by `getSplatCenter`) is populated slightly later. Extend the condition to also wait for `splatBuffers[0]`.

- [ ] **Step 1: Run Codex CLI to extend the poll condition**

```bash
codex "In wigglegram.html, find this exact line inside SplatDepthSource.load():

        while (splatMesh.getSplatCount() === 0 && pollMs < 5000) {

Replace it with:

        while ((splatMesh.getSplatCount() === 0 || !splatMesh.splatBuffers?.[0]) && pollMs < 5000) {"
```

- [ ] **Step 2: Also update the comment on the line above (line 932) to match**

```bash
codex "In wigglegram.html, find this comment inside SplatDepthSource.load():

        // Poll until GS3D worker has populated splatBuffer (getSplatCount > 0)

Replace it with:

        // Poll until GS3D worker has populated splatBuffer and splatBuffers[0] (both required for getSplatCenter)"
```

- [ ] **Step 3: Verify in browser**

Load a `.ply` file. Open DevTools console. You should no longer see:
```
Could not get splat bounds from GS3D API: TypeError: Cannot read properties of undefined (reading 'splatBuffer')
```
And you should no longer see:
```
SplatDepthSource: bbox unavailable, using fallback autoFitDist=3.0
```
The splat should fill the canvas instead of appearing as a tiny dot.

- [ ] **Step 4: Commit**

```bash
git add wigglegram.html
git commit -m "fix: extend splat bbox poll to wait for splatBuffers[0]"
```

---

## Task 2: Swap canvas visibility when toggling depth ↔ 3D mode

**Files:**
- Modify: `wigglegram.html:831-840` (`setMode`)
- Modify: `wigglegram.html:1036-1038` (end of `load`)

When `load()` runs it hides `depthCanvas` and shows a GL canvas. Neither `setMode` nor `load`'s completion path ever reveals the depth canvas again when in depth mode. Fix by swapping visibility in both places.

- [ ] **Step 1: Update `setMode` to swap canvas visibility**

```bash
codex "In wigglegram.html, find the setMode method of SplatDepthSource which currently reads:

    setMode(mode) {
      this.mode = mode;
      if (mode === '3d') {
        if (this._lastMode && this._lastParams) {
          this.startOscillation(this._lastMode, this._lastParams);
        }
      } else {
        this.stopOscillation();
      }
    }

Replace it with:

    setMode(mode) {
      this.mode = mode;
      if (mode === '3d') {
        if (this._originalCanvas) this._originalCanvas.style.display = 'none';
        if (this._glCanvas) this._glCanvas.style.display = '';
        if (this._lastMode && this._lastParams) {
          this.startOscillation(this._lastMode, this._lastParams);
        }
      } else {
        this.stopOscillation();
        if (this._glCanvas) this._glCanvas.style.display = 'none';
        if (this._originalCanvas) this._originalCanvas.style.display = '';
      }
    }"
```

- [ ] **Step 2: Reveal depth canvas after load completes**

```bash
codex "In wigglegram.html, find these lines at the end of SplatDepthSource.load(), just before the closing brace of the try block:

      await this._bakeDepth(THREE);
      this.mode = 'depth';
      setStatus('splat loaded', 'done');

Replace them with:

      await this._bakeDepth(THREE);
      this.mode = 'depth';
      if (this._glCanvas) this._glCanvas.style.display = 'none';
      if (this._originalCanvas) this._originalCanvas.style.display = '';
      setStatus('splat loaded', 'done');"
```

- [ ] **Step 3: Verify in browser**

Load a `.ply` file. After loading:
- The depth pane should show a grayscale image (brighter = closer to camera).
- Click `[3D]` — the grayscale disappears, the WebGL splat renders.
- Click `[depth]` — the grayscale reappears, the WebGL canvas hides.

- [ ] **Step 4: Commit**

```bash
git add wigglegram.html
git commit -m "fix: swap canvas visibility when toggling splat depth/3D mode"
```

---

## Task 3: Settle splat sort before capturing each GIF frame

**Files:**
- Modify: `wigglegram.html:1129-1134` (`captureFrame`, 3D branch)

GS3D sorts splats back-to-front in a web worker. `captureFrame` repositions the camera then immediately renders — the sort for the new angle isn't done yet. Replace the single `update/render` pair with a 3-tick rAF settle loop before the color readback.

- [ ] **Step 1: Run Codex CLI to add the settle loop**

```bash
codex "In wigglegram.html, inside the captureFrame method of SplatDepthSource, find this block in the 3D branch (after positionCamera is called):

      // Render color to default framebuffer
      this.renderer.setRenderTarget(null);
      this.viewer.update();
      this.viewer.render();

Replace it with:

      // Settle splat sort worker before capture (3 rAF ticks)
      for (let i = 0; i < 3; i++) {
        this.viewer.update();
        await new Promise(r => requestAnimationFrame(r));
      }

      // Render color to default framebuffer
      this.renderer.setRenderTarget(null);
      this.viewer.update();
      this.viewer.render();"
```

- [ ] **Step 2: Verify in browser**

Load a `.ply` file, switch to 3D mode, generate a GIF. The output frames should show no popping or flickering between them — the splat should appear stable across frames.

- [ ] **Step 3: Commit**

```bash
git add wigglegram.html
git commit -m "fix: settle splat sort worker before GIF frame capture in 3D mode"
```
