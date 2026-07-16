# Rotation-Synced Relighting via Intrinsic Decomposition — Design

**Date:** 2026-07-16
**Status:** Draft for review

## Problem

In depth-map parallax mode, reflections and shadows are baked into the source
photo. The depth map assigns those pixels the depth of the surface they appear
on, so during the wiggle they move rigidly with the surface instead of
behaving like light: reflections should parallax as if behind the glass, and
shadows should follow their occluder. Both read as "painted on" and break the
3D illusion.

## Approach

Remove baked lighting once, then re-add lighting synthetically, synced to the
camera rotation. Because we compute the shading ourselves, the light direction
is a function of the same rotation angle θ that drives the camera — sync is
exact by construction.

Research findings that shaped this (see `2404.11593`, repo
`zju3dv/IntrinsicAnything`):

- IntrinsicAnything's released single-view inference works on **scene-level
  images without masks** and outputs **albedo** (shading-free color) and
  **specular shading** maps via two diffusion models.
- It does **not** ship a relight function. All relighting in the paper is
  multi-view (SDF geometry supplies normals). GitHub issue #3 requesting the
  single-view relight script has been open, unanswered, since Sept 2024.
- The paper's own Section 3 rendering equation (diffuse + microfacet specular
  with normals) is the shading model to reimplement. The only unpublished
  input is the normals source; we derive normals from the DA3 depth map
  (gradient-based), already produced by the companion.

## Pipeline

```
photo ──► companion /intrinsic ──► albedo (+ specular map, stored)
photo ──► companion /depth     ──► depth ──► normals (in-browser, from gradients)
albedo ──► companion /predict  ──► ONE splat (geometry fixed for all frames)
render loop: θ ──► camera pose AND lightDir(θ)
             frame = albedo-textured splat × shading(normals, lightDir) [+ specular]
```

Key decision — **one splat, not one per frame.** Per-frame splats (relight
image, then run ml-sharp per frame) were considered and rejected: ml-sharp
geometry depends on pixel content, so independently generated splats jitter
geometrically frame-to-frame, diffusion relights flicker, and compute is
N × (relight + splat). One splat built from the albedo image keeps geometry
identical across the wiggle; only shading varies.

## Components

### 1. Companion server (`wigglegram-companion.py`)

- New endpoint `POST /intrinsic`: image bytes in → JSON out with base64-encoded
  `albedo` and `specular` PNGs in one response (both maps come from one
  request so the two diffusion passes share preprocessing and the browser
  never holds a half-decomposed state).
- Runs IntrinsicAnything `inference.py` models (two diffusion checkpoints,
  weights vendored under the existing `Depth-Anything-3`-style layout).
  Diffusion inference takes seconds–tens of seconds per image on CUDA; the
  endpoint is synchronous like `/predict`, with the browser showing busy
  state.
- `/health` response gains `"intrinsic": true|false` so the browser can
  feature-detect (older companion keeps working).

### 2. Browser: relight shading pass (`wigglegram.html`)

- Normals: computed from the depth texture via screen-space gradients in the
  shader (same texture the parallax already samples). No new model.
- Shading model: Lambertian diffuse `max(dot(n, l), 0)` plus a Blinn-Phong /
  simplified microfacet specular term modulated by IntrinsicAnything's
  specular map. Ambient floor parameter so shadows never crush to black.
- `lightDir(θ)`: light azimuth = camera rotation angle × gain + offset, both
  Tweakpane params. Elevation is a third param. Gain 0 = static light;
  gain 1 = light locked to camera (flash-like).
- This pass extends the existing synthetic-flash compositor (`SplatDepthSource`
  `_compositor`); flash becomes one preset of the relight system rather than
  a separate effect.
- Tweakpane: new "Relight" folder — enable toggle, light gain/offset/elevation,
  ambient, specular strength, original↔albedo blend slider (full albedo can
  look sterile; blending restores some photographic texture).

### 3. Browser: workflow changes

- **Remove luminance mode.** Delete `LuminanceDepthSource`,
  `computeLuminanceDepth`, and their call sites (~7 paths, including the
  tagline at line 326 and fallback at 1637/1668). With no depth available the
  UI shows an explicit "no depth — generate or upload" state instead of a
  luminance guess.
- **Stop depth auto-run.** Remove the `estimateAIDepth(canvas)` call from the
  image-load handler (line ~1397); add a "Generate depth" button next to the
  existing companion splat button. Depth runs only on click (or when a depth
  image is uploaded manually — unchanged).

## Error handling

- Companion absent or `/intrinsic` unsupported → Relight folder hidden;
  app behaves as today (minus luminance mode).
- `/intrinsic` failure (OOM, model error) → status message, photo remains
  usable un-relit.
- Albedo/specular resolution mismatch with source → browser rescales to
  source dimensions on load (same as depth handling today).

## Testing

- Companion: golden-image test — run `/intrinsic` on 2–3 `test-images/`,
  eyeball albedo has shadows removed; verify endpoint returns valid PNG and
  `/health` flag.
- Browser: manual checklist — relight off = current behavior; θ sweep shows
  light moving with rotation with zero lag; ambient/gain sliders behave;
  export (GIF/MP4) frames match live preview; no-companion path degrades
  cleanly; luminance code fully gone (grep).

## Milestones

1. **M4a — Workflow cleanup:** remove luminance mode; depth auto-run → button.
   (Independent, ships first, shrinks the file before shader work.)
2. **M4b — Companion `/intrinsic`:** IntrinsicAnything integration + endpoint.
3. **M4c — Relight shader:** normals-from-depth, shading pass, θ-synced light,
   Tweakpane folder, flash unified as preset, export parity.
4. **M5 (future, out of scope here):** layered reflection rendering for planar
   mirrors/windows using the reflection/specular residual with mirrored depth.

## Rejected alternatives

- **Per-frame relit splats** — geometry jitter, diffusion flicker, N× compute.
- **IC-Light keyframe textures** — more photoreal but adds a second heavy
  model and blend softness; revisit only if shader relight looks too "CG".
- **Dedicated normals estimator (StableNormal/Marigold-normals)** — upgrade
  path if depth-derived normals prove too coarse on smooth surfaces; not in
  initial scope.
- **Shadow-removal + reflection-removal specialist models** — superseded by
  intrinsic decomposition, which addresses shadows and specular reflections
  in one model. Diffuse mirror reflections (scene content in a mirror) are
  NOT fixed by this design; deferred to M5.
