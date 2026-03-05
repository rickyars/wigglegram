"""Convert an ARAG .npy depth map to a grayscale PNG for the wigglegram tool.

Usage: python npy2gray.py input.npy output.png

Output convention: bright = near (small depth), dark = far (large depth).
This matches the wigglegram tool's default (no invert needed).
"""
import sys
import numpy as np
from PIL import Image

if len(sys.argv) < 3:
    print("Usage: python npy2gray.py input.npy output.png")
    sys.exit(1)

depth = np.load(sys.argv[1]).astype(np.float32)
lo, hi = depth.min(), depth.max()
normalized = (depth - lo) / (hi - lo + 1e-8)  # 0 = near, 1 = far
inverted = 1.0 - normalized                    # flip: bright = near
gray = (inverted * 255).astype(np.uint8)

Image.fromarray(gray).save(sys.argv[2])
print(f"wrote {sys.argv[2]}  ({gray.shape[1]}x{gray.shape[0]})")
