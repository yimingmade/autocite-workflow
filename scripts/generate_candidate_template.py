#!/usr/bin/env python3
"""Create a deterministic candidate-map template from the comment audit."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from io_utils import atomic_write_csv, atomic_write_json

FIELDS = [
    "comment_id",
    "author",
    "date",
    "comment_text",
    "anchor_text",
    "paragraph_text",
    "candidate_references",
    "resolved_references",
    "confidence",
    "source_method",
    "record_numbers",
    "insertion_text",
    "doi",
    "pmid",
    "title",
    "first_author",
    "year",
    "journal",
    "evidence",
    "agent_agreement_status",
]


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data]
        for key in ("comments", "rows"):
            if isinstance(data.get(key), list):
                return [dict(row) for row in data[key]]
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
    raise ValueError(f"Unsupported comments input: {path}")


def source_method(signal: str, text: str) -> str:
    lowered = text.lower()
    if "doi" in signal or re.search(r"\b10\.\d{4,9}/\S+", text):
        return "doi"
    if "pmid" in signal or "pubmed" in lowered:
        return "pmid"
    if "url" in signal or "http://" in lowered or "https://" in lowered:
        return "url"
    if "brace_code" in signal:
        return "paper_code"
    if "code_number" in signal:
        return "paper_code_reference_number" if "+" not in text else "paper_code_plus_reference_number"
    if "citation_like" in signal:
        return "explicit_title"
    return "agent_inference"


def template_row(row: dict[str, Any]) -> dict[str, Any]:
    signal = clean(row.get("citation_signal"))
    comment_text = clean(row.get("comment_text"))
    method = source_method(signal, comment_text)
    confidence = "low" if signal == "weak_or_non_reference" else "moderate"
    evidence = "deterministic cue only; requires EndNote/PubMed/agent verification"
    if confidence == "low":
        evidence = "weak or non-reference comment unless another agent finds a citation target"
    return {
        "comment_id": row.get("comment_id", ""),
        "author": row.get("author", ""),
        "date": row.get("date", ""),
        "comment_text": comment_text,
        "anchor_text": row.get("anchor_text", ""),
        "paragraph_text": row.get("paragraph_text", ""),
        "candidate_references": comment_text if confidence != "low" else "",
        "resolved_references": "",
        "confidence": confidence,
        "source_method": method,
        "record_numbers": "",
        "insertion_text": "",
        "doi": "",
        "pmid": "",
        "title": "",
        "first_author": "",
        "year": "",
        "journal": "",
        "evidence": evidence,
        "agent_agreement_status": "not_checked",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_csv(path, rows, fieldnames=FIELDS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = [template_row(row) for row in load_rows(args.comments)]
    atomic_write_json(args.out_dir / "candidate_map.deterministic.json", rows)
    write_csv(args.out_dir / "candidate_map.deterministic.csv", rows)
    print(json.dumps({"candidate_rows": len(rows), "out_json": str(args.out_dir / "candidate_map.deterministic.json")}, indent=2))


if __name__ == "__main__":
    main()
