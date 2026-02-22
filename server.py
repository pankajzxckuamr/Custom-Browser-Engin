import socket
import os
import threading
import mimetypes

HOST = "0.0.0.0"
PORT = 8080

# ─────────────────────────────────────────────────────────────────────────────
# MIME types  (IMPROVEMENT: browsers need Content-Type or they won't render
#              HTML correctly — they'll often show it as plain text)
# ─────────────────────────────────────────────────────────────────────────────
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".txt":  "text/plain; charset=utf-8",
}

def get_mime_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Request handler  (IMPROVEMENT: runs in its own thread so multiple clients
#                   can connect simultaneously without blocking each other)
# ─────────────────────────────────────────────────────────────────────────────
def handle_client(conn, addr):
    """Handle a single client connection in a dedicated thread."""
    try:
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = conn.recv(1024)
            if not chunk:
                break
            raw += chunk
            # Stop reading after headers to avoid hanging on body-less GETs
            if len(raw) > 8192:
                break

        request = raw.decode(errors="ignore")

        if not request:
            return

        # Parse the request line:  GET /path HTTP/1.1
        first_line = request.split("\n")[0].strip()
        parts = first_line.split(" ")

        if len(parts) < 2:
            return

        method = parts[0]
        path   = parts[1]

        print(f"[{addr[0]}] {method} {path}")

        if path == "/":
            path = "/index.html"

        # Security: prevent directory traversal (../../etc/passwd etc.)
        # Resolve the path relative to the current directory only
        filename = os.path.normpath(path.lstrip("/"))
        if filename.startswith(".."):
            send_response(conn, "403 Forbidden", "text/plain", b"403 Forbidden")
            return

        if os.path.exists(filename) and os.path.isfile(filename):
            with open(filename, "rb") as f:
                content = f.read()
            mime = get_mime_type(filename)
            send_response(conn, "200 OK", mime, content)
        else:
            body = b"<html><body><h1>404 Not Found</h1><p>" + path.encode() + b"</p></body></html>"
            send_response(conn, "404 Not Found", "text/html; charset=utf-8", body)

    except Exception as e:
        print(f"[Error] {addr}: {e}")
    finally:
        conn.close()


def send_response(conn, status, content_type, body):
    """
    IMPROVEMENT: Sends proper HTTP/1.1 headers including Content-Type
    and Content-Length.  The original sent no headers at all, which
    causes browsers to guess the content type (often wrongly).
    """
    headers = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    conn.sendall(headers.encode() + body)


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# IMPROVEMENT: SO_REUSEADDR lets you restart the server immediately
# without waiting for the OS to release the port.

server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(10)

print(f"Listening on http://localhost:{PORT}")

while True:
    conn, addr = server.accept()
    print(f"[Connected] {addr[0]}:{addr[1]}")
    # IMPROVEMENT: each connection gets its own thread — the server
    # no longer blocks while serving one client.
    t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
    t.start()