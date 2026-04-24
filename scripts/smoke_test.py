"""End-to-end smoke test: runs the full pipeline on a file, no tests.

Usage:
    python scripts/smoke_test.py path/to/rfq.pdf
"""
import sys
from pathlib import Path

# Make `quoting` importable without installing
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from quoting.pipeline import QuotingPipeline  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_test.py <input-file> [output-dir]")
        return 1

    input_path = Path(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else _ROOT / "out"

    if not input_path.exists():
        print(f"Not found: {input_path}")
        return 1

    pipeline = QuotingPipeline()
    result = pipeline.run(input_path, output)

    print("\n--- SUMMARY ---")
    for k, v in result.summary().items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
