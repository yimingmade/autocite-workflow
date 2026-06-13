#!/usr/bin/env python3
"""Reconcile per-agent reference mappings into resolved and excluded rows."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from io_utils import atomic_write_csv, atomic_write_json


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).strip()


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".json" else None
    if isinstance(data, list):
        return [dict(row) for row in data]
    if isinstance(data, dict):
        for key in ("rows", "comments", "mappings", "resolved"):
            if isinstance(data.get(key), list):
                return [dict(row) for row in data[key]]
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    raise ValueError(f"Cannot load candidate rows from {path}")


def identity(row: dict[str, Any]) -> str:
    parts = [
        clean(row.get("record_numbers")),
        clean(row.get("doi")).lower(),
        clean(row.get("pmid")),
        clean(row.get("title")).lower(),
        clean(row.get("insertion_text")),
    ]
    return "|".join(part for part in parts if part)


def confidence_rank(value: str) -> int:
    return {"low": 0, "moderate": 1, "high": 2}.get(value.lower(), 0)


def reconcile(files: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in files:
        for row in load_rows(file):
            cid = clean(row.get("comment_id") if row.get("comment_id") is not None else row.get("id"))
            if not cid:
                continue
            row["_source_file"] = str(file)
            grouped[cid].append(row)

    resolved: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for cid in sorted(grouped, key=lambda x: int(x) if x.isdigit() else x):
        rows = grouped[cid]
        identities = {identity(row) for row in rows if identity(row)}
        low_seen = any(clean(row.get("confidence")).lower() == "low" for row in rows)
        if len(identities) == 1 and not low_seen:
            best = max(rows, key=lambda row: confidence_rank(clean(row.get("confidence"))))
            out = dict(best)
            out["comment_id"] = cid
            out["agent_agreement_status"] = "agreement"
            out["agent_votes"] = len(rows)
            out["confidence"] = clean(out.get("confidence")) or "moderate"
            resolved.append(out)
        else:
            representative = dict(rows[0])
            representative["comment_id"] = cid
            representative["confidence"] = "low"
            representative["exclusion_reason"] = (
                "agent disagreement or unresolved identity" if len(identities) != 1 else "low confidence from at least one agent"
            )
            representative["candidate_identities"] = "; ".join(sorted(identities))
            representative["agent_votes"] = len(rows)
            excluded.append(representative)
    return resolved, excluded


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row if not key.startswith("_")})
    cleaned = [{key: value for key, value in row.items() if key in fields} for row in rows]
    atomic_write_csv(path, cleaned, fieldnames=fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-file", action="append", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    resolved, excluded = reconcile(args.candidate_file)
    atomic_write_json(args.out_dir / "resolved_comments.json", resolved)
    atomic_write_json(args.out_dir / "excluded_comments.json", excluded)
    write_csv(args.out_dir / "resolved_comments.csv", resolved)
    write_csv(args.out_dir / "excluded_comments.csv", excluded)
    print(json.dumps({"resolved": len(resolved), "excluded": len(excluded), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
