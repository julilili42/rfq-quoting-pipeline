from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path


def content_hash_from_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:16]


def save_upload_stable(uploaded, content_hash: str) -> Path:
    upload_dir = Path(tempfile.gettempdir()) / "quoting_uploads" / content_hash
    upload_dir.mkdir(parents=True, exist_ok=True)

    input_path = upload_dir / Path(uploaded.name).name

    if not input_path.exists():
        input_path.write_bytes(uploaded.getvalue())

    return input_path


def handle_upload(uploaded) -> tuple[Path, str, bytes]:
    payload = uploaded.getvalue()
    content_hash = content_hash_from_bytes(payload)
    input_path = save_upload_stable(uploaded, content_hash)

    return input_path, content_hash, payload