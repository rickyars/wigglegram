# Design: Splat Camera Auto-Fit + Download Button Fix

**Date:** 2026-04-09
**File:** `wigglegram.html` (single-file app)

---

## Summary

Two fixes:
1. Download button is unstyled (plain browser default). Make it match the generate button's green-box style.
2. Splat camera uses a raw world-unit distance slider that ignores scene scale, causing the splat to appear tiny in a void. Replace with bounding-box auto-fit on load + a dimensionless zoom multiplier slider.

---

## Fix 1 — Download Button Styling

**Problem:** `button#downloadBtn` has class `download-btn` but no matching CSS. It renders as a plain browser button.

**Solution:** Add a `button#downloadBtn` CSS rule styled identically to `button#generateBtn`:
- Transparent background, `1px solid var(--green)`, green text
- Uppercase, `letter-spacing: 0.12em`, same font and padding as the generate button
- Hover: fill green background, black text
- Width: `auto` (not `100%`) — the button sits inline next to the "output" label in the preview panel header

---

## Fix 2 — Splat Camera Auto-Fit + Zoom Multiplier

**Problem:** On load, `SplatDepthSource` correctly retrieves the bounding box center but ignores the bounding box size when positioning the camera. `distance` is always set to `PARAMS.splatDistance` regardless of scene scale. A tiny scene at distance 3.0 looks like a dot in a void.

**Solution:**

### On load (inside `SplatDepthSource.load()`)

After resolving the bounding box:
1. Get bounding sphere: `bbox.getBoundingSphere(new THREE.Sphere())`
2. Compute auto-fit distance:
   ```
   const fovRad = (Math.PI / 180) * 60   // matches camera FOV
   autoFitDist = sphere.radius / Math.sin(fovRad / 2)
   ```
3. Store as `this._autoFitDist = autoFitDist`
4. Position camera at `autoFitDist * PARAMS.splatZoom`
5. Fallback: if bbox is empty or sphere radius is 0, use `this._autoFitDist = 3.0`

### repositionCamera()

Update signature to use the multiplier:
```
repositionCamera(zoomMultiplier) {
  const dist = (this._autoFitDist || 3.0) * zoomMultiplier
  // ... rest unchanged
}
```

### Tweakpane binding

Remove `splatDistance` binding. Add `splatZoom` binding:
- Label: `zoom`
- `min: 0.1`, `max: 3.0`, `step: 0.05`, default `1.0`
- On change: call `activeDepthSource.repositionCamera(PARAMS.splatZoom)` if `activeDepthSource` is a `SplatDepthSource`

### PARAMS

Remove `splatDistance: 3`. Add `splatZoom: 1.0`.

---

## What Is Not Changing

- The two processing paths (`LuminanceDepthSource`, `ImageDepthSource`, `SplatDepthSource`) are kept as-is. The `captureFrame` interface is already unified. No path rewrite.
- Camera FOV, near/far planes, and the oscillation logic are unchanged.
- All code changes are made via Codex CLI (Claude orchestrates, does not edit files directly).
