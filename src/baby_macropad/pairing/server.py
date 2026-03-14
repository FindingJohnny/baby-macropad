"""Temporary HTTP server for macropad pairing.

Runs in a daemon thread, listens for a single POST /pair request from
the iOS app. Validates the pairing code, saves credentials to
~/.baby-macropad/pairing.yaml, and shuts down.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import tempfile
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PAIRING_DIR = Path.home() / ".baby-macropad"
PAIRING_FILE = PAIRING_DIR / "pairing.yaml"
DEFAULT_PORT = 31337
TIMEOUT_SECONDS = 300  # 5 minutes
MAX_BODY_SIZE = 8192  # 8 KB
VALID_SERVER_ENVS = {"dev", "prod"}


def generate_pairing_code() -> str:
    """Generate a 4-char uppercase hex pairing code."""
    return secrets.token_hex(2).upper()


def get_local_ip() -> str:
    """Get the local IP address (best effort)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def load_pairing_config() -> dict | None:
    """Load pairing config from disk, or None if not found."""
    if not PAIRING_FILE.exists():
        return None
    try:
        with open(PAIRING_FILE) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        logger.warning("Failed to load pairing config from %s", PAIRING_FILE)
    return None


def save_pairing_config(config: dict) -> None:
    """Save pairing config to disk atomically."""
    PAIRING_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=PAIRING_DIR, suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        os.replace(tmp_path, PAIRING_FILE)
    except BaseException:
        os.unlink(tmp_path)
        raise
    logger.info("Pairing config saved to %s", PAIRING_FILE)


def has_valid_pairing(server: str = "dev") -> bool:
    """Check if a valid pairing exists for the given server."""
    config = load_pairing_config()
    if config is None:
        return False
    server_config = config.get(server)
    if not isinstance(server_config, dict):
        return False
    return bool(server_config.get("token") and server_config.get("api_url") and server_config.get("child_id"))


class PairingServer:
    """Temporary HTTP server that accepts a pairing request from the iOS app."""

    def __init__(
        self,
        code: str,
        name: str,
        on_paired: Callable[[dict], None] | None = None,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.code = code
        self.name = name
        self.port = port
        self._on_paired = on_paired
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self._paired = threading.Event()
        self._stop_lock = threading.Lock()

    @property
    def paired(self) -> bool:
        return self._paired.is_set()

    def start(self) -> None:
        """Start the pairing server in a daemon thread."""
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/pair":
                    self.send_error(404)
                    return

                # Validate pairing code from header (timing-safe)
                request_code = self.headers.get("X-Pairing-Code", "")
                if not secrets.compare_digest(request_code, server_ref.code):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "invalid pairing code"}).encode())
                    return

                # Parse body
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length == 0:
                    self.send_error(400, "empty body")
                    return
                if content_length > MAX_BODY_SIZE:
                    self.send_error(413, "body too large")
                    return

                try:
                    body = json.loads(self.rfile.read(content_length))
                except (json.JSONDecodeError, ValueError):
                    self.send_error(400, "invalid JSON")
                    return

                token = body.get("token")
                api_url = body.get("api_url")
                child_id = body.get("child_id")
                server_env = body.get("server", "dev")

                if not all([token, api_url, child_id]):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "missing token, api_url, or child_id"}).encode())
                    return

                if server_env not in VALID_SERVER_ENVS:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "invalid server environment"}).encode())
                    return

                # Save to config
                config = load_pairing_config() or {}
                config[server_env] = {
                    "token": token,
                    "api_url": api_url,
                    "child_id": child_id,
                }
                config["name"] = server_ref.name
                save_pairing_config(config)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "paired"}).encode())

                server_ref._paired.set()
                if server_ref._on_paired:
                    server_ref._on_paired(config)

                # Schedule shutdown (can't shutdown from request handler directly)
                threading.Thread(target=server_ref.stop, daemon=True).start()

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("PairingServer: %s", format % args)

        try:
            self._server = HTTPServer(("0.0.0.0", self.port), Handler)
        except OSError:
            # Port in use — let OS assign one
            self._server = HTTPServer(("0.0.0.0", 0), Handler)
            logger.info("Port %d in use, using %d", self.port, self._server.server_address[1])
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="pairing-server")
        self._thread.start()

        # Auto-shutdown after timeout
        self._timer = threading.Timer(TIMEOUT_SECONDS, self.stop)
        self._timer.daemon = True
        self._timer.start()

        logger.info("Pairing server started on port %d (name=%s)", self.port, self.name)

    def stop(self) -> None:
        """Shut down the server (thread-safe, idempotent)."""
        with self._stop_lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            server = self._server
            self._server = None
        if server:
            server.shutdown()
            logger.info("Pairing server stopped")
