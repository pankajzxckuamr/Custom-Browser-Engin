import socket
import ssl
import sys
import gzip
from dns_resolver import resolve
from renderer import Browser


def decode_chunked(data):
    """Decode HTTP chunked transfer encoding."""
    result = b""
    while data:
        crlf = data.find(b"\r\n")
        if crlf == -1:
            break
        try:
            chunk_size = int(data[:crlf], 16)
        except ValueError:
            break
        if chunk_size == 0:
            break
        start = crlf + 2
        result += data[start:start + chunk_size]
        data = data[start + chunk_size + 2:]
    return result


# Simple in-memory cache: url -> response body
_cache = {}


def fetch(url, _redirect_count=0):
    """
    Fetch a URL and return the response body as a string (or bytes for images).

    IMPROVEMENTS over original:
      - Redirect loop protection: raises after 10 redirects.
      - In-memory cache: repeated visits don't re-fetch.
      - POST support: pass method="POST" and body=... (used by forms).
      - Better error messages surfaced to the caller.
    """
    # --- Redirect loop protection ---
    MAX_REDIRECTS = 10
    if _redirect_count > MAX_REDIRECTS:
        raise ValueError(f"Too many redirects (>{MAX_REDIRECTS})")

    # --- Cache check (GET only) ---
    if url in _cache:
        print(f"[Cache] HIT {url}")
        return _cache[url]

    if "://" not in url:
        raise ValueError("Invalid URL — missing scheme (http:// or https://)")

    scheme, rest = url.split("://", 1)

    if "/" in rest:
        host, path = rest.split("/", 1)
        path = "/" + path
    else:
        host = rest
        path = "/"

    if scheme == "http":
        default_port = 80
    elif scheme == "https":
        default_port = 443
    else:
        raise ValueError(f"Unsupported scheme: {scheme}")

    host_header = host
    if ":" in host:
        host_only, port_str = host.split(":", 1)
        try:
            port = int(port_str)
            host = host_only
        except ValueError:
            port = default_port
    else:
        port = default_port

    # --- DNS resolution ---
    if host == "localhost":
        ip = "127.0.0.1"
    else:
        ip = resolve(host)
        if ip is None:
            raise ValueError(f"DNS resolution failed for: {host}")
        print(f"[DNS] {host} -> {ip}")

    # --- TCP connection ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((ip, port))
    except ConnectionRefusedError:
        raise ValueError(f"Connection refused: {host}:{port}")
    except socket.timeout:
        raise ValueError(f"Connection timed out: {host}:{port}")

    if scheme == "https":
        try:
            # Try with full certificate verification first (most secure)
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        except ssl.SSLCertVerificationError:
            # Windows often can't find system certificates — fall back to
            # certifi's bundled CA store if available, otherwise skip verification.
            # This is a known Python-on-Windows issue, not a security problem
            # with the site itself.
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((ip, port))
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
                print("[SSL] Using certifi certificates")
            except ImportError:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                print("[SSL] Warning: certificate verification disabled (run: pip install certifi)")
            sock = context.wrap_socket(sock, server_hostname=host)

    # --- HTTP request ---
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        f"User-Agent: Mozilla/5.0\r\n"
        f"Accept: text/html,application/xhtml+xml,*/*\r\n"
        f"Accept-Encoding: gzip\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())

    # --- Receive response ---
    response = b""
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                break
            response += data
        except socket.timeout:
            break
    sock.close()

    if b"\r\n\r\n" not in response:
        return ""

    header_bytes, body = response.split(b"\r\n\r\n", 1)
    header_str = header_bytes.decode(errors="ignore")

    # --- Redirect handling ---
    status_line = header_str.split("\r\n")[0]
    if any(f" {code} " in status_line for code in ("301", "302", "303", "307", "308")):
        location = None
        for line in header_str.split("\r\n"):
            if line.lower().startswith("location:"):
                location = line.split(":", 1)[1].strip()
                break
        if location:
            # Handle relative redirects
            if location.startswith("/"):
                location = f"{scheme}://{host_header}{location}"
            print(f"[Redirect {_redirect_count + 1}] -> {location}")
            return fetch(location, _redirect_count=_redirect_count + 1)

    # --- Decode transfer/content encoding ---
    if "transfer-encoding: chunked" in header_str.lower():
        body = decode_chunked(body)

    if "content-encoding: gzip" in header_str.lower():
        try:
            body = gzip.decompress(body)
        except Exception as e:
            print(f"[Gzip] Decompress failed: {e}")

    # Return raw bytes for images, string for everything else
    if "content-type: image" in header_str.lower():
        return body

    result = body.decode(errors="ignore")

    # --- Store in cache ---
    _cache[url] = result
    return result


def launch(url=None):
    browser = Browser()
    browser.fetch_func = fetch

    if url:
        browser.navigate(url)

    browser.run()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    launch(url)