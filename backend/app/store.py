"""The state store (B09, #41; spec #31 "Per-user state"): JSON documents by key, each read with its version and
written only if the version still matches.

    read(key)                     -> (data, version), or (None, None) when there is nothing
    write(key, data, if_version)  -> the new version; Conflict if someone wrote since `if_version` was read
                                     (None: only if there is nothing yet; ANY, the default: whatever is there)
    delete(key), keys(prefix)

Keys look like relative paths (`<user id>.json` in the users' store, `refresh.json`, `v000002/cves.json` in the live
data's). Callers (app.state) read, change and write, and on a Conflict read again and redo the change.

- LocalStore: JSON files under a folder, written whole (temp file, then rename), behind one lock. Named keys can sit
  at their old paths, so today's state file (STATE_PATH) is the default user's state, unchanged. The version is a
  hash of the file's bytes, so a write from another process in between is seen too.
- MemoryStore: the same in a dict, for tests.
- GcsStore: one Cloud Storage object per key, the object's generation as the version and as the write's
  precondition (`if_generation_match`, 0 for "doesn't exist yet"). It takes a google-cloud-storage Bucket, or
  anything with its few calls (tests/fake_gcs.py); the deploy (#44) builds the real one.
"""
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Protocol

ANY = object()  # write whatever version is there
_KEY = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


class Conflict(Exception):
    """The key changed since its version was read (or exists, for a create)."""


def check_key(key: str) -> str:
    if not _KEY.fullmatch(key) or any(part in (".", "..") or part.startswith(".") for part in key.split("/")):
        raise ValueError(f"not a store key: {key!r}")
    return key


class Store(Protocol):
    def read(self, key: str) -> tuple[Any, str | None]: ...

    def write(self, key: str, data: Any, if_version: Any = ANY) -> str: ...

    def delete(self, key: str) -> None: ...

    def keys(self, prefix: str = "") -> list[str]: ...


def _dump(data) -> bytes:
    return json.dumps(data, indent=1).encode()  # the state file's format since spec A


def _version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


_LOCAL_LOCK = threading.Lock()  # one for every local store: FastAPI runs sync routes in a thread pool


class LocalStore:
    """JSON files under `root`; `paths` puts named keys elsewhere (the default user's state at STATE_PATH)."""

    def __init__(self, root: Path, paths: dict[str, Path] | None = None):
        self.root = Path(root)
        self.paths = {check_key(k): Path(p) for k, p in (paths or {}).items()}

    def path(self, key: str) -> Path:
        return self.paths.get(key) or self.root / check_key(key)

    def read(self, key: str) -> tuple[Any, str | None]:
        path = self.path(key)
        with _LOCAL_LOCK:
            if not path.exists():
                return None, None
            raw = path.read_bytes()
        return json.loads(raw), _version(raw)

    def write(self, key: str, data: Any, if_version: Any = ANY) -> str:
        path, raw = self.path(key), _dump(data)
        with _LOCAL_LOCK:
            if if_version is not ANY:
                current = _version(path.read_bytes()) if path.exists() else None
                if current != if_version:
                    raise Conflict(key)
            # a temp file in the same folder, then rename: a crash never leaves half a file
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=path.suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            os.replace(tmp, path)
        return _version(raw)

    def delete(self, key: str) -> None:
        path = self.path(key)
        with _LOCAL_LOCK:
            path.unlink(missing_ok=True)
            if key not in self.paths:  # folders emptied under root go too (an old live version)
                folder = path.parent
                while folder != self.root and folder.is_relative_to(self.root) and not any(folder.iterdir()):
                    folder.rmdir()
                    folder = folder.parent

    def keys(self, prefix: str = "") -> list[str]:
        found = {k for k, p in self.paths.items() if p.exists()}
        if self.root.exists():
            for p in self.root.rglob("*"):
                rel = p.relative_to(self.root).as_posix()
                if p.is_file() and not any(part.startswith(".") for part in rel.split("/")) and _KEY.fullmatch(rel):
                    found.add(rel)
        return sorted(k for k in found if k.startswith(prefix))


class MemoryStore:
    """In memory, for tests: versions count up."""

    def __init__(self):
        self.docs: dict[str, tuple[bytes, str]] = {}
        self._n = 0
        self._lock = threading.Lock()

    def read(self, key: str) -> tuple[Any, str | None]:
        with self._lock:
            doc = self.docs.get(check_key(key))
        return (json.loads(doc[0]), doc[1]) if doc else (None, None)

    def write(self, key: str, data: Any, if_version: Any = ANY) -> str:
        with self._lock:
            current = self.docs.get(check_key(key))
            if if_version is not ANY and (current[1] if current else None) != if_version:
                raise Conflict(key)
            self._n += 1
            self.docs[key] = (_dump(data), str(self._n))
            return str(self._n)

    def delete(self, key: str) -> None:
        with self._lock:
            self.docs.pop(check_key(key), None)

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return sorted(k for k in self.docs if k.startswith(prefix))


def _code(e: Exception) -> int | None:
    return getattr(e, "code", None)  # google.api_core's errors carry the HTTP status: 412, 404


class GcsStore:
    """One Cloud Storage object per key, under `prefix`, with the generation as the version."""

    READ_TRIES = 3

    def __init__(self, bucket, prefix: str = ""):
        self.bucket, self.prefix = bucket, prefix

    def _name(self, key: str) -> str:
        return self.prefix + check_key(key)

    def read(self, key: str) -> tuple[Any, str | None]:
        for _ in range(self.READ_TRIES):  # the object can change between its metadata and its bytes
            blob = self.bucket.get_blob(self._name(key))
            if blob is None:
                return None, None
            try:
                raw = blob.download_as_bytes(if_generation_match=blob.generation)
            except Exception as e:
                if _code(e) in (404, 412):
                    continue
                raise
            return json.loads(raw), str(blob.generation)
        raise Conflict(key)

    def write(self, key: str, data: Any, if_version: Any = ANY) -> str:
        blob = self.bucket.blob(self._name(key))
        match = None if if_version is ANY else 0 if if_version is None else int(if_version)
        try:
            blob.upload_from_string(_dump(data), content_type="application/json", if_generation_match=match)
        except Exception as e:
            if _code(e) == 412:
                raise Conflict(key) from None
            raise
        return str(blob.generation)

    def delete(self, key: str) -> None:
        try:
            self.bucket.blob(self._name(key)).delete()
        except Exception as e:
            if _code(e) != 404:
                raise

    def keys(self, prefix: str = "") -> list[str]:
        return sorted(b.name[len(self.prefix):] for b in self.bucket.list_blobs(prefix=self.prefix + prefix))
