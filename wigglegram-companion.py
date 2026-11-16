"""Local companion server: wraps ml-sharp so the wigglegram app can generate
gaussian splats from within the browser.

Usage:
    python wigglegram-companion.py

Then open http://127.0.0.1:8765/ (the companion serves wigglegram.html with
no-cache headers, so edits show up on a plain reload). A "generate splat
(ml-sharp)" button appears when the companion is detected. The SHARP model is
loaded on the first /predict (first run downloads the checkpoint via
torch.hub, cached) and parked on the CPU between requests so it doesn't hold
VRAM that ComfyUI needs.

Endpoints (127.0.0.1:8765):
    GET  /         -> wigglegram.html (Cache-Control: no-store)
    GET  /health   -> {"ok": true, "device": "cuda", "intrinsic": bool, "flash": bool}
    GET  /progress -> {"task": "flash"|"depth"|..., "stage": str, "step", "total",
                       "waiting": n}; the page polls it once a second while a job
                      runs (Qwen sampler steps come from ComfyUI's websocket)
    POST /flash    -> body: image bytes; response: PNG, the same photo relit
                      with a harsh on-camera flash by Qwen-Image-Edit 2511 in
                      the local ComfyUI (127.0.0.1:8188; needs the
                      attention-override custom node, see README). ?seed=N,
                      ?prompt=<override>, ?keep=color (default: Qwen's light
                      and shadow with the photo's colors), keep=photo (the
                      original photo with only Qwen's soft light transferred;
                      subtler), keep=none (raw Qwen). Run it BEFORE depth/splat: a real
                      wigglegram camera fires one flash for all lenses, so the
                      light is fixed in the world and one relit source is right.
    POST /predict  -> body: image bytes; response: .ply bytes (ml-sharp splat)
    POST /depth    -> body: image bytes; response: grayscale PNG depth map
                      (Marigold-Depth, bright = near; lazy-loaded on first
                      call, VRAM released after each request)
    POST /intrinsic -> body: image bytes; response JSON:
                      {"albedo","specular","shading","normals": <base64 PNG>}
                      (Marigold-IID lighting decomposition + Marigold-Normals
                      surface normal estimation; lazy-loaded. ?hq=1 for more
                      steps + ensembling.)
"""
import functools
import http.server
import json
import logging
import sys
import tempfile
import threading
import types
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("companion")

# ml-sharp imports gsplat (CUDA renderer) at module level, but prediction
# doesn't need it — stub it out so we don't need the compiled extension.
try:
    import gsplat  # noqa: F401
except ImportError:
    sys.modules["gsplat"] = types.ModuleType("gsplat")

import torch  # noqa: E402
from sharp.cli.predict import DEFAULT_MODEL_URL, predict_image  # noqa: E402
from sharp.models import PredictorParams, create_predictor  # noqa: E402
from sharp.utils import io as sharp_io  # noqa: E402
from sharp.utils.gaussians import save_ply  # noqa: E402

HOST, PORT = "127.0.0.1", 8765

DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

APP_HTML = Path(__file__).with_name("wigglegram.html")
COMFY_URL = "http://127.0.0.1:8188"
PREDICTOR = None  # SHARP, loaded on first /predict


def get_predictor():
    global PREDICTOR
    if PREDICTOR is None:
        LOGGER.info("Loading SHARP model (device=%s)...", DEVICE)
        set_progress("loading SHARP model (first run downloads it)")
        state_dict = torch.hub.load_state_dict_from_url(DEFAULT_MODEL_URL, progress=True)
        predictor = create_predictor(PredictorParams())
        predictor.load_state_dict(state_dict)
        predictor.eval()
        PREDICTOR = predictor  # only cache a fully loaded model
    return PREDICTOR


# Serialize GPU work across the threading server's request threads
GPU_LOCK = threading.Lock()

# What the GPU is doing right now, for GET /progress (the page polls it so a
# minute-long job shows its stage instead of looking hung)
PROGRESS = {"task": None, "stage": "", "step": 0, "total": 0, "waiting": 0}
PROGRESS_LOCK = threading.Lock()


def set_progress(stage=None, step=None, total=None):
    with PROGRESS_LOCK:
        if stage is not None:
            PROGRESS["stage"] = stage
            PROGRESS["step"], PROGRESS["total"] = 0, 0
        if step is not None:
            PROGRESS["step"] = step
        if total is not None:
            PROGRESS["total"] = total


# ─── Flash relight via ComfyUI (Qwen-Image-Edit 2511 + Lightning 8-step) ───
FLASH_PROMPT = (
    "Relight this photo as if it was taken with a harsh direct on-camera flash, like a point-and-shoot "
    "film camera at night: the flash fires from the camera lens straight at the subject. Bright, hard, "
    "frontal light on the faces and the nearest surfaces, a thin hard-edged shadow just behind the "
    "subject on the surface behind them, and the background falls off darker with distance from the "
    "camera. Keep every person, face, expression, pose, object and the framing exactly the same. Keep "
    "all of the photo's original colors, hues and saturation exactly as they are. Natural matte skin, "
    "no added makeup, no sweat or wet sheen. Change only the lighting."
)
# 2026-11-12: the v2 wording "(a sepia or black-and-white photo stays sepia or black-and-white)"
# turned a COLOR photo black-and-white; never mention B&W. restore_color() also guards against it.
# 2026-11-11 first real run (woman-in-chair, seed 1): the old prompt's "crisp specular highlights on
# skin" gave a wet/sweaty sheen, and Qwen colorized the sepia photo + added makeup. light_transfer()
# below makes those mostly moot by keeping the photo and taking only Qwen's light.


def restore_color(photo, relit, sigma=3.0):
    """Qwen's light and shadow, the photo's colors (keep=color, the default).
    Lab: lightness from the relight, a/b from the photo. a/b are blurred a
    little so Qwen's few-pixel drift doesn't fringe edges, and scaled down
    where Qwen darkened (dark + full chroma looks neon) but never boosted
    where it brightened, so flash hot spots wash out like a real flash."""
    import cv2
    import numpy as np
    lp = cv2.cvtColor(photo, cv2.COLOR_RGB2LAB)
    lr = cv2.cvtColor(relit, cv2.COLOR_RGB2LAB)
    ab = cv2.GaussianBlur(lp[..., 1:], (0, 0), sigma)
    scale = np.clip((lr[..., 0] + 2) / (cv2.GaussianBlur(lp[..., 0], (0, 0), sigma) + 2), 0, 1)
    out = np.dstack([lr[..., 0], ab * scale[..., None]]).astype(np.float32)
    return np.clip(cv2.cvtColor(out, cv2.COLOR_LAB2RGB), 0, 1)


def light_transfer(photo, relit, floor=0.2, ceil=6.0):
    """Keep the photo, take only the relight's light: out = photo * ratio, where
    ratio = relit/photo luminance, smoothed edge-aware (guided filter, guide =
    photo luminance) so the light change stops at the subject's outline.

    Why: Qwen's output is ~1MP (soft when scaled back up), "beautifies" faces
    (makeup, eye color), adds skin sheen and colorizes toned photos. All of
    that is fine detail or chroma; the light is low-frequency luminance. A
    Gaussian-blurred ratio left a glow around the silhouette (2026-11-11 A/B);
    the guided filter fixed it. floor 0.2 keeps detail in crushed shadows.
    photo, relit: float32 HxWx3 in [0,1], same size.
    """
    import cv2
    import numpy as np

    w = np.array([0.2126, 0.7152, 0.0722], np.float32)
    g = photo @ w
    # pre-blur 3px so Qwen's pore/speckle/makeup texture doesn't enter the ratio
    lr = np.log((cv2.GaussianBlur(relit @ w, (0, 0), 3) + 0.01) / (cv2.GaussianBlur(g, (0, 0), 3) + 0.01))
    r = max(4, int(0.012 * min(g.shape)))

    def box(x):
        return cv2.blur(x, (2 * r + 1, 2 * r + 1))

    guide = np.log(g + 0.01)
    mI, mp = box(guide), box(lr)
    a = (box(guide * lr) - mI * mp) / (box(guide * guide) - mI * mI + 0.02)
    b = mp - a * mI
    ratio = np.clip(np.exp(box(a) * guide + box(b)), floor, ceil)
    return np.clip(photo * ratio[..., None], 0, 1)


def flash_graph(image_name: str, prompt: str, seed: int) -> dict:
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2511_fp8mixed.safetensors", "weight_dtype": "default"}},
        # Qwen-Image renders black (NaN) under --use-sage-attention: opt this one model back to PyTorch SDPA
        "attn": {"class_type": "AttentionOverridePytorch", "inputs": {"model": ["unet", 0]}},
        "aura": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["attn", 0], "shift": 3.1}},
        "cfgn": {"class_type": "CFGNorm", "inputs": {"model": ["aura", 0], "strength": 1}},
        "lora": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["cfgn", 0], "lora_name": "Qwen-Image-Edit-2511-Lightning-8steps-V1.0-fp32.safetensors", "strength_model": 1}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "img": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "sc": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["img", 0]}},
        "enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["sc", 0], "vae": ["vae", 0]}},
    }
    for k, text in (("pos", prompt), ("neg", "")):
        g[k + "e"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["clip", 0], "vae": ["vae", 0], "image1": ["sc", 0], "prompt": text}}
        g[k] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": [k + "e", 0], "reference_latents_method": "index_timestep_zero"}}
    g["ks"] = {"class_type": "KSampler", "inputs": {"model": ["lora", 0], "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["enc", 0],
                                                    "seed": seed, "steps": 8, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}}
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}}
    g["save"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "wigglegram/flash", "images": ["dec", 0]}}
    return g


def comfy_json(path: str, payload=None, timeout=10):
    import urllib.request
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(COMFY_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else {}


_FLASH_OK_UNTIL = 0.0


def flash_supported() -> bool:
    # Called by every /health: remember a yes for a minute so /health stays
    # fast; a no is re-checked (quickly) so starting ComfyUI later shows up
    global _FLASH_OK_UNTIL
    import time
    if time.time() < _FLASH_OK_UNTIL:
        return True
    try:
        ok = "AttentionOverridePytorch" in comfy_json("/object_info/AttentionOverridePytorch", timeout=1)
    except Exception:  # noqa: BLE001
        ok = False
    if ok:
        _FLASH_OK_UNTIL = time.time() + 60
    return ok


COMFY_NODE_STAGES = {"unet": "loading Qwen-Image-Edit (cold start)", "lora": "loading Lightning LoRA",
                     "clip": "loading text encoder", "vae": "loading VAE",
                     "enc": "encoding photo", "pose": "encoding prompt", "nege": "encoding prompt",
                     "pos": "encoding prompt", "neg": "encoding prompt",
                     "ks": "Qwen sampling", "dec": "decoding image", "save": "saving"}


def watch_comfy_progress(client_id, stop):
    """Mirror ComfyUI's websocket progress (current node, sampler step) into
    PROGRESS. Best effort: if the socket fails the job still completes via the
    /history poll; the page just shows fewer details."""
    try:
        from websockets.sync.client import connect
        ws_url = COMFY_URL.replace("http", "ws", 1) + "/ws?clientId=" + client_id
        with connect(ws_url, open_timeout=5, max_size=None) as ws:
            while not stop.is_set():
                try:
                    msg = ws.recv(timeout=0.5)
                except TimeoutError:
                    continue
                if not isinstance(msg, str):
                    continue  # binary preview frames
                m = json.loads(msg)
                d = m.get("data", {})
                if m.get("type") == "executing" and d.get("node"):
                    set_progress(COMFY_NODE_STAGES.get(d["node"], "ComfyUI: " + d["node"]))
                elif m.get("type") == "progress":
                    set_progress(step=d.get("value", 0), total=d.get("max", 0))
    except Exception as e:  # noqa: BLE001
        LOGGER.info("flash: no ComfyUI progress stream (%s)", e)


def run_flash(image_bytes: bytes, prompt: str, seed: int, keep: str = "color") -> bytes:
    import io as std_io
    import time
    import urllib.error
    import urllib.parse
    import urllib.request
    import uuid

    from PIL import Image, ImageOps

    src = Image.open(std_io.BytesIO(image_bytes))
    # Bake the EXIF rotation into the pixels, then carry the rest of the EXIF
    # (ml-sharp reads FocalLengthIn35mmFilm from it) over to the relit PNG.
    exif = src.getexif()
    src = ImageOps.exif_transpose(src)
    if 0x0112 in exif:
        exif[0x0112] = 1  # Orientation: already applied
    size = src.size
    png = std_io.BytesIO()
    src.convert("RGB").save(png, format="PNG")

    set_progress("checking ComfyUI")
    try:
        comfy_json("/queue", timeout=3)
    except Exception:  # noqa: BLE001
        raise RuntimeError(f"ComfyUI isn't answering at {COMFY_URL}. Start it (or wait until its "
                           "console says it's listening; startup takes a minute or two), then try again.") from None
    if not flash_supported():
        raise RuntimeError("ComfyUI is running but the attention-override custom node isn't loaded "
                           "(see README: Harsh flash relight). Install it and restart ComfyUI.")
    set_progress("uploading photo to ComfyUI")
    # multipart upload to ComfyUI's input dir
    boundary = uuid.uuid4().hex
    name = f"wigglegram-flash-{boundary[:8]}.png"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + png.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(COMFY_URL + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        up = json.loads(r.read())
    image_name = f"{up['subfolder']}/{up['name']}" if up.get("subfolder") else up["name"]

    LOGGER.info("flash: queue Qwen-Image-Edit 2511 relight (seed=%d)...", seed)
    t0 = time.time()
    client_id = "wigglegram-" + uuid.uuid4().hex[:8]
    stop_ws = threading.Event()
    threading.Thread(target=watch_comfy_progress, args=(client_id, stop_ws), daemon=True).start()
    pid, done = None, False
    try:
        set_progress("queued in ComfyUI")
        try:
            res = comfy_json("/prompt", {"prompt": flash_graph(image_name, prompt, seed), "client_id": client_id})
        except urllib.error.HTTPError as e:
            # ComfyUI answers a bad graph (missing model file, bad input) with HTTP 400 + node_errors
            try:
                res = json.loads(e.read())
            except Exception:  # noqa: BLE001
                res = {"error": f"HTTP {e.code}"}
        pid = res.get("prompt_id")
        if not pid:
            raise RuntimeError("ComfyUI refused the graph: " + json.dumps(res.get("node_errors") or res.get("error"))[:800])
        while True:
            time.sleep(1.0)
            if time.time() - t0 > 900:
                raise RuntimeError("ComfyUI flash relight timed out after 15 min")
            entry = comfy_json(f"/history/{pid}").get(pid)
            if not entry:
                continue
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError("ComfyUI error: " + json.dumps(status.get("messages"))[:800])
            imgs = entry.get("outputs", {}).get("save", {}).get("images")
            if imgs:
                break
            if status.get("completed"):
                raise RuntimeError("ComfyUI finished without an image (interrupted from the ComfyUI UI?)")
        set_progress("downloading result")
        im = imgs[0]
        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
        with urllib.request.urlopen(f"{COMFY_URL}/view?{q}", timeout=30) as r:
            out = Image.open(std_io.BytesIO(r.read())).convert("RGB")
        done = True
    finally:
        stop_ws.set()
        if pid and not done:
            # Failed or timed out: don't leave the job queued/running on the GPU
            for path, payload in (("/queue", {"delete": [pid]}), ("/interrupt", {})):
                try:
                    comfy_json(path, payload, timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        # Release ComfyUI's VRAM (~20GB Qwen) on every path, so SHARP /
        # Marigold / the WebGL viewer aren't starved after a failure either
        set_progress("freeing ComfyUI VRAM")
        try:
            comfy_json("/free", {"unload_models": True, "free_memory": True})
        except Exception:  # noqa: BLE001
            LOGGER.info("flash: could not ask ComfyUI to free VRAM")
    LOGGER.info("flash: done in %.1fs", time.time() - t0)
    # Qwen works at its own ~1MP size; scale back to the photo's exact size so depth/splat align
    out = out.resize(size, Image.LANCZOS)
    if keep in ("photo", "color"):
        import numpy as np
        photo = np.asarray(src.convert("RGB"), dtype=np.float32) / 255
        relit = np.asarray(out, dtype=np.float32) / 255
        if keep == "photo":
            set_progress("transferring the light onto your photo")
            res = light_transfer(photo, relit)
        else:
            # Safety net, not a filter: raw Qwen colors look richest when it
            # keeps them, so restore only if it drained them (it once turned
            # a color photo B&W; restore_color slightly dulls a good result)
            import cv2

            def chroma(im):
                return float(np.abs(cv2.cvtColor(im, cv2.COLOR_RGB2LAB)[..., 1:]).mean())
            kept = chroma(relit) / max(chroma(photo), 1e-3)
            LOGGER.info("flash: Qwen kept %.0f%% of the photo's color", 100 * kept)
            # measured 2026-11-12: drained-to-B&W run kept 12%, a good run 70%
            # (a flash darkens the background, so some loss is normal)
            if kept < 0.4:
                set_progress("Qwen drained the color; restoring your photo's colors")
                res = restore_color(photo, relit)
            else:
                res = relit
        out = Image.fromarray((res * 255 + 0.5).astype(np.uint8))
    buf = std_io.BytesIO()
    out.save(buf, format="PNG", exif=exif.tobytes())
    return buf.getvalue()


def run_depth(image_bytes: bytes, suffix: str) -> bytes:
    global INTRINSIC_RUNNER
    if INTRINSIC_RUNNER is None:
        import intrinsic_runner
        INTRINSIC_RUNNER = intrinsic_runner
    import io as std_io

    import numpy as np
    from PIL import Image

    img = np.array(Image.open(std_io.BytesIO(image_bytes)).convert("RGB"))
    LOGGER.info("depth: Marigold-Depth estimate...")
    set_progress("Marigold depth")
    gray = INTRINSIC_RUNNER.estimate_depth(img)
    INTRINSIC_RUNNER.offload_models()
    buf = std_io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="PNG")
    return buf.getvalue()


INTRINSIC_RUNNER = None


@functools.lru_cache(maxsize=None)
def intrinsic_supported() -> bool:
    # Cached: probing diffusers' lazy module costs ~5s, which made every
    # /health slow (the reason the browser probe needed a 6s timeout)
    try:
        import intrinsic_runner
        return intrinsic_runner.weights_available()
    except Exception:  # noqa: BLE001
        return False


def run_intrinsic(image_bytes: bytes, hq: bool, steps: int) -> bytes:
    global INTRINSIC_RUNNER
    if INTRINSIC_RUNNER is None:
        import intrinsic_runner
        INTRINSIC_RUNNER = intrinsic_runner
    import base64
    import io as std_io

    import numpy as np
    from PIL import Image

    img = np.array(Image.open(std_io.BytesIO(image_bytes)).convert("RGB"))

    def to_b64(arr):
        buf = std_io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    LOGGER.info("intrinsic: Marigold-IID decompose (hq=%s)...", hq)
    set_progress("Marigold-IID: albedo / shading / specular (1/2)")
    albedo, specular, shading = INTRINSIC_RUNNER.decompose_full(img, hq=hq)
    LOGGER.info("intrinsic: Marigold-Normals estimate...")
    set_progress("Marigold-Normals: surface normals (2/2)")
    normals = INTRINSIC_RUNNER.estimate_normals(img, hq=hq)
    # Free VRAM so the browser's WebGL splat viewer isn't starved
    INTRINSIC_RUNNER.offload_models()
    return json.dumps({"albedo": to_b64(albedo), "specular": to_b64(specular),
                       "shading": to_b64(shading),
                       "normals": to_b64(normals)}).encode()


def run_predict(image_bytes: bytes, suffix: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / ("input" + suffix)
        img_path.write_bytes(image_bytes)
        image, _, f_px = sharp_io.load_rgb(img_path)
        height, width = image.shape[:2]
        LOGGER.info("Predicting gaussians for %dx%d image...", width, height)
        predictor = get_predictor()
        set_progress("SHARP: predicting gaussians")
        try:
            # inside the try: an OOM partway through the move still parks it back on the CPU
            predictor.to(DEVICE)
            gaussians = predict_image(predictor, image, f_px, torch.device(DEVICE))
        finally:
            predictor.to("cpu")  # park off-GPU between requests (ComfyUI shares this card)
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
        set_progress("writing .ply")
        ply_path = Path(tmp) / "output.ply"
        save_ply(gaussians, f_px, (height, width), ply_path)
        return ply_path.read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body=None, mime="application/json", headers=None):
        """Send a full response, tolerating clients that disconnected midway
        (closed/refreshed tabs abort the socket -> WinError 10053; that's the
        client's problem, not ours — log one line instead of a traceback)."""
        try:
            self.send_response(code)
            self._cors()
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if body is not None:
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body is not None:
                self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            LOGGER.info("client disconnected before response completed (%s)", self.path)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome Private Network Access preflight
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/health":
            body = json.dumps({"ok": True, "device": DEVICE,
                               "intrinsic": intrinsic_supported(),
                               "flash": flash_supported()}).encode()
            self._send(200, body)
        elif route == "/progress":
            with PROGRESS_LOCK:
                body = json.dumps(PROGRESS).encode()
            self._send(200, body, headers={"Cache-Control": "no-store"})
        elif route in ("/", "/wigglegram.html"):
            # Served from here so a plain reload always gets the current file
            # (Chrome cached file:// / static-server copies aggressively)
            self._send(200, APP_HTML.read_bytes(), "text/html; charset=utf-8",
                       {"Cache-Control": "no-store"})
        elif route.startswith("/assets/"):
            # The page's relative assets (blue-noise texture); stay inside assets/
            import mimetypes
            from urllib.parse import unquote
            assets = APP_HTML.parent / "assets"
            f = (assets / unquote(route[len("/assets/"):])).resolve()
            if f.is_file() and assets.resolve() in f.parents:
                self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            else:
                self._send(404)
        else:
            self._send(404)

    def do_POST(self):
        route = self.path.split("?")[0]
        if route not in ("/predict", "/depth", "/intrinsic", "/flash"):
            self._send(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(n)
            ctype = self.headers.get("Content-Type", "")
            suffix = ".png" if "png" in ctype else ".jpg"
            with PROGRESS_LOCK:
                PROGRESS["waiting"] += 1
            with GPU_LOCK:
                with PROGRESS_LOCK:
                    PROGRESS["waiting"] -= 1
                    PROGRESS.update(task=route[1:], stage="starting", step=0, total=0)
                try:
                    body, mime = self._run(route, data, suffix)
                finally:
                    with PROGRESS_LOCK:
                        PROGRESS.update(task=None, stage="", step=0, total=0)
            self._send(200, body, mime)
            LOGGER.info("%s returned %.1f MB", route, len(body) / 1048576)
        except Exception as e:  # noqa: BLE001
            LOGGER.exception("%s failed", route)
            self._send(500, json.dumps({"error": str(e)}).encode())

    def _run(self, route, data, suffix):
        if route == "/depth":
            body = run_depth(data, suffix)
            mime = "image/png"
        elif route == "/intrinsic":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            hq = q.get("hq", ["0"])[0] in ("1", "true")
            steps = int(q.get("steps", ["50"])[0])
            body = run_intrinsic(data, hq, steps)
            mime = "application/json"
        elif route == "/flash":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            body = run_flash(data, q.get("prompt", [FLASH_PROMPT])[0] or FLASH_PROMPT,
                             int(q.get("seed", ["1"])[0]),
                             keep=q.get("keep", ["color"])[0])
            mime = "image/png"
        else:
            body = run_predict(data, suffix)
            mime = "application/octet-stream"
        return body, mime

    def log_message(self, fmt, *args):
        LOGGER.info(fmt, *args)


if __name__ == "__main__":
    # Threading server: a slow or frozen client can no longer block /health
    # (and with it the whole app). GPU work stays serialized via GPU_LOCK.
    import webbrowser
    app_url = f"http://{HOST}:{PORT}/"
    open_browser = "--open" in sys.argv  # start-companion.bat passes this
    import socket

    class CompanionServer(http.server.ThreadingHTTPServer):
        # http.server sets SO_REUSEADDR, which on Windows lets a second copy
        # bind the same port and silently split requests. Bind exclusively so
        # a second launch fails and just opens the app instead.
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    try:
        server = CompanionServer((HOST, PORT), Handler)
    except OSError as bind_err:
        # Port taken. Only call it "already running" if a companion answers
        # there; anything else (lingering socket, reserved port) is a real error.
        import urllib.request
        try:
            with urllib.request.urlopen(app_url + "health", timeout=3) as r:
                running = json.loads(r.read()).get("ok") is True
        except Exception:  # noqa: BLE001
            running = False
        if not running:
            LOGGER.error("Can't listen on %s:%d (%s). If you just closed the companion, wait "
                         "~30 s and try again.", HOST, PORT, bind_err)
            sys.exit(1)
        LOGGER.info("The companion is already running at %s (close that window to stop it)", app_url)
        if open_browser:
            webbrowser.open(app_url)
        sys.exit(0)
    intrinsic_supported()  # warm the cache before the first /health
    LOGGER.info("Listening on %s  (leave this window open; Ctrl+C to stop)", app_url)
    if open_browser:
        webbrowser.open(app_url)  # the socket is bound, so the page finds us on load
    server.serve_forever()
