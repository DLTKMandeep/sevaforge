"""
ForgeFlow Dashboard Server — Lightweight SSE server for real-time CLI progress.

Starts in a background thread when `forgeflow run-all --gui` is used.
Serves the existing UI (ui/index.html) and streams live pipeline events via
Server-Sent Events so the browser updates in real-time as each stage runs.

No external dependencies — uses Python stdlib only.

SSE Event Types:
    pipeline_start   { path, stages, total }
    stage_start      { stage, num, total, info }
    stage_result     { stage, result }
    log              { stage, message }
    pipeline_done    { success, elapsed_s, summary }
    heartbeat        {}
"""
from __future__ import annotations

import json
import queue
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Path to the single-file UI
_UI_DIR = Path(__file__).parent.parent / "ui"
_INDEX  = _UI_DIR / "index.html"

DEFAULT_PORT = 7860


# ---------------------------------------------------------------------------
# Global event bus — all SSE clients subscribe to this
# ---------------------------------------------------------------------------

class _EventBus:
    """Thread-safe SSE event broadcaster."""

    def __init__(self) -> None:
        self._lock    = threading.Lock()
        self._clients: List[queue.Queue] = []
        self._history: List[str]         = []   # replay for late-joiners

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._clients.append(q)
            # Replay buffered history so late-joiners catch up
            for msg in self._history[-30:]:
                q.put_nowait(msg)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients = [c for c in self._clients if c is not q]

    def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        payload = json.dumps({"type": event_type, "ts": time.time(), **data})
        msg     = f"data: {payload}\n\n"
        with self._lock:
            self._history.append(msg)
            dead = []
            for q in self._clients:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._clients = [c for c in self._clients if c is not q]


_bus = _EventBus()


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # silence default access log
        pass

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._serve_file()
        elif path == "/events":
            self._serve_sse()
        elif path == "/api/state":
            self._serve_state()
        elif path == "/health":
            self._json({"ok": True})
        else:
            # Try to serve static files from ui/ dir
            target = _UI_DIR / path.lstrip("/")
            if target.exists() and target.is_file():
                self._serve_static(target)
            else:
                self.send_response(404)
                self.end_headers()

    # ── File serving ──────────────────────────────────────────────────────

    def _serve_file(self):
        if not _INDEX.exists():
            self.send_response(404)
            self.end_headers()
            return
        content = _INDEX.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _serve_static(self, path: Path):
        ext_map = {".js": "application/javascript", ".css": "text/css",
                   ".png": "image/png", ".svg": "image/svg+xml"}
        ct = ext_map.get(path.suffix, "application/octet-stream")
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # ── SSE stream ────────────────────────────────────────────────────────

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type",  "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection",    "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = _bus.subscribe()
        # Send initial heartbeat
        try:
            self.wfile.write(b"data: {\"type\":\"connected\"}\n\n")
            self.wfile.flush()
        except Exception:
            _bus.unsubscribe(q)
            return

        try:
            while True:
                try:
                    msg = q.get(timeout=20)
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat to keep connection alive
                    self.wfile.write(b"data: {\"type\":\"heartbeat\"}\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            _bus.unsubscribe(q)

    # ── JSON helpers ──────────────────────────────────────────────────────

    def _serve_state(self):
        state = getattr(DashboardServer._instance, "_state", {})
        self._json(state)

    def _json(self, data: dict):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Dashboard Server
# ---------------------------------------------------------------------------

class DashboardServer:
    """
    Manages the background HTTP/SSE server and emits pipeline events.

    Usage:
        ds = DashboardServer()
        ds.start()                           # starts server + opens browser
        ds.emit_pipeline_start(path, stages)
        ds.emit_stage_start(stage, num, total, info)
        ds.emit_stage_result(stage, result)
        ds.emit_pipeline_done(success, elapsed_s, summary)
        ds.stop()
    """

    _instance: Optional["DashboardServer"] = None

    def __init__(self, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
        self.port         = self._find_free_port(port)
        self.open_browser = open_browser
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = {"mode": "live", "status": "idle"}
        self._start_ts: float = 0.0
        DashboardServer._instance = self

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> "DashboardServer":
        """Start the HTTP server in a daemon thread and open the browser."""
        self._server = HTTPServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="forgeflow-dashboard"
        )
        self._thread.start()
        self._start_ts = time.time()

        url = f"http://localhost:{self.port}"
        print(f"\n  🌐  ForgeFlow Dashboard → {url}\n")

        if self.open_browser:
            # Small delay so the server is ready before browser hits it
            threading.Timer(0.5, webbrowser.open, args=(url,)).start()

        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    # ── Event emitters ────────────────────────────────────────────────────

    def emit_pipeline_start(self, path: str, stages: List[str]) -> None:
        self._state.update({"status": "running", "path": path, "stages": stages,
                             "total": len(stages), "current_stage": None})
        _bus.emit("pipeline_start", {
            "path":   path,
            "stages": stages,
            "total":  len(stages),
        })

    def emit_stage_start(self, stage: str, num: int, total: int,
                         info: Dict[str, Any]) -> None:
        self._state["current_stage"] = stage
        _bus.emit("stage_start", {
            "stage": stage,
            "num":   num,
            "total": total,
            "info":  info,
        })

    def emit_stage_result(self, stage: str, result: Dict[str, Any]) -> None:
        _bus.emit("stage_result", {
            "stage":  stage,
            "result": result,
        })

    def emit_log(self, stage: str, message: str) -> None:
        _bus.emit("log", {"stage": stage, "message": message})

    def emit_pipeline_done(self, success: bool, summary: str = "") -> None:
        elapsed = round(time.time() - self._start_ts, 1)
        self._state.update({"status": "done", "success": success,
                             "elapsed_s": elapsed})
        _bus.emit("pipeline_done", {
            "success":   success,
            "elapsed_s": elapsed,
            "summary":   summary,
        })

    # ── Utility ───────────────────────────────────────────────────────────

    @staticmethod
    def _find_free_port(preferred: int) -> int:
        for port in range(preferred, preferred + 20):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        return preferred  # fallback, will fail loudly


# ---------------------------------------------------------------------------
# Module-level convenience — emitters used by mission_control
# ---------------------------------------------------------------------------

def get_dashboard() -> Optional[DashboardServer]:
    return DashboardServer._instance
