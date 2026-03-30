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
import logging
import queue
import re
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

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
# SSE log handler — captures Python logging and forwards to the browser console
# ---------------------------------------------------------------------------

class _SSELogHandler(logging.Handler):
    """
    Attach to the root Python logger once at startup.
    Every INFO+ record from forgeflow agents/MCP servers is forwarded
    to connected browsers via _bus so the LiveConsole widget can display it.
    """
    # Logger name prefixes we care about (everything else is ignored)
    _INCLUDE = (
        'forgeflow', 'discovery', 'normalize', 'iac', 'ci', 'cd', 'e2e',
        'review', 'test', 'scan', 'bridge', 'mission', 'agent', 'mcp',
        'documentation', 'security', 'generation', 'scaffolding',
    )
    # Noisy internal libraries to skip
    _EXCLUDE = ('werkzeug', 'urllib3', 'httpx', 'asyncio', 'charset', 'filelock')

    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
    _RICH_RE = re.compile(r'\[/?[^\]\s][^\]]*\]')

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            name_lower = record.name.lower()
            if any(name_lower.startswith(x) for x in self._EXCLUDE):
                return
            # Only forward records that look like forgeflow output
            # (but also accept root-logger records which have name 'root')
            if name_lower != 'root' and not any(x in name_lower for x in self._INCLUDE):
                return
            msg = record.getMessage()
            msg = self._ANSI_RE.sub('', msg)   # strip ANSI colour codes
            msg = self._RICH_RE.sub('', msg)   # strip Rich markup tags
            msg = msg.strip()
            if not msg:
                return
            _bus.emit("log", {
                "msg":   msg,
                "level": record.levelname,   # INFO | WARNING | ERROR
                "name":  record.name,
            })
        except Exception:
            pass


# Attach once — safe to call multiple times (noop if already present)
_sse_handler = _SSELogHandler()
if not any(isinstance(h, _SSELogHandler) for h in logging.root.handlers):
    logging.root.addHandler(_sse_handler)


def _pick_folder_native() -> Optional[str]:
    """
    Open the OS-native folder picker and return the chosen path (or None if cancelled).
    Returns the string 'ERROR:<reason>' if every method fails — lets the UI show a message.
    """
    import subprocess, sys as _sys

    # ── macOS: osascript (built-in, no deps, reliable) ──────────────────────
    if _sys.platform == "darwin":
        import os as _os
        home = _os.path.expanduser("~")
        try:
            # Key UX points:
            #   • default location → home dir (avoids starting buried somewhere)
            #   • prompt text explicitly tells user to SINGLE-CLICK then Open
            #   • "choose folder" only allows selecting folders, never files
            #   • Finder activate brings the dialog to the foreground
            r = subprocess.run(
                ["osascript",
                 "-e", "tell application \"Finder\" to activate",
                 "-e", (
                     f"POSIX path of (choose folder"
                     f" with prompt \"Select your AI project folder"
                     f" \\u2014 single-click the folder, then click Open\""
                     f" default location POSIX file \"{home}\")"
                 )],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                # Strip trailing slash that macOS always appends
                return r.stdout.strip().rstrip("/") or None
            # returncode 1 = user pressed Cancel — not an error
            return None
        except FileNotFoundError:
            pass   # osascript not found (shouldn't happen on macOS)
        except Exception:
            pass

    # ── subprocess + tkinter (fresh process avoids thread-safety issues) ────
    _tk_script = (
        "import tkinter as tk;"
        "from tkinter import filedialog;"
        "r=tk.Tk();r.withdraw();r.lift();r.attributes('-topmost',True);"
        "p=filedialog.askdirectory(title='Select your AI project folder');"
        "r.destroy();print(p or '',end='')"
    )
    try:
        result = subprocess.run(
            [_sys.executable, "-c", _tk_script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass

    # ── Linux: zenity / kdialog ──────────────────────────────────────────────
    if _sys.platform.startswith("linux"):
        for cmd in (
            ["zenity", "--file-selection", "--directory",
             "--title=Select your AI project folder"],
            ["kdialog", "--getexistingdirectory", "."],
        ):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    return r.stdout.strip() or None
            except FileNotFoundError:
                continue
            except Exception:
                break

    # Nothing worked — tell the UI so it can show a helpful message
    return "ERROR:no_picker"


# Global run-lock: prevents two pipelines running at the same time
_run_lock = threading.Lock()
_running  = False   # True while a pipeline is in flight


def _spawn_pipeline(
    path: str,
    stages: Optional[List[str]] = None,
    greenfield: bool = False,
    greenfield_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Run MissionControl.run_all() in a daemon thread.
    Called from the /api/run POST handler.

    For greenfield projects, ``path`` is the target directory that will be
    created (parent must already exist).  ``greenfield_config`` carries the
    wizard answers (language, framework, cloud, database, cicd, app_type …).
    """
    global _running

    def _work():
        global _running
        try:
            # Lazy import avoids circular dep during server startup.
            # Try installed package first, then local flat import (dev / editable install).
            MissionControl = None
            for _import in [
                "forgeflow.core.mission_control",
                "core.mission_control",
                "forgeflow_local.core.mission_control",
            ]:
                try:
                    import importlib
                    _mod = importlib.import_module(_import)
                    MissionControl = _mod.MissionControl
                    break
                except ImportError:
                    continue
            if MissionControl is None:
                raise ImportError(
                    "Cannot find MissionControl — tried forgeflow.core, core, and forgeflow_local.core"
                )

            # For greenfield mode, create the target directory first so
            # the scaffolding agent has a real path to populate.
            if greenfield:
                import os as _os
                _os.makedirs(path, exist_ok=True)

            # Write wizard config to sevaforge.json so every agent can read
            # project preferences (language, framework, cloud, CI, CD …).
            if greenfield_config:
                config_path = Path(path) / "sevaforge.json"
                config_path.write_text(
                    json.dumps({"greenfield": greenfield, **greenfield_config}, indent=2)
                )

            mc = MissionControl()
            mc.run_all(path=path, greenfield=greenfield)
        except Exception as exc:
            _bus.emit("log", {"stage": "server", "message": f"Pipeline error: {exc}"})
            _bus.emit("pipeline_done", {"success": False, "elapsed_s": 0,
                                        "summary": str(exc)})
        finally:
            _running = False

    _running = True
    t = threading.Thread(target=_work, daemon=True, name="forgeflow-pipeline")
    t.start()


# ---------------------------------------------------------------------------
# Threaded HTTP server — each connection (SSE, API, static) gets its own thread
# so long-lived SSE streams don't block short API calls like /api/browse
# ---------------------------------------------------------------------------

class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True   # threads die when the main process exits

    def handle_error(self, request, client_address):
        """Silence noisy-but-harmless browser connection resets."""
        import sys as _sys
        if _sys.exc_info()[0] in (ConnectionResetError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # silence default access log
        pass

    # ── CORS preflight ────────────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._serve_file()
        elif path == "/events":
            self._serve_sse()
        elif path == "/api/state":
            self._serve_state()
        elif path == "/api/running":
            self._json({"running": _running})
        elif path == "/api/ls":
            self._handle_ls()
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

    # ── POST handler — /api/run ───────────────────────────────────────────
    def do_POST(self):
        global _running
        parsed_path = urlparse(self.path).path

        if parsed_path == "/api/browse":
            self._handle_browse()
            return

        if parsed_path != "/api/run":
            self.send_response(404)
            self.end_headers()
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, status=400)
            return

        greenfield        = bool(payload.get("greenfield", False))
        greenfield_config = payload.get("config") or {}

        if greenfield:
            # Greenfield: caller supplies parent_path + project_name.
            # We combine them to get the target directory.
            parent_path  = (payload.get("parent_path") or "").strip()
            project_name = (payload.get("project_name") or "").strip()
            if not parent_path or not project_name:
                self._json({"error": "parent_path and project_name are required for greenfield mode"}, status=400)
                return
            parent_path = str(Path(parent_path).expanduser())
            if not Path(parent_path).exists():
                self._json({"error": f"Parent directory not found: {parent_path}"}, status=400)
                return
            # Sanitise project name — no path separators
            safe_name = project_name.replace("/", "-").replace("\\", "-").strip()
            repo_path = str(Path(parent_path) / safe_name)
        else:
            repo_path = (payload.get("path") or "").strip()
            if not repo_path:
                self._json({"error": "path is required"}, status=400)
                return
            # Expand ~ so /Users/mandeep/demo-api works
            repo_path = str(Path(repo_path).expanduser())
            if not Path(repo_path).exists():
                self._json({"error": f"Path not found: {repo_path}"}, status=400)
                return

        if _running:
            self._json({"error": "A pipeline is already running"}, status=409)
            return

        if not _run_lock.acquire(blocking=False):
            self._json({"error": "A pipeline is already starting"}, status=409)
            return

        try:
            _spawn_pipeline(
                repo_path,
                greenfield=greenfield,
                greenfield_config=greenfield_config if greenfield else None,
            )
        finally:
            _run_lock.release()

        self._json({"started": True, "path": repo_path})

    # ── /api/browse — open native OS folder picker (kept for compatibility) ─
    def _handle_browse(self):
        path = _pick_folder_native()
        if path:
            self._json({"path": path})
        else:
            self._json({"path": None, "cancelled": True})

    # ── /api/ls — list subdirectories of a path (cross-platform browser) ──
    def _handle_ls(self):
        import os as _os
        from urllib.parse import urlparse as _up, parse_qs as _pqs
        qs   = _pqs(_up(self.path).query)
        raw  = qs.get("path", ["~"])[0]
        path = _os.path.expanduser(raw)
        path = _os.path.abspath(path)

        if not _os.path.isdir(path):
            self._json({"error": "Not a directory"}, 400)
            return

        try:
            entries = []
            for name in sorted(_os.listdir(path), key=str.lower):
                if name.startswith("."):
                    continue          # skip hidden
                full = _os.path.join(path, name)
                if _os.path.isdir(full):
                    entries.append({"name": name, "path": full})

            # Parent directory (None when already at filesystem root)
            parent = _os.path.dirname(path)
            if parent == path:        # reached the root
                parent = None

            self._json({"path": path, "parent": parent, "entries": entries})
        except PermissionError:
            self._json({"error": "Permission denied"}, 403)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

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
        # Send initial heartbeat then replay current pipeline state so a
        # browser that loads after pipeline_start still sees the live view.
        try:
            self.wfile.write(b"data: {\"type\":\"connected\"}\n\n")
            self.wfile.flush()
            # Replay state if pipeline is already running or done
            inst = DashboardServer._instance
            if inst:
                s = inst._state
                status = s.get("status", "idle")
                if status in ("running", "done") and s.get("stages"):
                    # Re-emit pipeline_start so the UI initialises stages
                    replay = json.dumps({
                        "type":   "pipeline_start",
                        "path":   s.get("path", ""),
                        "stages": s.get("stages", []),
                        "total":  s.get("total", 0),
                    })
                    self.wfile.write(f"data: {replay}\n\n".encode())
                    # Re-emit current stage if one is active
                    if s.get("current_stage"):
                        cs = json.dumps({
                            "type":  "stage_start",
                            "stage": s["current_stage"],
                            "num":   s.get("current_num", 0),
                            "total": s.get("total", 0),
                            "info":  {},
                        })
                        self.wfile.write(f"data: {cs}\n\n".encode())
                    # Re-emit pipeline_done if finished
                    if status == "done":
                        done_msg = json.dumps({
                            "type":      "pipeline_done",
                            "success":   s.get("success", False),
                            "elapsed_s": s.get("elapsed_s", 0),
                        })
                        self.wfile.write(f"data: {done_msg}\n\n".encode())
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

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
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
        self._server: Optional[_ThreadedHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = {"mode": "live", "status": "idle"}
        self._start_ts: float = 0.0
        DashboardServer._instance = self

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> "DashboardServer":
        """Start the HTTP server in a daemon thread and open the browser."""
        self._server = _ThreadedHTTPServer(("127.0.0.1", self.port), _Handler)
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
        self._state["current_num"] = num
        _bus.emit("stage_start", {
            "stage": stage,
            "num":   num,
            "total": total,
            "info":  info,
        })

    def emit_stage_result(self, stage: str, result: Dict[str, Any]) -> None:
        self._state["current_stage"] = None
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
