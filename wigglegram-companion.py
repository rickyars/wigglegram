"""Local companion server: wraps ml-sharp so the wigglegram app can generate
gaussian splats from within the browser.

Usage:
    python wigglegram-companion.py

Then open wigglegram.html — a "generate splat (ml-sharp)" button appears when
the companion is detected. The SHARP model is loaded once at startup (first
run downloads the checkpoint via torch.hub, ~a few hundred MB, cached).

Endpoints (127.0.0.1:8765):
    GET  /health   -> {"ok": true, "device": "cuda"}
    POST /predict  -> body: image bytes; response: .ply bytes (ml-sharp splat)
    POST /depth    -> body: image bytes; response: grayscale PNG depth map
                      (Depth Anything 3 MONO-LARGE, bright = near; lazy-loaded
                      on first call, then kept warm)
    POST /intrinsic -> body: image bytes; response JSON:
                      {"albedo": <base64 PNG>, "specular": <base64 PNG>}
                      (IntrinsicAnything diffusion decomposition; lazy-loaded.
                      Query params: ?hq=1 for tiled high-res pass, ?steps=N
                      for DDIM steps, default 50.)
"""
import http.server
import json
import logging
import sys
import tempfile
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

LOGGER.info("Loading SHARP model (device=%s)...", DEVICE)
state_dict = torch.hub.load_state_dict_from_url(DEFAULT_MODEL_URL, progress=True)
PREDICTOR = create_predictor(PredictorParams())
PREDICTOR.load_state_dict(state_dict)
PREDICTOR.eval()
PREDICTOR.to(DEVICE)
LOGGER.info("Model ready. Listening on http://%s:%d", HOST, PORT)


DA3_MODEL = None


def run_depth(image_bytes: bytes, suffix: str) -> bytes:
    global DA3_MODEL
    if DA3_MODEL is None:
        LOGGER.info("Loading Depth Anything 3 (DA3MONO-LARGE)...")
        from depth_anything_3.api import DepthAnything3
        DA3_MODEL = DepthAnything3.from_pretrained("depth-anything/DA3MONO-LARGE")
        DA3_MODEL = DA3_MODEL.to(device=torch.device(DEVICE))
        LOGGER.info("DA3 ready.")
    import io as std_io

    import numpy as np
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / ("input" + suffix)
        img_path.write_bytes(image_bytes)
        pred = DA3_MODEL.inference([str(img_path)])
        depth = pred.depth[0].astype("float32")
        lo, hi = float(depth.min()), float(depth.max())
        if hi - lo <= 0:
            raise RuntimeError("degenerate depth output")
        # DA3 depth is distance (small = near); app wants bright = near
        gray = ((1.0 - (depth - lo) / (hi - lo)) * 255.0).astype(np.uint8)
        buf = std_io.BytesIO()
        Image.fromarray(gray, mode="L").save(buf, format="PNG")
        return buf.getvalue()


INTRINSIC_RUNNER = None


def intrinsic_supported() -> bool:
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

    LOGGER.info("intrinsic: albedo pass (hq=%s, steps=%d)...", hq, steps)
    albedo = INTRINSIC_RUNNER.decompose(img, kind="albedo", hq=hq, ddim_steps=steps)
    LOGGER.info("intrinsic: specular pass...")
    specular = INTRINSIC_RUNNER.decompose(img, kind="specular", hq=hq, ddim_steps=steps)
    # Free VRAM so the browser's WebGL splat viewer isn't starved
    INTRINSIC_RUNNER.offload_models()
    return json.dumps({"albedo": to_b64(albedo), "specular": to_b64(specular)}).encode()


def run_predict(image_bytes: bytes, suffix: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / ("input" + suffix)
        img_path.write_bytes(image_bytes)
        image, _, f_px = sharp_io.load_rgb(img_path)
        height, width = image.shape[:2]
        LOGGER.info("Predicting gaussians for %dx%d image...", width, height)
        gaussians = predict_image(PREDICTOR, image, f_px, torch.device(DEVICE))
        ply_path = Path(tmp) / "output.ply"
        save_ply(gaussians, f_px, (height, width), ply_path)
        return ply_path.read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome Private Network Access preflight
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": True, "device": DEVICE,
                               "intrinsic": intrinsic_supported()}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        route = self.path.split("?")[0]
        if route not in ("/predict", "/depth", "/intrinsic"):
            self.send_response(404)
            self._cors()
            self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(n)
            ctype = self.headers.get("Content-Type", "")
            suffix = ".png" if "png" in ctype else ".jpg"
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
            else:
                body = run_predict(data, suffix)
                mime = "application/octet-stream"
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            LOGGER.info("%s returned %.1f MB", route, len(body) / 1048576)
        except Exception as e:  # noqa: BLE001
            LOGGER.exception("predict failed")
            body = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        LOGGER.info(fmt, *args)


if __name__ == "__main__":
    http.server.HTTPServer((HOST, PORT), Handler).serve_forever()
