#!/usr/bin/env python3
"""Export and verify EndNote record numbers from .enl and sdb.eni."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from io_utils import atomic_write_csv, atomic_write_json


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_author(author_field: Any) -> str:
    first = clean(str(author_field or "").split("\r", 1)[0])
    return first.split(",", 1)[0].strip()


def derived_sdb(enl: Path) -> Path:
    return enl.with_suffix(".Data") / "sdb" / "sdb.eni"


def read_refs(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT id, author, year, title, secondary_title, accession_number, electronic_resource_number, trash_state FROM refs"
        ).fetchall()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return [], f"unreadable: {exc}"
    refs = []
    for rid, author, year, title, journal, pmid, doi, trash_state in rows:
        if int(trash_state or 0) != 0:
            continue
        refs.append(
            {
                "record_number": int(rid),
                "first_author": first_author(author),
                "authors": clean(str(author or "").replace("\r", "; ")),
                "year": clean(year),
                "title": clean(title),
                "journal": clean(journal),
                "pmid": clean(pmid),
                "doi": clean(doi),
            }
        )
    return refs, "ok"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["record_number", "first_author", "authors", "year", "title", "journal", "pmid", "doi"]
    atomic_write_csv(path, rows, fieldnames=fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enl", required=True, type=Path)
    parser.add_argument("--sdb", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    sdb = args.sdb or derived_sdb(args.enl)
    enl_refs, enl_status = read_refs(args.enl)
    sdb_refs, sdb_status = read_refs(sdb)
    chosen = enl_refs if enl_refs else sdb_refs
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "endnote_record_number_map.csv", chosen)
    atomic_write_json(args.out_dir / "endnote_record_number_map.json", chosen)
    summary = {
        "enl": str(args.enl),
        "sdb": str(sdb),
        "enl_status": enl_status,
        "sdb_status": sdb_status,
        "enl_active_records": len(enl_refs),
        "sdb_active_records": len(sdb_refs),
        "record_counts_match": enl_status == "ok" and sdb_status == "ok" and len(enl_refs) == len(sdb_refs),
        "exported_records": len(chosen),
        "record_number_min": min((row["record_number"] for row in chosen), default=None),
        "record_number_max": max((row["record_number"] for row in chosen), default=None),
    }
    atomic_write_json(args.out_dir / "endnote_record_number_map_summary.json", summary, ensure_ascii=True)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
