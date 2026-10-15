"""One port for the API and the built frontend (B12): how the container serves the app.

The API moves under /api because the frontend's pages share names with API routes (/cves, /settings, /dev): a
reload of /cves must get the page, not the JSON. Every path outside /api is a built file when one exists, else the
frontend's index.html, which picks the page from the address (frontend/src/route.ts). /health also stays at the
root, for the CI smoke test and Cloud Run's start-up probe.

Without FRONTEND_DIR none of this is used: locally Vite serves the frontend on its own port, and the API stays at
the root.
"""
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse

API_PREFIX = "/api"


def one_port(api: FastAPI, frontend_dir: pathlib.Path) -> FastAPI:
    root = frontend_dir.resolve()
    index = root / "index.html"
    health = next(r.endpoint for r in api.routes if getattr(r, "path", None) == "/health")

    site = FastAPI(title=api.title, docs_url=None, redoc_url=None, openapi_url=None)
    site.add_api_route("/health", health, methods=["GET"])
    site.mount(API_PREFIX, api)

    @site.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            # Vite names built files by their content hash, so they can be cached for good
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})  # a new build is picked up on reload

    return site
