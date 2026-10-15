"""Build the search index: embed every chunk with EMBEDDER and write the Chroma collection to INDEX_PATH.

    cd backend && uv run --env-file .env python -m app.rag.build_index

With EMBEDDER=openrouter this is a paid call (text-embedding-3-small, about 1,700 chunks: well under a cent).
The app loads the result at start-up and refuses to start if EMBEDDER has changed since.
"""
import sys
import time

from app.config import ConfigError, Settings
from app.knowledge import load_knowledge
from app.rag.chunking import build_chunks
from app.rag.embed import make_embedder
from app.rag.vector import build_index


def main(argv: list[str] | None = None) -> int:
    try:
        settings = Settings.from_env()
        settings.check()
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 1
    chunks = build_chunks(load_knowledge())
    embedder = make_embedder(settings)
    print(f"Embedding {len(chunks)} chunks with {embedder.name} into {settings.index_path} ...")
    started = time.monotonic()
    index = build_index(chunks, embedder, settings.index_path,
                        progress=lambda done, total: print(f"  {done}/{total}", end="\r", flush=True))
    print(f"\nDone in {time.monotonic() - started:.1f} s: {len(chunks)} chunks, {index.dim} dimensions, "
          f"model {index.embedder_name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
