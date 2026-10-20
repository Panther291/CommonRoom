from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import socket
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, urlsplit


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SHARE = APP_DIR / "shared"
SESSION_COOKIE = "lan_file_session"
SESSION_SECONDS = 12 * 60 * 60
CHUNK_SIZE = 256 * 1024
SERVER_PASSWORD = "Test@1234"
STATIC_ICONS = {
    f"/static/icons/{name}.svg": f"static/icons/{name}.svg"
    for name in ("archive", "audio", "code", "document", "drive", "file", "folder", "image", "video")
}


def resolve_shared_path(root: Path, relative_path: str) -> Path:
    if "\x00" in relative_path or "\\" in relative_path:
        raise ValueError("Invalid path")

    parts = PurePosixPath(relative_path).parts
    if any(part == ".." for part in parts) or relative_path.startswith("/"):
        raise ValueError("Invalid path")

    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Path is outside the shared folder")
    return candidate


def parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None:
        return None
    if size <= 0 or not header.startswith("bytes=") or "," in header:
        raise ValueError("Invalid byte range")

    value = header[6:].strip()
    if "-" not in value:
        raise ValueError("Invalid byte range")
    first, last = value.split("-", 1)

    try:
        if first:
            start = int(first)
            end = int(last) if last else size - 1
            if start < 0 or start >= size or end < start:
                raise ValueError("Invalid byte range")
            return start, min(end, size - 1)

        suffix_length = int(last)
        if suffix_length <= 0:
            raise ValueError("Invalid byte range")
        return max(0, size - suffix_length), size - 1
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid byte range") from error


def detect_lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def discover_roots() -> dict[str, tuple[str, Path]]:
    roots: dict[str, tuple[str, Path]] = {}
    if os.name == "nt":
        import ctypes

        drive_mask = ctypes.windll.kernel32.GetLogicalDrives()
        for index in range(26):
            if drive_mask & (1 << index):
                letter = chr(ord("A") + index)
                path = Path(f"{letter}:\\")
                if path.exists():
                    roots[f"drive-{letter.lower()}"] = (f"{letter}:", path.resolve())
    if roots:
        return roots

    DEFAULT_SHARE.mkdir(parents=True, exist_ok=True)
    return {"shared": ("Shared folder", DEFAULT_SHARE.resolve())}


class FileBrowserServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], roots: dict[str, tuple[str, Path]], password: str):
        self.roots = {root_id: (label, path.resolve()) for root_id, (label, path) in roots.items()}
        self.password = password
        self.sessions: dict[str, float] = {}
        super().__init__(address, FileBrowserHandler)


class FileBrowserHandler(BaseHTTPRequestHandler):
    server: FileBrowserServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            return False
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is None:
            return False

        now = time.time()
        for token, expires in list(self.server.sessions.items()):
            if expires <= now:
                self.server.sessions.pop(token, None)
        expires = self.server.sessions.get(morsel.value)
        return expires is not None and expires > now

    def same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.netloc == self.headers.get("Host") and parsed.scheme in {"http", "https"}

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        route = request.path

        if route == "/":
            self.serve_static("index.html", "text/html; charset=utf-8")
            return
        if route == "/static/app.css":
            self.serve_static("static/app.css", "text/css; charset=utf-8")
            return
        if route == "/static/app.js":
            self.serve_static("static/app.js", "text/javascript; charset=utf-8")
            return
        if route in STATIC_ICONS:
            self.serve_static(STATIC_ICONS[route], "image/svg+xml; charset=utf-8")
            return
        if route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Sign in to continue"})
            return
        if route == "/api/session":
            self.send_json(HTTPStatus.OK, {"authenticated": True})
        elif route == "/api/list":
            query = parse_qs(request.query)
            self.list_directory(query.get("root", [""])[0], query.get("path", [""])[0])
        elif route == "/api/file":
            query = parse_qs(request.query)
            self.serve_file(query.get("root", [""])[0], query.get("path", [""])[0], request.query)
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route not in {"/api/login", "/api/logout"}:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self.same_origin():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Request origin rejected"})
            return

        if route == "/api/login":
            self.login()
            return
        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Sign in to continue"})
            return

        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        if morsel:
            self.server.sessions.pop(morsel.value, None)
        self.send_response(HTTPStatus.OK)
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def login(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
            password = payload.get("password")
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid sign-in request"})
            return

        if not isinstance(password, str) or not hmac.compare_digest(
            hashlib.sha256(password.encode("utf-8")).digest(),
            hashlib.sha256(self.server.password.encode("utf-8")).digest(),
        ):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "That password did not match"})
            return

        token = secrets.token_urlsafe(32)
        self.server.sessions[token] = time.time() + SESSION_SECONDS
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}",
        )
        body = b'{"authenticated":true}'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, relative_path: str, content_type: str) -> None:
        path = APP_DIR / relative_path
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def list_directory(self, root_id: str, relative_path: str) -> None:
        if not root_id:
            entries = [
                {"name": label, "path": "", "root": identifier, "volume": True, "directory": True}
                for identifier, (label, _path) in self.server.roots.items()
            ]
            self.send_json(HTTPStatus.OK, {"path": "", "root": "", "rootName": "Computer", "entries": entries})
            return

        root_entry = self.server.roots.get(root_id)
        if root_entry is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Drive not found"})
            return
        root_name, root = root_entry
        try:
            directory = resolve_shared_path(root, relative_path)
            if not directory.is_dir():
                raise ValueError("Not a folder")
            entries = []
            for item in directory.iterdir():
                try:
                    resolved = item.resolve()
                    if not resolved.is_relative_to(root):
                        continue
                    info = item.stat()
                except (OSError, RuntimeError):
                    continue
                item_path = item.relative_to(root).as_posix()
                mime_type = mimetypes.guess_type(item.name)[0] or "application/octet-stream"
                entries.append(
                    {
                        "name": item.name,
                        "path": item_path,
                        "directory": item.is_dir(),
                        "size": None if item.is_dir() else info.st_size,
                        "modified": info.st_mtime,
                        "type": mime_type,
                    }
                )
            entries.sort(key=lambda entry: (not entry["directory"], entry["name"].casefold()))
        except (OSError, ValueError):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Folder not found"})
            return

        self.send_json(
            HTTPStatus.OK,
            {"path": relative_path, "root": root_id, "rootName": root_name, "entries": entries},
        )

    def serve_file(self, root_id: str, relative_path: str, query: str) -> None:
        root_entry = self.server.roots.get(root_id)
        if root_entry is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Drive not found"})
            return
        _root_name, root = root_entry
        try:
            path = resolve_shared_path(root, relative_path)
            if not path.is_file():
                raise ValueError("Not a file")
            media_file = path.open("rb")
            size = os.fstat(media_file.fileno()).st_size
        except (OSError, ValueError):
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "File is not accessible"})
            return

        try:
            byte_range = parse_byte_range(self.headers.get("Range"), size)
        except ValueError:
            media_file.close()
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        start, end = byte_range if byte_range is not None else (0, size - 1)
        length = max(0, end - start + 1)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        inline_requested = parse_qs(query).get("inline", [""])[0] == "1"
        inline_allowed = mime_type.startswith(("audio/", "video/"))
        disposition = "inline" if inline_requested and inline_allowed else "attachment"
        self.send_response(HTTPStatus.PARTIAL_CONTENT if byte_range else HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(path.name)}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if byte_range:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        if length == 0:
            media_file.close()
            return
        try:
            media_file.seek(start)
            remaining = length
            while remaining:
                chunk = media_file.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            media_file.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse and play files from your drives on your local network.")
    parser.add_argument(
        "--share",
        type=Path,
        action="append",
        help="Folder to share instead of detected drives (repeat to share multiple folders)",
    )
    parser.add_argument("--host", default=None, help="Network interface IP to bind (default: detected LAN IP)")
    parser.add_argument("--port", type=int, default=8000, help="Port to use (default: 8000)")
    args = parser.parse_args()

    if args.share:
        roots = {}
        for index, configured_path in enumerate(args.share, start=1):
            root = configured_path.expanduser().resolve()
            if not root.is_dir():
                parser.error(f"The share path must be an existing directory: {configured_path}")
            label = root.drive if root == Path(root.anchor) else (root.name or str(root))
            roots[f"share-{index}"] = (label, root)
    else:
        roots = discover_roots()

    host = args.host or detect_lan_ip()
    try:
        server = FileBrowserServer((host, args.port), roots, SERVER_PASSWORD)
    except OSError as error:
        parser.error(f"Could not start server at {host}:{args.port}: {error}")

    print("Available roots:")
    for label, path in roots.values():
        print(f"  {label}: {path}")
    print(f"Open:    http://{host}:{args.port}")
    print(f"Password: {SERVER_PASSWORD}")
    print("Warning: this fixed password is easy to guess; use only on a trusted private network.")
    print("Stop the server with Ctrl+C. Use only on a trusted private network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()