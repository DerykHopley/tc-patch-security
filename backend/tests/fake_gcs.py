"""A fake Cloud Storage bucket: the few calls of google-cloud-storage that app.store.GcsStore makes, in memory.

Like the real client: every write makes a new generation, `if_generation_match=0` means "only if the object doesn't
exist", and a failed precondition raises an error whose `code` is 412 (google.api_core.exceptions.PreconditionFailed),
a missing object one whose `code` is 404 (NotFound). `calls` records each upload and delete with its precondition.
"""


class PreconditionFailed(Exception):
    code = 412


class NotFound(Exception):
    code = 404


class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str, generation: int | None = None):
        self.bucket, self.name, self.generation = bucket, name, generation

    def _check(self, if_generation_match: int | None) -> None:
        current = self.bucket.objects.get(self.name)
        gen = current[1] if current else 0
        if if_generation_match is not None and if_generation_match != gen:
            raise PreconditionFailed(f"{self.name}: generation {gen}, not {if_generation_match}")

    def download_as_bytes(self, if_generation_match: int | None = None) -> bytes:
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        self._check(if_generation_match)
        return self.bucket.objects[self.name][0]

    def upload_from_string(self, data: bytes | str, content_type: str = "application/octet-stream",
                           if_generation_match: int | None = None) -> None:
        self.bucket.calls.append(("upload", self.name, if_generation_match))
        self._check(if_generation_match)
        self.bucket.generation += 1
        self.bucket.objects[self.name] = (data.encode() if isinstance(data, str) else data, self.bucket.generation)
        self.generation = self.bucket.generation

    def delete(self, if_generation_match: int | None = None) -> None:
        self.bucket.calls.append(("delete", self.name, if_generation_match))
        if self.name not in self.bucket.objects:
            raise NotFound(self.name)
        self._check(if_generation_match)
        del self.bucket.objects[self.name]


class FakeBucket:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, int]] = {}
        self.generation = 1000
        self.calls: list[tuple] = []

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def get_blob(self, name: str) -> FakeBlob | None:
        return FakeBlob(self, name, self.objects[name][1]) if name in self.objects else None

    def list_blobs(self, prefix: str = ""):
        return [FakeBlob(self, n, g) for n, (_, g) in sorted(self.objects.items()) if n.startswith(prefix)]
