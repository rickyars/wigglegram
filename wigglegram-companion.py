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
                      (Marigold-Depth, bright = near; lazy-loaded on first
                      call, VRAM released after each request)
    POST /intrinsic -> body: image bytes; response JSON:
                      {"albedo","specular","shading","normals": <base64 PNG>}
                      (Marigold-IID lighting decomposition + Marigold-Normals
                      surface normal estimation; lazy-loaded. ?hq=1 for more
                      steps + ensembling.)
"""
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

LOGGER.info("Loading SHARP model (device=%s)...", DEVICE)
state_dict = torch.hub.load_state_dict_from_url(DEFAULT_MODEL_URL, progress=True)
PREDICTOR = create_predictor(PredictorParams())
PREDICTOR.load_state_dict(state_dict)
PREDICTOR.eval()
PREDICTOR.to(DEVICE)
LOGGER.info("Model ready. Listening on http://%s:%d", HOST, PORT)


# Serialize GPU work across the threading server's request threads
GPU_LOCK = threading.Lock()


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
    gray = INTRINSIC_RUNNER.estimate_depth(img)
    INTRINSIC_RUNNER.offload_models()
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

    LOGGER.info("intrinsic: Marigold-IID decompose (hq=%s)...", hq)
    albedo, specular, shading = INTRINSIC_RUNNER.decompose_full(img, hq=hq)
    LOGGER.info("intrinsic: Marigold-Normals estimate...")
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
        gaussians = predict_image(PREDICTOR, image, f_px, torch.device(DEVICE))
        ply_path = Path(tmp) / "output.ply"
        save_ply(gaussians, f_px, (height, width), ply_path)
        return ply_path.read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body=None, mime="application/json"):
        """Send a full response, tolerating clients that disconnected midway
        (closed/refreshed tabs abort the socket -> WinError 10053; that's the
        client's problem, not ours — log one line instead of a traceback)."""
        try:
            self.send_response(code)
            self._cors()
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
        if self.path == "/health":
            body = json.dumps({"ok": True, "device": DEVICE,
                               "intrinsic": intrinsic_supported()}).encode()
            self._send(200, body)
        else:
            self._send(404)

    def do_POST(self):
        route = self.path.split("?")[0]
        if route not in ("/predict", "/depth", "/intrinsic"):
            self._send(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(n)
            ctype = self.headers.get("Content-Type", "")
            suffix = ".png" if "png" in ctype else ".jpg"
            with GPU_LOCK:
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
            self._send(200, body, mime)
            LOGGER.info("%s returned %.1f MB", route, len(body) / 1048576)
        except Exception as e:  # noqa: BLE001
            LOGGER.exception("%s failed", route)
            self._send(500, json.dumps({"error": str(e)}).encode())

    def log_message(self, fmt, *args):
        LOGGER.info(fmt, *args)


if __name__ == "__main__":
    # Threading server: a slow or frozen client can no longer block /health
    # (and with it the whole app). GPU work stays serialized via GPU_LOCK.
    http.server.ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
