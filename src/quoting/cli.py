"""Command-line entry point.

Usage:
    python -m quoting.cli run path/to/rfq.pdf
    python -m quoting.cli run mail.eml --output ./results
    python -m quoting.cli batch ./inbox --output ./results
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import get_logger, load_settings
from .pipeline import QuotingPipeline

log = get_logger()

_SUPPORTED_EXT = {".pdf", ".eml", ".xlsx", ".xls", ".csv"}


def _cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        log.error("File not found: %s", input_path)
        return 1

    pipeline = QuotingPipeline(load_settings())
    try:
        result = pipeline.run(input_path, Path(args.output) if args.output else None)
    except Exception as exc:
        log.exception("Pipeline failed: %s", exc)
        return 2

    print(json.dumps(result.summary(), indent=2, ensure_ascii=False))
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    inbox = Path(args.inbox)
    if not inbox.is_dir():
        log.error("Not a directory: %s", inbox)
        return 1

    settings = load_settings()
    pipeline = QuotingPipeline(settings)
    output = Path(args.output) if args.output else settings.output_dir

    files = sorted(p for p in inbox.iterdir() if p.suffix.lower() in _SUPPORTED_EXT)
    if not files:
        log.warning("No supported files in %s", inbox)
        return 0

    log.info("Batch: %d file(s)", len(files))
    summaries: list[dict] = []
    failed = 0
    for f in files:
        try:
            res = pipeline.run(f, output)
            summaries.append(res.summary())
        except Exception as exc:
            failed += 1
            log.exception("Failed %s: %s", f.name, exc)
            summaries.append({"input": str(f), "error": str(exc)})

    print(json.dumps(summaries, indent=2, ensure_ascii=False))
    log.info("Batch done: %d OK, %d failed", len(files) - failed, failed)
    return 0 if failed == 0 else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quoting-pipeline",
        description="AI-assisted draft quotation generator",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="process a single RFQ file")
    p_run.add_argument("input", help="path to PDF / EML / XLSX / CSV")
    p_run.add_argument("-o", "--output", help="output directory")
    p_run.set_defaults(func=_cmd_run)

    p_batch = sub.add_parser("batch", help="process all supported files in a folder")
    p_batch.add_argument("inbox", help="folder with RFQ files")
    p_batch.add_argument("-o", "--output", help="output directory")
    p_batch.set_defaults(func=_cmd_batch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
