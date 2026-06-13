#!/usr/bin/env python3
"""Insert EndNote temporary citations after DOCX comment anchors."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import time
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree as ET
from io_utils import atomic_copy_file, atomic_write_csv, atomic_write_json

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "xml": "http://www.w3.org/XML/1998/namespace"}
W = f"{{{NS['w']}}}"
XML_SPACE = f"{{{NS['xml']}}}space"
TEMP_CITATION = re.compile(r"^\{[^{}]+, (?:19|20)\d{2} #\d+(?:; [^{}]+, (?:19|20)\d{2} #\d+)*\}$")


def load_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        for key in ("resolved", "rows", "mappings"):
            if isinstance(data.get(key), list):
                return data[key]
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def visible_text_hash(root: ET._Element) -> str:
    text = "".join(root.xpath(".//w:t/text()", namespaces=NS))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_run(text: str, template: ET._Element | None) -> ET._Element:
    run = ET.Element(f"{W}r")
    if template is not None:
        rpr = template.find(f"{W}rPr")
        if rpr is not None:
            run.append(deepcopy(rpr))
    t = ET.SubElement(run, f"{W}t")
    t.attrib[XML_SPACE] = "preserve"
    t.text = text
    return run


def insertion_points(root: ET._Element) -> dict[int, tuple[ET._Element, ET._Element | None]]:
    points: dict[int, tuple[ET._Element, ET._Element | None]] = {}
    for ref in root.xpath(".//w:commentReference", namespaces=NS):
        cid = int(ref.get(f"{W}id"))
        run = ref.getparent()
        if run is not None:
            points[cid] = (run, run)
    for end in root.xpath(".//w:commentRangeEnd", namespaces=NS):
        cid = int(end.get(f"{W}id"))
        points.setdefault(cid, (end, None))
    return points


def following_text(anchor: ET._Element, limit: int = 5) -> str:
    parent = anchor.getparent()
    if parent is None:
        return ""
    siblings = list(parent)
    index = siblings.index(anchor)
    return "".join("".join(s.xpath(".//w:t/text()", namespaces=NS)) for s in siblings[index + 1 : index + 1 + limit])


def replace_document_xml(docx: Path, document_xml: bytes) -> None:
    tmp = docx.with_suffix(".autocite.tmp.docx")
    with ZipFile(docx, "r") as src, ZipFile(tmp, "w", compression=ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, document_xml if item.filename == "word/document.xml" else src.read(item.filename))
    tmp.replace(docx)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    atomic_write_csv(path, rows, fieldnames=fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--resolved", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.resolved)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.docx) as zf:
        root = ET.fromstring(zf.read("word/document.xml"), parser=ET.XMLParser(remove_blank_text=False))
    before_hash = visible_text_hash(root)
    points = insertion_points(root)

    log: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda r: int(r.get("comment_id", 0))):
        cid = int(row.get("comment_id", 0))
        citation = str(row.get("insertion_text") or row.get("temporary_citation") or "").strip()
        confidence = str(row.get("confidence", "")).lower()
        status = "skipped"
        if confidence not in {"high", "moderate"}:
            status = "skipped_confidence"
        elif not TEMP_CITATION.match(citation):
            status = "skipped_bad_syntax"
        elif cid not in points:
            status = "missing_anchor"
        else:
            anchor, template = points[cid]
            if citation in following_text(anchor):
                status = "already_present"
            elif args.apply:
                parent = anchor.getparent()
                parent.insert(list(parent).index(anchor) + 1, make_run(citation, template))
                status = "inserted"
            else:
                status = "would_insert"
        log.append({"comment_id": cid, "status": status, "confidence": confidence, "insertion_text": citation})

    after_hash = visible_text_hash(root)
    backup = ""
    if args.apply:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = args.docx.with_name(f"{args.docx.stem}.before-autocite-insertions.{timestamp}{args.docx.suffix}")
        atomic_copy_file(args.docx, backup_path)
        backup = str(backup_path)
        replace_document_xml(args.docx, ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))

    summary = {
        "docx": str(args.docx),
        "apply": args.apply,
        "backup": backup,
        "rows": len(rows),
        "inserted_or_would_insert": sum(1 for row in log if row["status"] in {"inserted", "would_insert"}),
        "missing_anchor": sum(1 for row in log if row["status"] == "missing_anchor"),
        "bad_syntax": sum(1 for row in log if row["status"] == "skipped_bad_syntax"),
        "visible_text_sha256_before": before_hash,
        "visible_text_sha256_after_xml_edit": after_hash,
    }
    atomic_write_json(args.out_dir / "docx_insertion_summary.json", summary)
    atomic_write_json(args.out_dir / "docx_insertion_log.json", log)
    write_csv(args.out_dir / "docx_insertion_log.csv", log)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
