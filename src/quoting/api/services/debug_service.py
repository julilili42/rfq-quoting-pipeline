"""Configuration/health checks and LLM probing for the debug page."""

from __future__ import annotations

import csv
import math
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from quoting.reviews import default_artifact_root, get_default_repository


# --------------------------------------------------------------------------- models
class CheckResult(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str


class PipelineFailure(BaseModel):
    review_id: str
    subject: str
    sender: str
    current_step: str
    error: str
    updated_at: str
    progress_percent: int


class PipelineFailureSummary(BaseModel):
    total_failed: int
    recent: list[PipelineFailure]


class StammdatenQuality(BaseModel):
    path: str
    total_rows: int
    file_size_kb: int
    last_modified: str
    duplicate_article_numbers: int
    missing_article_numbers: int
    missing_descriptions: int
    zero_or_missing_prices: int
    invalid_price_ranges: int
    single_offer_articles: int
    missing_materials: int
    missing_dimensions: int
    sample_duplicate_articles: list[str]
    sample_zero_price_articles: list[str]


class LlmProbeUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class LlmProbeResult(BaseModel):
    status: Literal["ok", "error"]
    provider: str
    model: str
    checked_at: str
    latency_ms: int
    detail: str
    response_preview: str | None = None
    error_type: str | None = None
    usage: LlmProbeUsage | None = None


class DebugInfo(BaseModel):
    overall: Literal["ok", "warning", "error"]
    checks: list[CheckResult]
    llm_provider: str
    checked_at: str
    pipeline_failures: PipelineFailureSummary
    stammdaten_quality: StammdatenQuality | None


# --------------------------------------------------------------------------- helpers
def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    if math.isnan(result):
        return None
    return result


def _safe_int(value: object) -> int | None:
    raw = _safe_float(value)
    return int(raw) if raw is not None else None


def _safe_datetime(value: object, fallback_path: Path | None = None) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    if fallback_path is not None:
        try:
            return datetime.fromtimestamp(fallback_path.stat().st_mtime)
        except OSError:
            pass
    return datetime.fromtimestamp(0)


def llm_model_name(settings: Any) -> str:
    if settings.llm_provider == "gemini":
        return settings.gemini_model
    if settings.llm_provider == "azure":
        return settings.azure_model
    return "(unbekannt)"


def scrub_llm_error(message: str, settings: Any) -> str:
    scrubbed = message
    for secret in (settings.google_api_key, settings.nexus_api_key):
        if secret:
            scrubbed = scrubbed.replace(secret, "***")
    return scrubbed


# --------------------------------------------------------------------------- checks
def check_llm_key(settings: Any) -> CheckResult:
    provider = settings.llm_provider
    if provider == "gemini":
        key = settings.google_api_key or ""
        if key:
            return CheckResult(name="LLM API-Key (Gemini)", status="ok", detail=f"GOOGLE_API_KEY gesetzt ({len(key)} Zeichen)")
        return CheckResult(name="LLM API-Key (Gemini)", status="error", detail="GOOGLE_API_KEY fehlt oder leer")
    if provider == "azure":
        key = settings.nexus_api_key or ""
        if key:
            return CheckResult(name="LLM API-Key (Azure)", status="ok", detail=f"NEXUS_API_KEY gesetzt ({len(key)} Zeichen)")
        return CheckResult(name="LLM API-Key (Azure)", status="error", detail="NEXUS_API_KEY fehlt oder leer")
    return CheckResult(name="LLM Provider", status="error", detail=f"Unbekannter Provider: {provider!r}")


def check_llm_model(settings: Any) -> CheckResult:
    if settings.llm_provider == "gemini":
        model = settings.gemini_model
        thinking = settings.gemini_thinking_budget
        hint = f"Thinking-Budget: {thinking}" if thinking != 0 else "Thinking deaktiviert"
        return CheckResult(name="LLM Modell", status="ok", detail=f"{model} — {hint}")
    model = settings.azure_model
    endpoint = settings.azure_endpoint
    return CheckResult(name="LLM Modell", status="ok", detail=f"{model} @ {endpoint}")


def check_env_file(root: Path) -> CheckResult:
    env_file = root / ".env"
    if not env_file.exists():
        return CheckResult(name=".env Datei", status="error", detail=f"Nicht gefunden: {env_file} — Umgebungsvariablen fehlen möglicherweise")
    return CheckResult(name=".env Datei", status="ok", detail=str(env_file))


def check_stammdaten(path: Path) -> CheckResult:
    if not path.exists():
        return CheckResult(name="stammdaten.csv", status="error", detail=f"Datei nicht gefunden: {path}")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rows = max(0, len(lines) - 1)
        size_kb = round(path.stat().st_size / 1024)
        return CheckResult(name="stammdaten.csv", status="ok", detail=f"{rows:,} Einträge · {size_kb} KB")
    except OSError as e:
        return CheckResult(name="stammdaten.csv", status="error", detail=str(e))


def check_writable_dir(path: Path, label: str) -> CheckResult:
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return CheckResult(name=label, status="error", detail=str(e))
    probe = path / ".write_probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        return CheckResult(name=label, status="ok", detail=str(path))
    except OSError as e:
        return CheckResult(name=label, status="error", detail=f"Nicht beschreibbar: {e}")


def check_review_count() -> CheckResult:
    count = get_default_repository().review_count()
    if count == 0:
        return CheckResult(name="Vorhandene Reviews", status="ok", detail="Noch keine Reviews")
    return CheckResult(name="Vorhandene Reviews", status="ok", detail=f"{count} Review{'s' if count != 1 else ''}")


def check_disk_space(path: Path) -> CheckResult:
    import shutil as _shutil
    try:
        usage = _shutil.disk_usage(path)
        free_mb = usage.free // (1024 * 1024)
        free_gb = free_mb / 1024
        detail = f"{free_gb:.1f} GB frei von {usage.total / (1024 ** 3):.1f} GB"
        if free_mb < 200:
            return CheckResult(name="Speicherplatz", status="error", detail=f"Kritisch wenig: {detail}")
        if free_mb < 1024:
            return CheckResult(name="Speicherplatz", status="warning", detail=f"Wenig Speicher: {detail}")
        return CheckResult(name="Speicherplatz", status="ok", detail=detail)
    except OSError as e:
        return CheckResult(name="Speicherplatz", status="warning", detail=str(e))


def check_thresholds(settings: Any) -> CheckResult:
    return CheckResult(
        name="Matching-Schwellenwerte",
        status="ok",
        detail=f"Fuzzy: {settings.fuzzy_threshold} · Semantisch: {settings.semantic_threshold} · PDF-DPI: {settings.pdf_render_dpi}",
    )


def check_settings_file(path: Path) -> CheckResult:
    if not path.exists():
        return CheckResult(name="settings.json", status="warning", detail="Noch nicht erstellt — wird beim ersten Speichern angelegt")
    try:
        import json
        json.loads(path.read_text(encoding="utf-8"))
        return CheckResult(name="settings.json", status="ok", detail=str(path))
    except Exception as e:
        return CheckResult(name="settings.json", status="error", detail=f"Parse-Fehler: {e}")


# --------------------------------------------------------------------------- aggregations
def recent_pipeline_failures(
    settings: Any,
    *,
    limit: int = 5,
) -> PipelineFailureSummary:
    repo = get_default_repository()
    failures: list[tuple[float, PipelineFailure]] = []
    for row in repo.list_reviews():
        review_id = str(row["review_id"])
        progress = repo.load_progress(review_id)
        if progress is None:
            continue
        error = str(progress.get("error") or "").strip()
        if progress.get("status") != "failed" and not error:
            continue

        failed_step = next(
            (
                step for step in progress.get("steps") or []
                if isinstance(step, dict) and step.get("status") == "failed"
            ),
            None,
        )
        current_step = str(
            progress.get("current_step")
            or (failed_step or {}).get("name")
            or "Unbekannter Schritt"
        )
        detail = error or str(progress.get("current_detail") or "").strip()
        if not detail and isinstance(failed_step, dict):
            detail = str(failed_step.get("detail") or "").strip()

        mail = repo.load_mail(review_id) or {}
        updated = _safe_datetime(progress.get("updated_at"))
        try:
            progress_percent = int(progress.get("progress_percent") or 0)
        except (TypeError, ValueError):
            progress_percent = 0

        failures.append((
            updated.timestamp(),
            PipelineFailure(
                review_id=review_id,
                subject=str(mail.get("subject") or "(ohne Betreff)"),
                sender=str(mail.get("from") or mail.get("sender") or ""),
                current_step=current_step,
                error=scrub_llm_error(detail, settings),
                updated_at=updated.isoformat(timespec="seconds"),
                progress_percent=max(0, min(100, progress_percent)),
            ),
        ))

    failures.sort(key=lambda item: item[0], reverse=True)
    return PipelineFailureSummary(
        total_failed=len(failures),
        recent=[failure for _updated, failure in failures[:limit]],
    )


def stammdaten_quality(path: Path) -> StammdatenQuality | None:
    if not path.exists():
        return None

    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return None

    article_counts: dict[str, int] = {}
    missing_article_numbers = 0
    missing_descriptions = 0
    zero_or_missing_prices = 0
    invalid_price_ranges = 0
    single_offer_articles = 0
    missing_materials = 0
    missing_dimensions = 0
    zero_price_articles: list[str] = []

    for index, row in enumerate(rows, start=2):
        article = str(row.get("artikel_nr") or "").strip()
        if article:
            article_counts[article] = article_counts.get(article, 0) + 1
        else:
            missing_article_numbers += 1
            article = f"Zeile {index}"

        if not str(row.get("bezeichnung") or "").strip():
            missing_descriptions += 1

        basispreis = _safe_float(row.get("basispreis_eur"))
        if basispreis is None or basispreis <= 0:
            zero_or_missing_prices += 1
            if len(zero_price_articles) < 5:
                zero_price_articles.append(article)

        preis_min = _safe_float(row.get("preis_min_eur"))
        preis_max = _safe_float(row.get("preis_max_eur"))
        if preis_min is not None and preis_max is not None and preis_min > preis_max:
            invalid_price_ranges += 1

        n_offers = _safe_int(row.get("n_offers"))
        if n_offers == 1:
            single_offer_articles += 1

        if not str(row.get("werkstoff") or "").strip():
            missing_materials += 1
        if not str(row.get("abmessungen") or "").strip():
            missing_dimensions += 1

    duplicate_articles = [
        article for article, count in article_counts.items() if count > 1
    ]
    stat = path.stat()
    return StammdatenQuality(
        path=str(path),
        total_rows=len(rows),
        file_size_kb=round(stat.st_size / 1024),
        last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        duplicate_article_numbers=len(duplicate_articles),
        missing_article_numbers=missing_article_numbers,
        missing_descriptions=missing_descriptions,
        zero_or_missing_prices=zero_or_missing_prices,
        invalid_price_ranges=invalid_price_ranges,
        single_offer_articles=single_offer_articles,
        missing_materials=missing_materials,
        missing_dimensions=missing_dimensions,
        sample_duplicate_articles=duplicate_articles[:5],
        sample_zero_price_articles=zero_price_articles,
    )


def compute_debug_info(project_root: Path) -> DebugInfo:
    from quoting.core.config import load_settings

    settings = load_settings()
    data_dir = settings.data_dir
    artifact_root = default_artifact_root()
    failures = recent_pipeline_failures(settings)
    quality = stammdaten_quality(settings.stammdaten_path)

    checks: list[CheckResult] = [
        check_env_file(project_root),
        check_llm_key(settings),
        check_llm_model(settings),
        check_stammdaten(settings.stammdaten_path),
        check_writable_dir(artifact_root, "Review-Artefakte"),
        check_writable_dir(settings.output_dir, "Output-Verzeichnis"),
        check_review_count(),
        check_disk_space(data_dir),
        check_thresholds(settings),
        check_settings_file(data_dir / "settings.json"),
    ]

    statuses = {c.status for c in checks}
    if "error" in statuses:
        overall: Literal["ok", "warning", "error"] = "error"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "ok"

    return DebugInfo(
        overall=overall,
        checks=checks,
        llm_provider=settings.llm_provider,
        checked_at=datetime.now().isoformat(timespec="seconds"),
        pipeline_failures=failures,
        stammdaten_quality=quality,
    )


def probe_llm(timeout_s: int) -> LlmProbeResult:
    """Run an explicit, minimal provider call for the debug page."""
    from quoting.core.config import load_settings
    from quoting.extraction.llm import build_llm

    settings = load_settings()
    if settings.llm_provider == "azure":
        settings = replace(settings, llm_timeout_s=timeout_s)

    started = time.monotonic()
    checked_at = datetime.now().isoformat(timespec="seconds")
    provider = settings.llm_provider
    model = llm_model_name(settings)

    try:
        llm = build_llm(settings)
        response = llm.generate(
            'Dies ist ein Connectivity-Check. Antworte ausschließlich mit gültigem JSON: {"status":"ok"}',
            images=[],
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = None
        if response.usage is not None:
            usage = LlmProbeUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
            )
        preview = response.text.strip()
        return LlmProbeResult(
            status="ok",
            provider=provider,
            model=model,
            checked_at=checked_at,
            latency_ms=latency_ms,
            detail="Provider erreichbar; Testantwort erhalten.",
            response_preview=preview[:500] or "(leere Antwort)",
            usage=usage,
        )
    except Exception as exc:  # noqa: BLE001 - provider SDKs raise their own types
        latency_ms = int((time.monotonic() - started) * 1000)
        return LlmProbeResult(
            status="error",
            provider=provider,
            model=model,
            checked_at=checked_at,
            latency_ms=latency_ms,
            detail=scrub_llm_error(str(exc), settings) or "Unbekannter LLM-Fehler",
            error_type=type(exc).__name__,
        )
