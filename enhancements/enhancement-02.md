# Wiggle Gram — Upgrade Brief

## Role

You are the orchestrator. You plan, reason, and verify. You do not edit code directly. All code changes go through Codex CLI. When you need a change made, invoke Codex with a precise instruction. Review what it produces before proceeding.

---

## Context

`wigglegram.html` is a single-file portable HTML app that generates synthetic wiggle grams from a still image. It currently has three effect modes:

1. **Luminance proxy** — no depth model, treats pixel brightness as depth, used as a fast proof of concept
2. **Parallax / Warp** — depth-based pixel shifting using a user-supplied depth map (or luminance fallback); two sub-modes (forward-mapped parallax and backward-mapped warp)
3. **Orbit** — full 3D reprojection: unprojects pixels to world coordinates using the depth map, applies a yaw rotation, reprojects back; exposes holes at occlusion edges filled with a single-pass horizontal neighbor copy

The app is desktop-only, runs entirely in the browser, no server, no external calls. Depth maps are user-supplied grayscale images. GIF export is handled with `gif.js`.

---

## What is wrong

**Mode 2/3 (depth-based modes) look like a sliding image.** The depth compositing does not produce enough visual separation. Two likely causes:

- Background is not blurred relative to foreground. A real wiggle gram has focus falloff — background should blur proportional to estimated depth distance from the in-focus plane.
- Occlusion gap fill is too simple. When a near pixel shifts, it leaves a hole. Currently filled with source image as a base, but the seam is visible.

---

## Upgrade plan

### Fix 1 — Depth-proportional background blur (apply to all depth-warp modes)

When compositing each frame, apply a Gaussian blur to pixels proportional to their depth value. Foreground (low depth value = near) gets no blur. Background (high depth value = far) gets blur up to a configurable max radius. Implement as a pre-blur step on the source image before warping: generate a blur stack (e.g., 5 discrete blur levels) and sample from the appropriate level per pixel based on depth. This is faster than per-pixel variable blur and avoids blur bleeding across depth edges.

### Fix 2 — Edge-aware occlusion fill (apply to forward-mapped parallax mode)

After the forward pass, unfilled pixels should be filled using an edge-aware neighbor search rather than a simple horizontal copy. Specifically: for each unfilled pixel, check both left and right neighbors and pick the one whose depth value is closer to the unfilled pixel's expected depth (derived from interpolation). This reduces the smearing artifact at foreground/background boundaries.

### Mode 4 — ml-sharp depth input

Add a fourth depth source option: **ml-sharp**. This is Apple's monocular depth model (`github.com/apple/ml-sharp`) run locally via Python. The user runs the model outside the browser and gets a `.ply` Gaussian splat file and/or a depth map PNG as output.

For Mode 4 in the app: accept a depth map PNG exported from the ml-sharp pipeline (same grayscale format as the existing depth map input). Route it through the existing orbit reprojection mode with tighter defaults (smaller angle range, more depth passes) since ml-sharp depth maps are higher quality and benefit from the physically accurate reprojection. Label this input "ml-sharp depth" in the UI and set it as a distinct input path so the user knows which pipeline produced the depth.

Add a collapsible help section in the UI explaining how to run ml-sharp locally to produce the depth PNG:
```
git clone https://github.com/apple/ml-sharp
cd ml-sharp
pip install -e .
python run_sharp.py --input your_image.jpg --output_dir ./output --save_depth
```
The depth map will be at `./output/depth.png`. Upload it as the depth map in this tool.

### Mode 5 — Splat wiggle

Add a fifth mode: **Splat Wiggle**. This accepts a `.ply` Gaussian splat file (produced by ml-sharp or any compatible pipeline) and renders it using `@mkkellogg/gaussian-splats-3d` loaded from CDN. Instead of user navigation, the viewer automates a small lateral camera oscillation (±configurable degrees, default ±3°) on a loop to produce the wiggle gram effect. The oscillation should be smooth (sine curve, not linear).

Export: add a "Record GIF" button that captures N frames of the oscillation loop and encodes with `gif.js` — same export pipeline as the existing modes.

The splat viewer should be isolated in its own canvas element. The existing 2D canvas pipeline is not used in this mode.

---

## Constraints

- Single HTML file. No build step. No npm. External libraries loaded from CDN only.
- No server calls, no API calls. Everything runs in the browser.
- Desktop-only gate is already implemented. Do not remove it.
- Do not break existing modes 1, 2, 3.
- Voice in UI labels: terse, lowercase, declarative. No marketing language. Match existing UI tone.
- The `gif.js` export pipeline is already working. Extend it, don't replace it.

---

## Libraries already in use

- `gif.js` (CDN) — GIF encoding
- Native Canvas 2D API — all rendering in modes 1–3

## New libraries to add (CDN)

- `@mkkellogg/gaussian-splats-3d` — for Mode 5 splat rendering
- `three.js` — required by gaussian-splats-3d (check if already present; if not, add)

---

## Codex workflow

For each change:
1. Reason about what needs to change and where in the file.
2. Write a precise Codex instruction specifying the function name, the change, and the expected behavior.
3. Run Codex. Review the diff.
4. Verify the change does not break adjacent logic before proceeding to the next.

Work in this order:
1. Fix 1 (blur stack)
2. Fix 2 (occlusion fill)
3. Mode 4 (ml-sharp depth input + UI)
4. Mode 5 (splat wiggle + GIF export)
