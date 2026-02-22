import tkinter as tk
from html.parser import HTMLParser
import urllib.parse
import io


# ─────────────────────────────────────────────
#  HTML Parser  (replaces fragile regex splits)
# ─────────────────────────────────────────────
class HTMLNode:
    """Simple node produced by the parser."""
    def __init__(self, tag, attrs=None, text="", is_closing=False):
        self.tag = tag.lower() if tag else ""
        self.attrs = dict(attrs or [])
        self.text = text
        self.is_closing = is_closing

    def get(self, attr, default=None):
        return self.attrs.get(attr, default)


class PageParser(HTMLParser):
    """
    IMPROVEMENT: Uses Python's built-in html.parser instead of regex.
    This correctly handles:
      - Tags with attributes: <p class="foo">
      - Self-closing tags: <input ... />
      - Multiline attributes
      - HTML entities like &amp; &lt; &gt;
    """
    def __init__(self):
        super().__init__()
        self.nodes = []
        self._pending_tag = None   # tag waiting for its text content

    def handle_starttag(self, tag, attrs):
        self.nodes.append(HTMLNode(tag, attrs))

    def handle_endtag(self, tag):
        self.nodes.append(HTMLNode(tag, is_closing=True))

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.nodes.append(HTMLNode("__text__", text=text))

    def handle_entityref(self, name):
        entities = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "nbsp": " "}
        self.nodes.append(HTMLNode("__text__", text=entities.get(name, "")))

    def handle_charref(self, name):
        try:
            ch = chr(int(name[1:], 16) if name.startswith("x") else int(name))
            self.nodes.append(HTMLNode("__text__", text=ch))
        except Exception:
            pass


def parse_html(html):
    p = PageParser()
    p.feed(html)
    return p.nodes


# ─────────────────────────────────────
#  Browser / Renderer
# ─────────────────────────────────────
class Browser:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mini Browser")
        self.root.geometry("900x650")

        self.current_url = ""
        self.inputs = {}
        self.fetch_func = None

        self._build_ui()

    # ── UI layout ──────────────────────────────────────────────────────────
    def _build_ui(self):
        nav = tk.Frame(self.root, bg="#e8e8e8", pady=4)
        nav.pack(side="top", fill="x")

        self.url_bar = tk.Entry(nav, width=80, font=("Arial", 12))
        self.url_bar.pack(side="left", padx=8, pady=4)
        self.url_bar.bind("<Return>", lambda e: self._on_go())

        tk.Button(nav, text="Go",      command=self._on_go).pack(side="left")
        tk.Button(nav, text="← Back",  command=self._on_back).pack(side="left", padx=4)
        tk.Button(nav, text="↺ Reload", command=self._on_reload).pack(side="left")

        # Status bar at the bottom
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              bd=1, relief="sunken", anchor="w",
                              font=("Arial", 10), bg="#f5f5f5")
        status_bar.pack(side="bottom", fill="x")

        # Scrollable canvas
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, bg="white")
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = tk.Frame(self.canvas, bg="white")
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        ))
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.history = []

    # ── Navigation helpers ─────────────────────────────────────────────────
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_go(self):
        url = self.url_bar.get().strip()
        if url:
            self.navigate(url)

    def _on_back(self):
        if len(self.history) > 1:
            self.history.pop()
            self.navigate(self.history.pop())

    def _on_reload(self):
        # IMPROVEMENT: reload clears the cache entry so you get fresh content
        if self.current_url:
            from browser import _cache
            _cache.pop(self.current_url, None)
            self.navigate(self.current_url)

    def navigate(self, url):
        if not url.startswith("http"):
            url = "http://" + url
        self.current_url = url
        self.url_bar.delete(0, tk.END)
        self.url_bar.insert(0, url)
        self.history.append(url)
        self.status_var.set(f"Loading {url}…")
        self.root.update_idletasks()

        try:
            html = self.fetch_func(url)
            self.render(html)
            self.status_var.set(url)
        except Exception as e:
            self.clear()
            tk.Label(self.frame, text=f"Error: {e}", bg="white",
                     fg="red", font=("Arial", 13), wraplength=860).pack(padx=20, pady=20)
            self.status_var.set(f"Error: {e}")

    def clear(self):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.inputs = {}

    def run(self):
        self.root.mainloop()

    # ── Renderer ───────────────────────────────────────────────────────────
    def render(self, html):
        """
        IMPROVEMENT: Uses the HTMLParser-based tokeniser instead of regex,
        so tags with attributes, entities, and unusual whitespace all work.
        Also adds support for <strong>, <em>, <b>, <i>, <pre>, <code>,
        <title> (sets window title), <br>, and <hr>.
        """
        self.clear()

        if isinstance(html, bytes):
            # Shouldn't normally get here but handle gracefully
            html = html.decode(errors="ignore")

        nodes = parse_html(html)

        current_form_action = None
        # Track inline formatting context
        bold = False
        italic = False

        i = 0
        while i < len(nodes):
            node = nodes[i]

            # ── Structural / metadata ──────────────────────────────────────
            if node.tag == "title" and not node.is_closing:
                i += 1
                if i < len(nodes) and nodes[i].tag == "__text__":
                    self.root.title(nodes[i].text)

            elif node.tag in ("h1", "h2", "h3", "h4", "h5", "h6") and not node.is_closing:
                sizes = {"h1": 24, "h2": 20, "h3": 16, "h4": 14, "h5": 12, "h6": 11}
                size = sizes.get(node.tag, 12)
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text=text, bg="white",
                         font=("Arial", size, "bold")).pack(anchor="w", padx=10, pady=(8, 2))

            elif node.tag == "p" and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text=text, bg="white",
                         font=("Arial", 12), wraplength=840, justify="left"
                         ).pack(anchor="w", padx=10, pady=3)

            elif node.tag == "li" and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text="  •  " + text, bg="white",
                         font=("Arial", 12)).pack(anchor="w", padx=30, pady=1)

            # IMPROVEMENT: <strong> / <b> and <em> / <i> inline labels
            elif node.tag in ("strong", "b") and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text=text, bg="white",
                         font=("Arial", 12, "bold")).pack(anchor="w", padx=10)

            elif node.tag in ("em", "i") and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text=text, bg="white",
                         font=("Arial", 12, "italic")).pack(anchor="w", padx=10)

            # IMPROVEMENT: <pre> / <code> monospace block
            elif node.tag in ("pre", "code") and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else ""
                tk.Label(self.frame, text=text, bg="#f4f4f4",
                         font=("Courier", 11), justify="left",
                         wraplength=840, anchor="w").pack(anchor="w", padx=10, pady=4, fill="x")

            # IMPROVEMENT: <hr> horizontal rule
            elif node.tag == "hr":
                tk.Frame(self.frame, height=1, bg="#cccccc").pack(
                    fill="x", padx=10, pady=6)

            # IMPROVEMENT: <br> line break
            elif node.tag == "br":
                tk.Label(self.frame, text="", bg="white").pack()

            # ── Forms ──────────────────────────────────────────────────────
            elif node.tag == "form" and not node.is_closing:
                current_form_action = node.get("action")

            elif node.tag == "form" and node.is_closing:
                current_form_action = None

            elif node.tag == "input" and not node.is_closing:
                name = node.get("name", f"input_{len(self.inputs)}")
                placeholder = node.get("placeholder", "")
                itype = node.get("type", "text")
                value = node.get("value", "")

                row = tk.Frame(self.frame, bg="white")
                row.pack(anchor="w", padx=10, pady=4)

                if itype == "password":
                    entry = tk.Entry(row, show="*", width=40, font=("Arial", 12))
                elif itype == "submit":
                    label = value or "Submit"
                    action = current_form_action
                    tk.Button(row, text=label, font=("Arial", 12),
                              command=lambda a=action: self._on_button(a)).pack()
                    i += 1
                    continue
                else:
                    entry = tk.Entry(row, width=40, font=("Arial", 12))

                if placeholder:
                    entry.insert(0, placeholder)
                    entry.config(fg="grey")
                    entry.bind("<FocusIn>",
                               lambda e, en=entry, p=placeholder:
                               en.delete(0, tk.END) if en.get() == p else None)
                elif value:
                    entry.insert(0, value)

                entry.pack()
                self.inputs[name] = entry

            elif node.tag == "button" and not node.is_closing:
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else "Click"
                action = current_form_action
                tk.Button(self.frame, text=text, font=("Arial", 12),
                          command=lambda a=action: self._on_button(a)
                          ).pack(anchor="w", padx=10, pady=4)

            # ── Links ──────────────────────────────────────────────────────
            elif node.tag == "a" and not node.is_closing:
                href = node.get("href", "")
                i += 1
                text = nodes[i].text if i < len(nodes) and nodes[i].tag == "__text__" else href
                if href:
                    lbl = tk.Label(self.frame, text=text, bg="white",
                                   fg="blue", font=("Arial", 12, "underline"),
                                   cursor="hand2")
                    lbl.pack(anchor="w", padx=10, pady=1)
                    lbl.bind("<Button-1>", lambda e, u=href: self._on_link(u))

            # ── Images ─────────────────────────────────────────────────────
            elif node.tag == "img" and not node.is_closing:
                src = node.get("src", "")
                alt = node.get("alt", "[image]")
                if src:
                    self._render_image(src, alt)

            i += 1

    # ── Event handlers ─────────────────────────────────────────────────────
    def _on_link(self, url):
        if url.startswith("http"):
            self.navigate(url)
        else:
            base = self.current_url.rsplit("/", 1)[0]
            self.navigate(base + "/" + url.lstrip("/"))

    def _on_button(self, action):
        if not action:
            print("[Form] Button clicked but no action defined")
            return
        params = {name: entry.get() for name, entry in self.inputs.items()}
        query = urllib.parse.urlencode(params)
        if action.startswith("http"):
            url = f"{action}?{query}"
        else:
            base = self.current_url.rsplit("/", 1)[0]
            url = f"{base}/{action.lstrip('/')}?{query}"
        self.navigate(url)

    def _render_image(self, src, alt="[image]"):
        """
        IMPROVEMENT: image_data is already bytes when content-type is image,
        so we no longer need the latin-1 encode/decode round-trip.
        """
        try:
            if not src.startswith("http"):
                base = self.current_url.rsplit("/", 1)[0]
                src = base + "/" + src.lstrip("/")

            image_data = self.fetch_func(src)

            from PIL import Image, ImageTk

            # fetch() returns raw bytes for images; handle both just in case
            if isinstance(image_data, str):
                image_data = image_data.encode("latin-1")

            img = Image.open(io.BytesIO(image_data))
            img.thumbnail((700, 500))
            photo = ImageTk.PhotoImage(img)

            lbl = tk.Label(self.frame, image=photo, bg="white")
            lbl.image = photo   # prevent garbage collection
            lbl.pack(anchor="w", padx=10, pady=4)

        except ImportError:
            tk.Label(self.frame, text=f"[Image: install Pillow to view — {alt}]",
                     bg="white", fg="orange").pack(anchor="w", padx=10)
        except Exception as e:
            tk.Label(self.frame, text=f"[Image failed: {e}]",
                     bg="white", fg="red").pack(anchor="w", padx=10)