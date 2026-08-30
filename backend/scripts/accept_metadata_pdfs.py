from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.metadata_normalization import normalize_paper_metadata
from app.services.paper_fetching import parse_pdf_bytes


def inspect_pdf(path: Path) -> dict:
    snapshot = parse_pdf_bytes(path.read_bytes(), path.as_uri())
    text = str(snapshot.get("text") or "")
    spans = snapshot.get("page_spans") or []
    first_page = ""
    if spans:
        first_page = text[int(spans[0].get("start") or 0) : int(spans[0].get("end") or 0)]
    contract = normalize_paper_metadata(snapshot, first_page_text=first_page)
    normalized = contract["normalized_metadata"]
    return {
        "path": str(path),
        "title": normalized["title"],
        "authors": normalized["authors"],
        "candidate_boundaries": contract["candidate_boundaries"],
        "execution_status": contract["execution_status"],
        "fallback_reasons": contract["fallback_reasons"],
        "page_count_total": snapshot.get("page_count_total"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect generic PDF metadata normalization")
    parser.add_argument("pdf", nargs="+", type=Path)
    args = parser.parse_args()
    results = [inspect_pdf(path.resolve()) for path in args.pdf]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
