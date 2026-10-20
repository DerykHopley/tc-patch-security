"""Link previews for the landing page only (B61, #108): the Open Graph tags a chat app reads to draw a card.

A link pasted into Telegram, Slack or WhatsApp becomes a card (title, text, picture) when the page's HTML has Open
Graph tags. The fetchers run no JavaScript, so React can't add them: the server puts them into index.html when it
serves `/` or `/about` (the landing page, B42). Every other address gets index.html unchanged.

The addresses in the tags are absolute and come from the app address (APP_URL, or the owner's saved one: B26), the
same trusted setting the alert links use. Never from the request's Host header: a spoofed Host would end up in the
card. No tags at all while that address isn't a public https one (local runs), or while the image isn't in the
build: Open Graph needs og:image, so a card without one would be incomplete.
"""
import functools
import hashlib
import html
import pathlib
from urllib.parse import urlsplit

from app.notify import reachable_from_phone

IMAGE = "link-preview/patch.png"  # in the build (frontend/public/link-preview/patch.png); cached for a year
IMAGE_SIZE = (1200, 630)
PAGES = {"": "/", "about": "/about"}  # the path one_port sees (no leading slash) -> the page's own address
TITLE = "Patch, the LLM-security assistant"
DESCRIPTION = ("Security flaws in your LLM stack, tracked for you. Patch watches the products you run, says which "
               "flaws affect you and what to fix first, and answers your questions with sources.")
IMAGE_ALT = ("Patch, a purple robot, beside the name Patch, the line \"Security flaws in your LLM stack, tracked for "
             "you\" and four labels: Watch, Judge, Alert, Ask.")


def public_base(app_url: str | None) -> str | None:
    """The app's public address for the tags, or None: only an https address a fetcher could reach (not localhost)."""
    if not app_url or urlsplit(app_url).scheme != "https" or not reachable_from_phone(app_url):
        return None
    return app_url.rstrip("/")


@functools.lru_cache(maxsize=4)
def _version(path: pathlib.Path, mtime_ns: int, size: int) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def image_version(image: pathlib.Path) -> str | None:
    """A short hash of the image, added to its address so a new image is never served from a chat app's cache."""
    if not image.is_file():
        return None
    stat = image.stat()
    return _version(image, stat.st_mtime_ns, stat.st_size)


def tags(base: str, page: str, version: str) -> str:
    """The <meta> tags for one page, every value escaped."""
    image = f"{base}/{IMAGE}?v={version}"
    pairs = [
        ("name", "description", DESCRIPTION),
        ("property", "og:type", "website"),
        ("property", "og:site_name", "Patch"),
        ("property", "og:title", TITLE),
        ("property", "og:description", DESCRIPTION),
        ("property", "og:url", base + page),
        ("property", "og:image", image),
        ("property", "og:image:type", "image/png"),
        ("property", "og:image:width", str(IMAGE_SIZE[0])),
        ("property", "og:image:height", str(IMAGE_SIZE[1])),
        ("property", "og:image:alt", IMAGE_ALT),
        ("name", "twitter:card", "summary_large_image"),
    ]
    return "".join(f'<meta {kind}="{html.escape(key)}" content="{html.escape(value)}" />\n' for kind, key, value in pairs)


def with_tags(index_html: str, path: str, app_url: str | None, root: pathlib.Path) -> str:
    """index.html for `path`: with the tags on the landing page, unchanged anywhere else or without a public address
    or an image."""
    page = PAGES.get(path.strip("/"))
    base = public_base(app_url)
    version = image_version(root / IMAGE)
    if page is None or base is None or version is None or "</head>" not in index_html:
        return index_html
    return index_html.replace("</head>", tags(base, page, version) + "</head>", 1)
