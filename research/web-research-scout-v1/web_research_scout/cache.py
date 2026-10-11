"""Content-addressed local bundles: atomic activation, one coherent read."""

import errno
import json
import os
import tempfile
from pathlib import Path

from .security import SafeError, digest, load_json, relative_file

MAX_FILE = 2_000_000
MAX_BUNDLE = 16_000_000


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


class EvidenceCache:
    def __init__(self, root):
        self.root = Path(root)

    def read(self):
        try:
            with relative_file(self.root, "ACTIVE.json").open("rb") as file:
                pointer = load_json(file.read(4097))
            revision = pointer["revision"]
            if (
                not isinstance(revision, str)
                or len(revision) != 64
                or any(c not in "0123456789abcdef" for c in revision)
            ):
                raise SafeError("invalid_cache_pointer")
            bundle = relative_file(self.root, "revisions/" + revision)
            path = relative_file(bundle, "manifest.json")
            with path.open("rb") as file:
                raw = file.read(MAX_FILE + 1)
            if len(raw) > MAX_FILE or digest(raw) != revision:
                raise SafeError("cache_manifest_integrity_failed")
            manifest = load_json(raw)
            files = {}
            total = 0
            if (
                manifest.get("schema_version") != "web-scout-cache.1"
                or not 1 <= len(manifest["files"]) <= 128
            ):
                raise SafeError("invalid_cache_manifest")
            for name, expected in manifest["files"].items():
                path = relative_file(bundle, name)
                with path.open("rb") as file:
                    raw = file.read(MAX_FILE + 1)
                total += len(raw)
                if len(raw) > MAX_FILE or total > MAX_BUNDLE:
                    raise SafeError("cache_size_limit")
                if digest(raw) != expected:
                    raise SafeError("cache_file_integrity_failed")
                files[name] = load_json(raw)
            return revision, files
        except SafeError:
            raise
        except Exception:
            raise SafeError("cache_unavailable_or_invalid") from None

    def activate(self, documents):
        self.root.mkdir(parents=True, exist_ok=True)
        revisions = relative_file(self.root, "revisions")
        revisions.mkdir(exist_ok=True)
        if "manifest.json" in documents:
            raise SafeError("reserved_evidence_path")
        files = {name: encoded(body) for name, body in documents.items()}
        if (
            not files
            or len(files) > 128
            or any(len(raw) > MAX_FILE for raw in files.values())
            or sum(map(len, files.values())) > MAX_BUNDLE
        ):
            raise SafeError("cache_size_limit")
        manifest = {
            "schema_version": "web-scout-cache.1",
            "files": {name: digest(raw) for name, raw in files.items()},
        }
        raw = encoded(manifest)
        revision = digest(raw)
        target = revisions / revision
        if not target.exists():
            with tempfile.TemporaryDirectory(dir=revisions, prefix=".staging-") as tmp:
                stage = Path(tmp) / "bundle"
                stage.mkdir()
                for name, body in {**files, "manifest.json": raw}.items():
                    path = relative_file(stage, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("wb") as file:
                        file.write(body)
                        file.flush()
                        os.fsync(file.fileno())
                try:
                    os.rename(stage, target)
                except OSError as error:
                    if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                        raise
        # Verify stored bytes before activation; a hash-corrupt existing bundle
        # must not replace a good ACTIVE pointer.
        for name, expected in manifest["files"].items():
            with relative_file(target, name).open("rb") as file:
                stored = file.read(MAX_FILE + 1)
            if digest(stored) != expected:
                raise SafeError("cache_file_integrity_failed")
        if relative_file(target, "manifest.json").read_bytes() != raw:
            raise SafeError("cache_manifest_integrity_failed")
        pointer = {"schema_version": "web-scout-active.1", "revision": revision}
        fd, name = tempfile.mkstemp(dir=self.root, prefix=".active-")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(encoded(pointer))
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.root / "ACTIVE.json")
            handle = os.open(self.root, os.O_RDONLY)
            os.fsync(handle)
            os.close(handle)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return revision
