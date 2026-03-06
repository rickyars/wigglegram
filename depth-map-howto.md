# Depth Map How-To

## Option A: ARAG (Any-Resolution-Any-Geometry)

Highest quality. Chains Depth Anything V2 + Metric3D V2 + a URGT refiner for high-res depth and surface normals. Requires CUDA 12.4.

### Setup (one time)

```bash
git clone https://github.com/Dreamaker-MrC/Any-Resolution-Any-Geometry
cd Any-Resolution-Any-Geometry
pip install -r requirements.txt

mkdir -p work_dir/ckpts
huggingface-cli download Kingslanding/Any-Resolution-Any-Geometry ckpt_best.pth ckpt_promask_best.pth --local-dir work_dir/ckpts
```

### Run

```bash
cd Any-Resolution-Any-Geometry

python tools/infer.py \
    --image /path/to/photo.jpg \
    --checkpoint work_dir/ckpts/ckpt_promask_best.pth \
    --output-dir ./output
```

Use `ckpt_promask_best.pth` for arbitrary photos (zero-shot). Use `ckpt_best.pth` for U4K benchmark stuff.

### Convert to grayscale for wigglegram

ARAG outputs a turbo-colormapped PNG (for viewing) and a raw `.npy` (for processing). The wigglegram tool needs a grayscale PNG, so convert with:

```bash
python npy2gray.py output/photo_depth_pred.npy output/photo_depth_gray.png
```

`npy2gray.py` is in the wigglegram project root. Then drag `photo_depth_gray.png` into the "override depth map" slot.

### Output files

| File | What it is |
|------|------------|
| `photo_depth_pred.png` | Turbo-colormapped depth (for viewing) |
| `photo_depth_pred.npy` | Raw depth array (for processing) |
| `photo_normal_pred.png` | Surface normals (bonus) |
| `photo_depth_gray.png` | Grayscale depth after conversion (for wigglegram) |

### Optional flags

| Flag | Default | What it does |
|------|---------|-------------|
| `--save-intermediates` | off | Also save coarse depth/normal maps |
| `--dav2-encoder` | `vitl` | Depth Anything V2 backbone: `vits` / `vitb` / `vitl` / `vitg` |
| `--metric3d-model` | `ViT-Small` | Metric3D V2 variant: `ViT-Small` / `ViT-Large` / `ViT-giant2` |
| `--patch-split` | `8 8` | Patch grid NxN (image resized to be divisible) |
| `--min-depth` | `0.001` | Min depth in metres |
| `--max-depth` | `80.0` | Max depth in metres |

---

## Option B: Depth Anything V2

Simpler model, no normals, but much easier to set up. Works on CPU.

### Setup (one time)

```bash
git clone https://github.com/DepthAnything/Depth-Anything-V2
cd Depth-Anything-V2
pip install -r requirements.txt

mkdir checkpoints
# small (fast, 25M params):
huggingface-cli download depth-anything/Depth-Anything-V2-Small --include "*.pth" --local-dir checkpoints
# OR large (best quality, 335M params):
huggingface-cli download depth-anything/Depth-Anything-V2-Large --include "*.pth" --local-dir checkpoints
```

### Run

```bash
cd Depth-Anything-V2

python run.py --encoder vits --img-path /path/to/photo.jpg --outdir ./output --pred-only --grayscale
#              ^^^^^ use vitl if you downloaded Large
```

Output: grayscale PNG in `./output/`. Drag it into the "override depth map" slot. If the wiggle looks inverted, tick the "invert" checkbox.

---

## Option C: MiDaS (zero clone, just pip)

The classic. No git clone needed — loads from PyTorch Hub. Works on CPU.

### Setup (one time)

```bash
pip install torch torchvision timm opencv-python
```

### Run

Save this as `depth.py`:

```python
import cv2, torch, numpy as np, sys
img = cv2.imread(sys.argv[1])
midas = torch.hub.load("intel-isl/MiDaS", "DPT_Large").to("cuda" if torch.cuda.is_available() else "cpu").eval()
transform = torch.hub.load("intel-isl/MiDaS", "transforms").dpt_transform
with torch.no_grad():
    pred = midas(transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).to(next(midas.parameters()).device))
    pred = torch.nn.functional.interpolate(pred.unsqueeze(1), size=img.shape[:2], mode="bicubic").squeeze().cpu().numpy()
pred = ((pred - pred.min()) / (pred.max() - pred.min()) * 255).astype(np.uint8)
cv2.imwrite("depth.png", pred)
print("wrote depth.png")
```

```bash
python depth.py /path/to/photo.jpg
```

MiDaS outputs inverse depth (bright = near) which matches the wigglegram default convention.

---

## Notes

- All three work on CPU, but a GPU makes them much faster
- ARAG needs CUDA 12.4 specifically
- The wigglegram tool expects **bright = near** by default. If the wiggle looks wrong, tick the "invert" checkbox
