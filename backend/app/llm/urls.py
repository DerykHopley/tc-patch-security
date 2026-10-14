"""The SSRF guard for local model servers: their URL may only point at this machine.

The URL will be settable from the dev panel (A11). A model URL must never let a request reach another machine
on the network or a cloud metadata address (169.254.169.254). No imports from the app: config.py uses it.
"""
from urllib.parse import urlsplit


def local_url_allowed(url: str, hosts: list[str]) -> bool:
    """Only http(s) to a listed host (loopback plus LOCAL_LLM_HOSTS), no user info in the URL."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and not parts.username and not parts.password and host in hosts
