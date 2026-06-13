#!/usr/bin/env python3
"""Verify DOCX temporary citations against EndNote .enl and sdb.eni records."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
from io_utils import atomic_write_json

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
TEMP_BLOCK = re.compile(r"\{([^{}]+, (?:19|20)\d{2} #\d+(?:; [^{}]+, (?:19|20)\d{2} #\d+)*)\}")
TEMP_ITEM = re.compile(r"(.+), ((?:19|20)\d{2}) #(\d+)$")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_author(author_field: object) -> str:
    first = clean(str(author_field or "").split("\r", 1)[0])
    if "," in first:
        return first.split(",", 1)[0].strip()
    return first.split(" ", 1)[0].strip()


def read_docx_text(docx: Path) -> str:
    with ZipFile(docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    return "".join(root.xpath(".//w:t/text()", namespaces=NS))


def load_refs(path: Path) -> tuple[dict[int, dict[str, str]], str]:
    refs: dict[int, dict[str, str]] = {}
    if not path.exists():
        return refs, "missing"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute("SELECT id, author, year, title, trash_state FROM refs").fetchall()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return refs, f"unreadable: {exc}"
    for rid, author, year, title, trash_state in rows:
        if int(trash_state or 0) == 0:
            refs[int(rid)] = {"first_author": first_author(author), "year": clean(year), "title": clean(title)}
    return refs, "ok"


def derived_sdb(enl: Path) -> Path:
    data = enl.with_suffix(".Data")
    return data / "sdb" / "sdb.eni"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--enl", required=True, type=Path)
    parser.add_argument("--sdb", type=Path)
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args()

    sdb = args.sdb or derived_sdb(args.enl)
    text = read_docx_text(args.docx)
    enl_refs, enl_status = load_refs(args.enl)
    sdb_refs, sdb_status = load_refs(sdb)
    preferred_refs = enl_refs if enl_refs else sdb_refs

    malformed: list[str] = []
    missing: list[dict[str, object]] = []
    mismatches: list[dict[str, object]] = []
    parsed: list[dict[str, object]] = []

    for block in TEMP_BLOCK.findall(text):
        for item in block.split("; "):
            match = TEMP_ITEM.match(item)
            if not match:
                malformed.append(item)
                continue
            author, year, rid_text = match.groups()
            rid = int(rid_text)
            parsed.append({"author": author, "year": year, "record_number": rid})
            record = preferred_refs.get(rid)
            if not record:
                missing.append({"record_number": rid, "item": item})
                continue
            if clean(year) != record["year"] or clean(author).lower() != record["first_author"].lower():
                mismatches.append(
                    {
                        "record_number": rid,
                        "item": item,
                        "citation_author": clean(author),
                        "endnote_author": record["first_author"],
                        "citation_year": year,
                        "endnote_year": record["year"],
                        "title": record["title"],
                    }
                )

    summary = {
        "docx": str(args.docx),
        "enl": str(args.enl),
        "sdb": str(sdb),
        "enl_status": enl_status,
        "sdb_status": sdb_status,
        "enl_active_records": len(enl_refs),
        "sdb_active_records": len(sdb_refs),
        "record_counts_match": enl_status == "ok" and sdb_status == "ok" and len(enl_refs) == len(sdb_refs),
        "temporary_citation_blocks": len(TEMP_BLOCK.findall(text)),
        "temporary_citation_items": len(parsed),
        "malformed_items": malformed,
        "missing_record_numbers": missing,
        "author_year_mismatches": mismatches,
        "failure_count": len(malformed) + len(missing) + len(mismatches),
    }
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.out_json, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
