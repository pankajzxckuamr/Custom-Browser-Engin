# Custom-Browser-Engin

A web browser built from scratch in Python — no `requests`, no `urllib`, no browser engines. Everything from DNS resolution to HTML rendering is implemented manually using raw sockets.

---

## What it does

- Resolves domain names by sending raw DNS queries to Google's `8.8.8.8` nameserver
- Opens TCP connections directly using Python's `socket` module
- Handles HTTP/1.1 and HTTPS (with SSL/TLS)
- Parses HTTP responses including chunked transfer encoding and gzip compression
- Follows redirects (301, 302, 303, 307, 308) with loop protection
- Caches pages in memory so repeated visits don't re-fetch
- Renders HTML in a Tkinter GUI with clickable links, forms, images, and styled text
- Includes a local HTTP server to serve your own HTML files

---

## Project structure

```
my_browser/
├── browser.py        # Core fetch logic — DNS, TCP, HTTP, SSL, redirects, cache
├── dns_resolver.py   # Raw DNS lookup over UDP (no OS resolver)
├── renderer.py       # Tkinter GUI — HTML parser and page renderer
├── server.py         # Local HTTP server with threading and MIME types
└── index.html        # Test page for the local server
```

---

## Setup

**Requirements:** Python 3.8+

Install optional dependencies:

```bash
pip install certifi     # recommended — fixes SSL on Windows
pip install Pillow      # required only if you want images to render
```

---

## Running

**Launch the browser:**
```bash
python browser.py http://example.com
python browser.py https://github.com
```

**Launch with no URL** (opens an empty window, type a URL in the bar):
```bash
python browser.py
```

**Start the local server** (serves files from the current directory):
```bash
python server.py
# then visit http://localhost:8080 in the browser
```

**Test DNS resolution standalone:**
```bash
python dns_resolver.py google.com
python dns_resolver.py github.com
```

---

## How each part works

### `dns_resolver.py`
Builds a raw DNS query packet using `struct.pack` and sends it over UDP to `8.8.8.8:53`. Parses the binary response to extract A records (IPv4 addresses). Handles both compressed and uncompressed name pointers in the response.

### `browser.py`
1. Parses the URL into scheme, host, port, and path
2. Calls `dns_resolver.resolve()` to get the IP address
3. Opens a raw TCP socket and connects to the server
4. Wraps the socket in SSL for HTTPS connections
5. Sends a hand-crafted HTTP/1.1 GET request
6. Reads the response in a loop, decodes chunked encoding and gzip
7. Follows redirects recursively (up to 10 hops)
8. Returns the response body as a string (or bytes for images)

### `renderer.py`
Uses Python's built-in `html.parser` to tokenise the HTML rather than regex. Walks the token list and creates Tkinter widgets for each element — `Label` for headings and paragraphs, `Entry` for inputs, `Button` for form buttons, `Label` with click binding for links. Images are rendered using Pillow if installed.

### `server.py`
A multi-threaded HTTP/1.1 server. Each incoming connection is handed to a new `threading.Thread` so clients don't block each other. Serves static files with correct `Content-Type` and `Content-Length` headers. Includes basic directory traversal protection.

---

## Supported HTML tags

| Tag | Rendered as |
|---|---|
| `<h1>` – `<h6>` | Bold labels at decreasing font sizes |
| `<p>` | Wrapping text label |
| `<a href>` | Clickable blue underlined link |
| `<ul>` / `<li>` | Bullet list items |
| `<strong>`, `<b>` | Bold text |
| `<em>`, `<i>` | Italic text |
| `<pre>`, `<code>` | Monospace block with grey background |
| `<form>`, `<input>`, `<button>` | Working form with GET submission |
| `<img src>` | Image (requires Pillow) |
| `<hr>` | Horizontal rule |
| `<br>` | Line break |
| `<title>` | Sets the window title |

---

## Known limitations

- No CSS support — pages are styled with default fonts only
- No JavaScript
- GET forms only (no POST body)
- Images require `pip install Pillow`
- Very large or complex pages (heavy JavaScript SPAs) will show raw HTML or blank

---

## Troubleshooting

**SSL certificate error on Windows:**
```bash
pip install certifi
```
The browser will automatically use certifi's certificate store as a fallback.

**`ModuleNotFoundError: No module named 'PIL'`:**
```bash
pip install Pillow
```
Images will show a placeholder text until Pillow is installed — everything else still works.

**Port 8080 already in use:**
Change `PORT = 8080` in `server.py` to any free port like `8181`.