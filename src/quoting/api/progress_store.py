from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("quoting.progress_store")

PIPELINE_STEPS = [
    "Mail vorbereiten",
    "Extraktion",
    "Matching",
    "Preisberechnung",
    "PDF-Rendering",
]

STEP_STATUS_MAP = {
    "started": "running",
    "completed": "completed",
    "failed": "failed",
    "skipped": "skipped",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress_path(review_dir: Path) -> Path:
    return review_dir / "progress.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def init_progress(review_dir: Path, review_id: str) -> dict[str, Any]:
    now = _now_iso()
    data: dict[str, Any] = {
        "review_id": review_id,
        "status": "running",
        "current_step": "Mail vorbereiten",
        "current_detail": "Review wird vorbereitet",
        "progress_percent": 0,
        "created_at": now,
        "updated_at": now,
        "steps": [
            {
                "name": step_name,
                "status": "running" if step_name == "Mail vorbereiten" else "pending",
                "detail": "Review wird vorbereitet" if step_name == "Mail vorbereiten" else "",
                "updated_at": now if step_name == "Mail vorbereiten" else None,
            }
            for step_name in PIPELINE_STEPS
        ],
        "result": None,
        "error": None,
    }
    write_progress(review_dir, data)
    return data


def read_progress(review_dir: Path) -> dict[str, Any] | None:
    path = progress_path(review_dir)
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_progress(review_dir: Path, data: dict[str, Any]) -> None:
    _atomic_write_json(progress_path(review_dir), data)


def update_step(
    review_dir: Path,
    step_name: str,
    status: str,
    detail: str = "",
) -> None:
    data = read_progress(review_dir)
    if data is None:
        return

    mapped_status = STEP_STATUS_MAP.get(status, status)
    now = _now_iso()

    steps = data.get("steps", [])

    for step in steps:
        if step.get("name") != step_name:
            continue

        step["status"] = mapped_status
        step["detail"] = detail
        step["updated_at"] = now
        break

    completed_count = sum(
        1 for step in steps if step.get("status") in {"completed", "skipped"}
    )
    total_count = len(steps) or 1

    data["progress_percent"] = int((completed_count / total_count) * 100)
    data["updated_at"] = now

    if mapped_status == "running":
        data["status"] = "running"
        data["current_step"] = step_name
        data["current_detail"] = detail
        data["error"] = None

    elif mapped_status == "completed":
        running_steps = [
            step for step in steps if step.get("status") == "running"
        ]
        next_pending = next(
            (step for step in steps if step.get("status") == "pending"),
            None,
        )

        if running_steps:
            data["current_step"] = running_steps[0].get("name", step_name)
            data["current_detail"] = running_steps[0].get("detail", "")
        elif next_pending:
            data["current_step"] = next_pending.get("name", step_name)
            data["current_detail"] = next_pending.get("detail", "")
        else:
            data["current_step"] = step_name
            data["current_detail"] = detail

    elif mapped_status == "failed":
        data["status"] = "failed"
        data["current_step"] = step_name
        data["current_detail"] = detail
        data["error"] = detail or f"Step failed: {step_name}"

    write_progress(review_dir, data)


def complete_progress(review_dir: Path, result: dict[str, Any]) -> None:
    data = read_progress(review_dir)
    if data is None:
        _log.warning("complete_progress: progress.json missing for %s — creating synthetic record", review_dir.name)
        data = {"review_id": review_dir.name, "status": "running", "steps": [], "result": None, "error": None}

    now = _now_iso()

    for step in data.get("steps", []):
        if step.get("status") in {"pending", "running"}:
            step["status"] = "completed"
            step["updated_at"] = now

    data["status"] = "completed"
    data["current_step"] = "Review bereit"
    data["current_detail"] = "Pipeline abgeschlossen"
    data["progress_percent"] = 100
    data["result"] = result
    data["error"] = None
    data["updated_at"] = now

    write_progress(review_dir, data)


def fail_progress(review_dir: Path, error: str) -> None:
    data = read_progress(review_dir)
    if data is None:
        _log.warning("fail_progress: progress.json missing for %s — creating synthetic record", review_dir.name)
        data = {"review_id": review_dir.name, "status": "running", "steps": [], "result": None, "error": None}

    now = _now_iso()

    for step in data.get("steps", []):
        if step.get("status") == "running":
            step["status"] = "failed"
            step["detail"] = error
            step["updated_at"] = now
            break

    data["status"] = "failed"
    data["current_detail"] = error
    data["error"] = error
    data["updated_at"] = now

    write_progress(review_dir, data)
