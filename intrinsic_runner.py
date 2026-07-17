"""In-memory IntrinsicAnything wrapper for the wigglegram companion server.

Uses the HF Space code (vendored in ./IntrinsicAnythingSpace, downloaded via
`hf download LittleFrog/IntrinsicAnything --repo-type space`) because its
InferenceModel takes in-memory tensors; the GitHub repo's only reads/writes
directories. Weights come from the model repo (see README).

    decompose(image_rgb_u8, kind="albedo"|"specular", hq=False) -> HxWx3 uint8

Scene-level: the whole image is foreground (all-ones mask). Fast mode is one
low-res diffusion pass; HQ additionally runs a 2x2-tiled guided pass at higher
step count (slower, sharper).
"""
import sys
from pathlib import Path

import numpy as np
import torch
from loguru import logger

IA_ROOT = Path(__file__).resolve().parent / "IntrinsicAnythingSpace"
sys.path.insert(1, str(IA_ROOT))
sys.path.insert(1, str(IA_ROOT / "models"))

from inference import InferenceModel  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_MODELS = {}


def weights_available():
    return all(
        (IA_ROOT / "weights" / k / "checkpoints" / "last.ckpt").exists()
        for k in ("albedo", "specular")
    )


def get_model(kind):
    if kind not in _MODELS:
        logger.info(f"Loading IntrinsicAnything {kind} model...")
        _MODELS[kind] = InferenceModel(
            ckpt_path=str(IA_ROOT / "weights" / kind), use_ddim=True, gpu_id=DEVICE
        )
        logger.info(f"{kind} model ready.")
    # Model may have been offloaded to CPU after the previous request
    _MODELS[kind].model.model.to(DEVICE)
    return _MODELS[kind]


def offload_models():
    """Move IA models to CPU RAM and free VRAM. The diffusion models are used
    rarely (once per photo) but hold ~10GB of VRAM warm, which starves the
    browser's WebGL context when a large splat loads. CPU round-trip costs
    ~10-20s per request — much better than checkpoint reload from disk."""
    for kind, m in _MODELS.items():
        try:
            m.model.model.to("cpu")
        except Exception:  # noqa: BLE001
            logger.warning(f"offload of {kind} failed")
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    logger.info("IA models offloaded to CPU; VRAM freed.")


def decompose(image_rgb_u8, kind="albedo", hq=False, ddim_steps=50):
    """image_rgb_u8: HxWx3 uint8. Returns HxWx3 uint8 at source resolution."""
    model = get_model(kind)
    img = torch.from_numpy(image_rgb_u8.astype(np.float32) / 255.0).to(DEVICE)
    mask = torch.ones_like(img[..., :1])

    res = model.generation((1, 1), 1, None, img, mask, dps_scale=0, uc_score=1,
                           ddim_steps=ddim_steps, batch_size=1, n_samples=1)
    out = res["out_images"][0]

    if hq:
        guid = torch.from_numpy(out.astype(np.float32) / 255.0).to(DEVICE)
        res = model.generation((2, 2), 2, guid, img, mask, dps_scale=3, uc_score=1,
                               ddim_steps=max(80, ddim_steps), batch_size=1, n_samples=1)
        out = res["out_images"][0]

    # generation() returns the full-frame composite; resize guard just in case
    if out.shape[:2] != image_rgb_u8.shape[:2]:
        from PIL import Image
        out = np.array(Image.fromarray(out).resize(
            (image_rgb_u8.shape[1], image_rgb_u8.shape[0]), Image.LANCZOS))
    return out
