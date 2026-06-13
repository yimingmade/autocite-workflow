#!/usr/bin/env python3
"""Write an EndNote-importable RIS bundle from resolved reference metadata."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from io_utils import atomic_write_text


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data]
        for key in ("resolved", "rows", "records", "mappings"):
            if isinstance(data.get(key), list):
                return [dict(row) for row in data[key]]
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
    raise ValueError(f"Unsupported input: {path}")


def authors(row: dict[str, Any]) -> list[str]:
    raw = row.get("authors") or row.get("author") or row.get("first_author") or ""
    parts = re.split(r"\s*;\s*|\r|\n", str(raw))
    return [clean(part) for part in parts if clean(part)]


def write_ris(rows: list[dict[str, Any]], path: Path) -> int:
    written = 0
    lines: list[str] = []
    for row in rows:
        confidence = clean(row.get("confidence")).lower()
        title = clean(row.get("title") or row.get("resolved_references") or row.get("candidate_references"))
        year = clean(row.get("year"))
        if confidence == "low" or not title or not year:
            continue
        lines.append("TY  - JOUR")
        for author in authors(row):
            lines.append(f"AU  - {author}")
        lines.append(f"PY  - {year}")
        lines.append(f"TI  - {title}")
        if clean(row.get("journal")):
            lines.append(f"JO  - {clean(row.get('journal'))}")
        if clean(row.get("doi")):
            lines.append(f"DO  - {clean(row.get('doi'))}")
        if clean(row.get("pmid")):
            lines.append(f"AN  - {clean(row.get('pmid'))}")
        if clean(row.get("url")):
            lines.append(f"UR  - {clean(row.get('url'))}")
        if clean(row.get("evidence")):
            lines.append(f"N1  - {clean(row.get('evidence'))}")
        lines.extend(["ER  - ", ""])
        written += 1
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = load_rows(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = write_ris(rows, args.output)
    print(json.dumps({"input_rows": len(rows), "ris_records": written, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
