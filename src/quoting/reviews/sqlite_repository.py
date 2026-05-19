"""SQLite-backed review persistence.

SQLite is the source of truth for review state. Binary artifacts
(uploaded originals, generated PDFs) stay on disk and are tracked via the
``documents`` table.

Payloads are stored as JSON blobs in ``review_payloads``. Callers should
prefer the typed accessors (``load_mail`` / ``save_mail`` etc.) over the
raw ``load_payload`` / ``save_payload`` plumbing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "quoting.sqlite"
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "data" / "artifacts" / "reviews"


class Payloads:
    """Canonical payload keys stored in the ``review_payloads`` table."""

    MAIL = "mail"
    APPROVAL = "approval"
    PROGRESS = "progress"
    EXTRACTED = "extracted"
    ANFRAGE_REVIEWED = "anfrage_reviewed"
    MATCHES = "matches"
    MATCHES_REVIEWED = "matches_reviewed"
    MANUAL_OVERRIDES = "manual_overrides"
    QUOTATION = "quotation"
    QUOTATION_REVIEWED = "quotation_reviewed"


# Legacy keys produced before payload names dropped their ``.json`` suffix
# and pipeline-step prefixes. Renamed in place on startup.
_LEGACY_PAYLOAD_RENAMES = {
    "mail.json": Payloads.MAIL,
    "approval.json": Payloads.APPROVAL,
    "progress.json": Payloads.PROGRESS,
    "01_extracted.json": Payloads.EXTRACTED,
    "anfrage_reviewed.json": Payloads.ANFRAGE_REVIEWED,
    "02_matches.json": Payloads.MATCHES,
    "matches_reviewed.json": Payloads.MATCHES_REVIEWED,
    "manual_overrides.json": Payloads.MANUAL_OVERRIDES,
    "03_quotation.json": Payloads.QUOTATION,
    "quotation_reviewed.json": Payloads.QUOTATION_REVIEWED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def default_db_path() -> Path:
    raw = os.getenv("QUOTING_DB_PATH")
    return Path(raw) if raw else DEFAULT_DB_PATH


def default_artifact_root() -> Path:
    raw = os.getenv("QUOTING_ARTIFACT_ROOT")
    return Path(raw) if raw else DEFAULT_ARTIFACT_ROOT


class SQLiteReviewRepository:
    """Persistence boundary for reviews and their artifacts."""

    def __init__(self, db_path: Path | None = None, artifact_root: Path | None = None):
        self.db_path = Path(db_path or default_db_path())
        self.artifact_root = Path(artifact_root or default_artifact_root())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ------------------------------------------------------------------ setup
    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL DEFAULT '',
                    sender TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'api',
                    status TEXT NOT NULL DEFAULT 'running',
                    approval_state TEXT NOT NULL DEFAULT 'draft_generated',
                    final_pdf_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS review_payloads (
                    review_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (review_id, name),
                    FOREIGN KEY (review_id) REFERENCES reviews(review_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT,
                    storage_path TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (review_id) REFERENCES reviews(review_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_documents_review_kind
                    ON documents(review_id, kind, is_current);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_current_name
                    ON documents(review_id, kind, filename, is_current)
                    WHERE is_current = 1;
                """
            )
            self._rename_legacy_payloads(conn)

    def _rename_legacy_payloads(self, conn: sqlite3.Connection) -> None:
        for old, new in _LEGACY_PAYLOAD_RENAMES.items():
            conn.execute(
                "UPDATE OR IGNORE review_payloads SET name=? WHERE name=?",
                (new, old),
            )
            conn.execute("DELETE FROM review_payloads WHERE name=?", (old,))

    # ---------------------------------------------------------------- reviews
    def artifact_dir(self, review_id: str) -> Path:
        return self.artifact_root / review_id

    def create_review(
        self,
        review_id: str,
        *,
        subject: str = "",
        sender: str = "",
        body: str = "",
        source: str = "api",
    ) -> None:
        now = _now_iso()
        self.artifact_dir(review_id).mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews
                    (review_id, subject, sender, body, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    subject=excluded.subject,
                    sender=excluded.sender,
                    body=excluded.body,
                    source=excluded.source,
                    deleted_at=NULL,
                    updated_at=excluded.updated_at
                """,
                (review_id, subject, sender, body, source, now, now),
            )

    def ensure_review(self, review_id: str) -> None:
        now = _now_iso()
        self.artifact_dir(review_id).mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO reviews
                    (review_id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (review_id, now, now),
            )

    def exists(self, review_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM reviews WHERE review_id=? AND deleted_at IS NULL",
                (review_id,),
            ).fetchone()
        return row is not None

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM reviews
                WHERE review_id=? AND deleted_at IS NULL
                """,
                (review_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_reviews(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reviews
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def review_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM reviews WHERE deleted_at IS NULL"
            ).fetchone()
        return int(row["count"] if row else 0)

    def delete_review(self, review_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM reviews WHERE review_id=?", (review_id,))

    def list_review_ids(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT review_id FROM reviews
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [str(row["review_id"]) for row in rows]

    # -------------------------------------------------------------- payloads
    def load_payload(self, review_id: str, name: str) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM review_payloads
                WHERE review_id=? AND name=?
                """,
                (review_id, name),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(str(row["payload_json"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def save_payload(self, review_id: str, name: str, value: Any) -> None:
        self.ensure_review(review_id)
        payload = _jsonable(value)
        payload_json = json.dumps(payload, ensure_ascii=False)
        now = _now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO review_payloads
                    (review_id, name, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(review_id, name) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (review_id, name, payload_json, now, now),
            )
            conn.execute(
                "UPDATE reviews SET updated_at=? WHERE review_id=?",
                (now, review_id),
            )
            self._sync_review_columns(conn, review_id, name, payload, now)

    def delete_payload(self, review_id: str, name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM review_payloads WHERE review_id=? AND name=?",
                (review_id, name),
            )

    def has_payload(self, review_id: str, name: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM review_payloads WHERE review_id=? AND name=?",
                (review_id, name),
            ).fetchone()
        return row is not None

    def reset_review_state(self, review_id: str, *, keep: set[str]) -> None:
        now = _now_iso()
        with self.connect() as conn:
            placeholders = ",".join("?" for _ in keep) if keep else None
            if placeholders:
                conn.execute(
                    f"""
                    DELETE FROM review_payloads
                    WHERE review_id=? AND name NOT IN ({placeholders})
                    """,
                    [review_id, *sorted(keep)],
                )
            else:
                conn.execute(
                    "DELETE FROM review_payloads WHERE review_id=?",
                    (review_id,),
                )
            conn.execute(
                """
                UPDATE reviews
                SET status='running',
                    approval_state='draft_generated',
                    final_pdf_path=NULL,
                    updated_at=?
                WHERE review_id=?
                """,
                (now, review_id),
            )

    # ----------------------------------------------------------- typed accessors
    def load_mail(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.MAIL)
        return data if isinstance(data, dict) else None

    def save_mail(self, review_id: str, mail: dict[str, Any]) -> None:
        self.save_payload(review_id, Payloads.MAIL, mail)

    def load_approval(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.APPROVAL)
        return data if isinstance(data, dict) else None

    def save_approval(self, review_id: str, approval: dict[str, Any]) -> None:
        self.save_payload(review_id, Payloads.APPROVAL, approval)

    def load_progress(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.PROGRESS)
        return data if isinstance(data, dict) else None

    def save_progress(self, review_id: str, progress: dict[str, Any]) -> None:
        self.save_payload(review_id, Payloads.PROGRESS, progress)

    def load_extracted(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.EXTRACTED)
        return data if isinstance(data, dict) else None

    def save_extracted(self, review_id: str, anfrage: Any) -> None:
        self.save_payload(review_id, Payloads.EXTRACTED, anfrage)

    def load_anfrage_reviewed(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.ANFRAGE_REVIEWED)
        return data if isinstance(data, dict) else None

    def save_anfrage_reviewed(self, review_id: str, anfrage: Any) -> None:
        self.save_payload(review_id, Payloads.ANFRAGE_REVIEWED, anfrage)

    def load_anfrage(self, review_id: str) -> dict[str, Any] | None:
        return self.load_anfrage_reviewed(review_id) or self.load_extracted(review_id)

    def load_matches_initial(self, review_id: str) -> list | None:
        data = self.load_payload(review_id, Payloads.MATCHES)
        return data if isinstance(data, list) else None

    def save_matches_initial(self, review_id: str, matches: Any) -> None:
        self.save_payload(review_id, Payloads.MATCHES, matches)

    def load_matches_reviewed(self, review_id: str) -> list | None:
        data = self.load_payload(review_id, Payloads.MATCHES_REVIEWED)
        return data if isinstance(data, list) else None

    def save_matches_reviewed(self, review_id: str, matches: Any) -> None:
        self.save_payload(review_id, Payloads.MATCHES_REVIEWED, matches)

    def has_matches_reviewed(self, review_id: str) -> bool:
        return self.has_payload(review_id, Payloads.MATCHES_REVIEWED)

    def load_matches(self, review_id: str) -> list:
        return (
            self.load_matches_reviewed(review_id)
            or self.load_matches_initial(review_id)
            or []
        )

    def load_overrides(self, review_id: str) -> list:
        data = self.load_payload(review_id, Payloads.MANUAL_OVERRIDES)
        return data if isinstance(data, list) else []

    def save_overrides(self, review_id: str, overrides: Any) -> None:
        self.save_payload(review_id, Payloads.MANUAL_OVERRIDES, overrides)

    def load_quotation_initial(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.QUOTATION)
        return data if isinstance(data, dict) else None

    def save_quotation_initial(self, review_id: str, quotation: Any) -> None:
        self.save_payload(review_id, Payloads.QUOTATION, quotation)

    def load_quotation_reviewed(self, review_id: str) -> dict[str, Any] | None:
        data = self.load_payload(review_id, Payloads.QUOTATION_REVIEWED)
        return data if isinstance(data, dict) else None

    def save_quotation_reviewed(self, review_id: str, quotation: Any) -> None:
        self.save_payload(review_id, Payloads.QUOTATION_REVIEWED, quotation)

    def load_quotation(self, review_id: str) -> dict[str, Any] | None:
        return self.load_quotation_reviewed(review_id) or self.load_quotation_initial(
            review_id
        )

    # ------------------------------------------------------------- documents
    def register_document(
        self,
        review_id: str,
        *,
        kind: str,
        path: Path,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> None:
        self.ensure_review(review_id)
        path = Path(path)
        filename = Path(filename or path.name).name
        try:
            data = path.read_bytes()
            size_bytes = len(data)
            digest = hashlib.sha256(data).hexdigest()
        except OSError:
            size_bytes = 0
            digest = None

        now = _now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET is_current=0
                WHERE review_id=? AND kind=? AND filename=? AND is_current=1
                """,
                (review_id, kind, filename),
            )
            row = conn.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM documents
                WHERE review_id=? AND kind=? AND filename=?
                """,
                (review_id, kind, filename),
            ).fetchone()
            version = int(row["next_version"] if row else 1)
            conn.execute(
                """
                INSERT INTO documents
                    (review_id, kind, filename, content_type, size_bytes, sha256,
                     storage_path, version, is_current, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    review_id,
                    kind,
                    filename,
                    content_type,
                    size_bytes,
                    digest,
                    str(path),
                    version,
                    now,
                ),
            )
            conn.execute(
                "UPDATE reviews SET updated_at=? WHERE review_id=?",
                (now, review_id),
            )

    def current_document(
        self,
        review_id: str,
        *,
        kind: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any] | None:
        clauses = ["review_id=?", "is_current=1"]
        params: list[Any] = [review_id]
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        if filename is not None:
            clauses.append("filename=?")
            params.append(Path(filename).name)
        where = " AND ".join(clauses)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM documents
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return dict(row) if row is not None else None

    def list_documents(self, review_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        clauses = ["review_id=?", "is_current=1"]
        params: list[Any] = [review_id]
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        where = " AND ".join(clauses)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM documents
                WHERE {where}
                ORDER BY created_at ASC, id ASC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_documents_except(self, review_id: str, *, keep_kinds: set[str]) -> None:
        placeholders = ",".join("?" for _ in keep_kinds)
        with self.connect() as conn:
            if keep_kinds:
                conn.execute(
                    f"""
                    DELETE FROM documents
                    WHERE review_id=? AND kind NOT IN ({placeholders})
                    """,
                    [review_id, *sorted(keep_kinds)],
                )
            else:
                conn.execute("DELETE FROM documents WHERE review_id=?", (review_id,))

    # ----------------------------------------------------------- sync hooks
    def _sync_review_columns(
        self,
        conn: sqlite3.Connection,
        review_id: str,
        name: str,
        payload: Any,
        now: str,
    ) -> None:
        """Mirror a few payload fields onto the ``reviews`` row for cheap querying."""
        if name == Payloads.MAIL and isinstance(payload, dict):
            conn.execute(
                """
                UPDATE reviews
                SET subject=?, sender=?, body=?, updated_at=?
                WHERE review_id=?
                """,
                (
                    str(payload.get("subject") or ""),
                    str(payload.get("from") or payload.get("sender") or ""),
                    str(payload.get("body") or ""),
                    now,
                    review_id,
                ),
            )
        elif name == Payloads.PROGRESS and isinstance(payload, dict):
            conn.execute(
                "UPDATE reviews SET status=?, updated_at=? WHERE review_id=?",
                (str(payload.get("status") or "running"), now, review_id),
            )
        elif name == Payloads.APPROVAL and isinstance(payload, dict):
            conn.execute(
                """
                UPDATE reviews
                SET approval_state=?, final_pdf_path=?, updated_at=?
                WHERE review_id=?
                """,
                (
                    str(payload.get("state") or "draft_generated"),
                    payload.get("final_pdf_path"),
                    now,
                    review_id,
                ),
            )


_DEFAULT_REPOSITORY: SQLiteReviewRepository | None = None


def get_default_repository() -> SQLiteReviewRepository:
    global _DEFAULT_REPOSITORY
    db_path = default_db_path()
    artifact_root = default_artifact_root()
    if (
        _DEFAULT_REPOSITORY is None
        or _DEFAULT_REPOSITORY.db_path != db_path
        or _DEFAULT_REPOSITORY.artifact_root != artifact_root
    ):
        _DEFAULT_REPOSITORY = SQLiteReviewRepository(db_path, artifact_root)
    return _DEFAULT_REPOSITORY


def reset_default_repository() -> None:
    """Test helper for code that changes DB-related environment variables."""
    global _DEFAULT_REPOSITORY
    _DEFAULT_REPOSITORY = None
