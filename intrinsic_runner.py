"""Intrinsic decomposition for the wigglegram companion server.

Backend: Marigold-IID "Lighting" (prs-eth/marigold-iid-lighting-v1-1) via the
diffusers pipeline. It decomposes a photo as  I = Albedo * Shading + Residual,
which maps 1:1 onto the app's relight model: albedo feeds the relit splat,
the non-diffuse residual is the specular map, the shading is discarded (the
shader synthesizes new shading). Runs at 768px in a few steps — orders of
magnitude faster than the previous IntrinsicAnything backend, with a usable
license (CreativeML OpenRAIL++-M). Weights (~2GB) auto-download on first use.

    decompose_full(image_rgb_u8, hq=False) -> (albedo, specular, shading) u8

Albedo gets high-frequency detail re-injected from the original photo
(the diffusion works at 768px; fine detail above that is transferred back
multiplicatively).
"""
import numpy as np
import torch
from loguru import logger

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_PIPE = None


def weights_available():
    """Marigold auto-downloads from the HF hub; intrinsic support just needs
    diffusers with the Marigold pipelines (>= 0.34)."""
    try:
        import diffusers
        return hasattr(diffusers, "MarigoldIntrinsicsPipeline")
    except Exception:  # noqa: BLE001
        return False


def get_pipe():
    global _PIPE
    if _PIPE is None:
        import diffusers
        logger.info("Loading Marigold-IID (lighting) pipeline...")
        _PIPE = diffusers.MarigoldIntrinsicsPipeline.from_pretrained(
            "prs-eth/marigold-iid-lighting-v1-1",
            variant="fp16", torch_dtype=torch.float16,
        )
        logger.info("Marigold-IID ready.")
    _PIPE.to(DEVICE)
    return _PIPE


def offload_models():
    """Free VRAM between requests so the browser's WebGL splat viewer isn't
    starved. Marigold is small (~2GB) and cheap to shuttle back."""
    if _PIPE is not None:
        _PIPE.to("cpu")
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    logger.info("Marigold pipeline offloaded to CPU; VRAM freed.")


def reinject_detail(albedo_u8, original_u8, radius=8):
    """Multiply the albedo by the ORIGINAL photo's high-frequency ratio
    (orig / blur(orig)): fine detail — faces, hair, fabric weave — comes back
    from the photo while the albedo keeps its shading-free colors and the
    low-frequency shading stays removed."""
    import cv2
    alb = albedo_u8.astype(np.float32)
    orig = original_u8.astype(np.float32)
    k = (2 * radius + 1, 2 * radius + 1)
    blur_o = cv2.GaussianBlur(orig, k, 0)
    detail = (orig + 1.0) / (blur_o + 1.0)
    return np.clip(alb * detail, 0, 255).astype(np.uint8)


def decompose_full(image_rgb_u8, hq=False, ddim_steps=None):
    """image_rgb_u8: HxWx3 uint8. Returns (albedo, specular, shading), each
    HxWx3 uint8 at source resolution. hq trades time for an ensemble."""
    from PIL import Image

    pipe = get_pipe()
    img = Image.fromarray(image_rgb_u8)
    steps = ddim_steps or (10 if hq else 4)
    kwargs = {"num_inference_steps": steps}
    if hq:
        kwargs["ensemble_size"] = 3

    with torch.no_grad():
        result = pipe(img, **kwargs)
    vis = pipe.image_processor.visualize_intrinsics(
        result.prediction, pipe.target_properties)

    def to_u8(pil_img):
        arr = np.array(pil_img.convert("RGB"))
        if arr.shape[:2] != image_rgb_u8.shape[:2]:
            arr = np.array(Image.fromarray(arr).resize(
                (image_rgb_u8.shape[1], image_rgb_u8.shape[0]), Image.LANCZOS))
        return arr

    albedo = reinject_detail(to_u8(vis[0]["albedo"]), image_rgb_u8)
    specular = to_u8(vis[0]["residual"])
    shading = to_u8(vis[0]["shading"])
    return albedo, specular, shading
