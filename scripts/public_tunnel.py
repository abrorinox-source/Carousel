from __future__ import annotations

import argparse
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path


URL_RE = re.compile(r"https://[a-z0-9.-]+\.lhr\.life", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the project over HTTP and expose it through localhost.run."
    )
    parser.add_argument(
        "--root",
        default=str(PROJECT_ROOT / "output"),
        help="Directory to serve. Defaults to the output/ directory.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local HTTP port to bind. Defaults to 8000.",
    )
    parser.add_argument(
        "--url-file",
        default=".public_base_url",
        help="File where the public base URL will be written.",
    )
    return parser.parse_args()


def _start_http_server(root: Path, port: int) -> socketserver.TCPServer:
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(root), **kwargs
    )
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _start_tunnel(port: int) -> subprocess.Popen[str]:
    if shutil.which("ssh") is None:
        raise RuntimeError("ssh is not installed or not in PATH.")

    return subprocess.Popen(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=60",
            "-R",
            f"80:127.0.0.1:{port}",
            "nokey@localhost.run",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"Root directory does not exist: {root}", file=sys.stderr)
        return 1

    server = _start_http_server(root, args.port)
    tunnel = _start_tunnel(args.port)

    url = None
    try:
        assert tunnel.stdout is not None
        for line in tunnel.stdout:
            print(line, end="")
            match = URL_RE.search(line)
            if match and url is None:
                url = match.group(0).rstrip("/")
                url_file = Path(args.url_file)
                if not url_file.is_absolute():
                    url_file = PROJECT_ROOT / url_file
                url_file.write_text(url, encoding="utf-8")
                print(f"\nPublic base URL written to {url_file}")
                print(f"Base URL: {url}")
    except KeyboardInterrupt:
        pass
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()
        server.shutdown()
        server.server_close()

    return 0 if url else 1


if __name__ == "__main__":
    raise SystemExit(main())
