#!/usr/bin/env python3
"""Infer and optionally create a manuscript-specific EndNote writeout."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import time
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
from io_utils import atomic_copy_file, atomic_copy_tree, atomic_write_json

CORE_NS = {"dc": "http://purl.org/dc/elements/1.1/"}
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_filename(value: str, max_len: int = 110) -> str:
    value = clean(value)
    value = re.sub(r"[/\\\\:*?\"<>|]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value or "Untitled manuscript")[:max_len].rstrip()


def default_endnote_dir(manuscript_dir: Path, today: dt.date | None = None) -> Path:
    today = today or dt.date.today()
    return manuscript_dir / f"autocite-{today:%d%m%y}"


def infer_title(docx: Path) -> str:
    with ZipFile(docx) as zf:
        try:
            core = ET.fromstring(zf.read("docProps/core.xml"))
            titles = [clean(t) for t in core.xpath(".//dc:title/text()", namespaces=CORE_NS) if clean(t)]
            if titles:
                return titles[0]
        except KeyError:
            pass
        document = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for p in document.xpath(".//w:p", namespaces=W_NS):
        text = clean("".join(p.xpath(".//w:t/text()", namespaces=W_NS)))
        if 12 <= len(text) <= 180:
            paragraphs.append(text)
    return paragraphs[0] if paragraphs else docx.stem


def choose_paths(docx: Path, suffix: str, reuse: bool, endnote_dir: Path | None = None) -> dict[str, Path | str]:
    manuscript_dir = docx.parent
    endnote_dir = endnote_dir or default_endnote_dir(manuscript_dir)
    title = safe_filename(infer_title(docx))
    stem = f"{title} {suffix}"
    enl = endnote_dir / f"{stem}.enl"
    data = endnote_dir / f"{stem}.Data"
    if not reuse and (enl.exists() or data.exists()):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        stem = f"{title} {timestamp} {suffix}"
        enl = endnote_dir / f"{stem}.enl"
        data = endnote_dir / f"{stem}.Data"
    return {"title": title, "stem": stem, "endnote_dir": endnote_dir, "enl": enl, "data": data, "sdb": data / "sdb" / "sdb.eni"}


def copy_template(template_enl: Path, template_data: Path, target_enl: Path, target_data: Path) -> None:
    if not template_enl.exists():
        raise FileNotFoundError(template_enl)
    if not template_data.exists():
        raise FileNotFoundError(template_data)
    target_enl.parent.mkdir(parents=True, exist_ok=True)
    atomic_copy_file(template_enl, target_enl)
    atomic_copy_tree(template_data, target_data)


def clear_records(sqlite_path: Path) -> None:
    conn = sqlite3.connect(sqlite_path)
    conn.create_function("EN_MAKE_SORT_KEY", 3, lambda value, *_args: clean(str(value)).lower())
    conn.create_collation("ENCI_Base", lambda left, right: (clean(left).lower() > clean(right).lower()) - (clean(left).lower() < clean(right).lower()))
    conn.create_collation("ENCIN_Base", lambda left, right: (clean(left).lower() > clean(right).lower()) - (clean(left).lower() < clean(right).lower()))
    try:
        for table in ("file_res", "refs", "refs_ord", "ret_watch"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM tag_members")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'refs'")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def clear_writeout_records(target_enl: Path, target_data: Path) -> None:
    clear_records(target_enl)
    sdb = target_data / "sdb" / "sdb.eni"
    if sdb.exists():
        clear_records(sdb)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--suffix", default="autocite-cwyw")
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--template-enl", type=Path)
    parser.add_argument("--template-data", type=Path)
    parser.add_argument("--endnote-dir", type=Path)
    parser.add_argument("--clear-template-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args()

    paths = choose_paths(args.docx, args.suffix, args.reuse, args.endnote_dir)
    created = False
    if args.template_enl or args.template_data:
        if not (args.template_enl and args.template_data):
            raise SystemExit("--template-enl and --template-data must be provided together")
        if not args.dry_run:
            copy_template(args.template_enl, args.template_data, paths["enl"], paths["data"])  # type: ignore[arg-type]
            if args.clear_template_records:
                clear_writeout_records(paths["enl"], paths["data"])  # type: ignore[arg-type]
            created = True

    summary = {
        "docx": str(args.docx),
        "inferred_title": paths["title"],
        "suffix": args.suffix,
        "stem": paths["stem"],
        "endnote_dir": str(paths["endnote_dir"]),
        "enl": str(paths["enl"]),
        "data": str(paths["data"]),
        "sdb": str(paths["sdb"]),
        "created_from_template": created,
        "cleared_template_records": bool(created and args.clear_template_records),
        "dry_run": args.dry_run,
        "exists": {
            "enl": Path(paths["enl"]).exists(),
            "data": Path(paths["data"]).exists(),
            "sdb": Path(paths["sdb"]).exists(),
        },
    }
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(args.out_json, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
