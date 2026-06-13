#!/usr/bin/env python3
"""Extract Word comments, anchors, and paragraph context from a DOCX."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
from io_utils import atomic_write_csv, atomic_write_json

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
W = f"{{{NS['w']}}}"
W14 = f"{{{NS['w14']}}}"


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def element_text(element: ET._Element) -> str:
    return "".join(element.xpath(".//w:t/text()", namespaces=NS))


def citation_signal(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b10\.\d{4,9}/\S+", text) or "doi" in lowered:
        return "doi"
    if "pubmed" in lowered or re.search(r"\bpmid\b", lowered):
        return "pmid"
    if "http://" in lowered or "https://" in lowered:
        return "url"
    if re.search(r"\{[^}]+\}", text):
        return "brace_code"
    if re.search(r"\b[A-Za-z][A-Za-z ._-]{1,40}\s*\+?\s*\d+(?:\s*[,;-]\s*\d+)*\b", text):
        return "code_number"
    if re.search(r"\b(et al\.|jacc|lancet|circulation|hepatology|gastroenterology|journal|nature|guideline)\b", lowered):
        return "citation_like"
    return "weak_or_non_reference"


def extract_comments(docx: Path) -> list[dict[str, object]]:
    with ZipFile(docx) as zf:
        comments_xml = zf.read("word/comments.xml")
        document_xml = zf.read("word/document.xml")

    comments_root = ET.fromstring(comments_xml)
    document_root = ET.fromstring(document_xml)

    comments: dict[int, dict[str, object]] = {}
    for comment in comments_root.xpath(".//w:comment", namespaces=NS):
        cid = int(comment.get(f"{W}id"))
        comments[cid] = {
            "comment_id": cid,
            "author": comment.get(f"{W}author", ""),
            "date": comment.get(f"{W}date", ""),
            "comment_text": clean(element_text(comment)),
        }

    anchors: dict[int, dict[str, object]] = {}
    for p_index, paragraph in enumerate(document_root.xpath(".//w:p", namespaces=NS), start=1):
        pieces: list[str] = []
        positions: list[tuple[str, int, int]] = []
        char_pos = 0
        for elem in paragraph.iter():
            if elem.tag == f"{W}commentRangeStart":
                positions.append(("start", int(elem.get(f"{W}id")), char_pos))
            elif elem.tag == f"{W}commentRangeEnd":
                positions.append(("end", int(elem.get(f"{W}id")), char_pos))
            elif elem.tag == f"{W}t":
                text = elem.text or ""
                pieces.append(text)
                char_pos += len(text)
        paragraph_text = "".join(pieces)
        starts = {cid: pos for typ, cid, pos in positions if typ == "start"}
        ends = {cid: pos for typ, cid, pos in positions if typ == "end"}
        for cid, start in starts.items():
            end = ends.get(cid, start)
            anchors[cid] = {
                "paragraph_index": p_index,
                "paragraph_id": paragraph.get(f"{W14}paraId", ""),
                "anchor_start": start,
                "anchor_end": end,
                "anchor_text": clean(paragraph_text[start:end]),
                "paragraph_text": clean(paragraph_text),
                "anchor_context": clean(paragraph_text[max(0, start - 200) : min(len(paragraph_text), end + 200)]),
            }

    rows: list[dict[str, object]] = []
    for cid in sorted(comments):
        row = dict(comments[cid])
        row.update(anchors.get(cid, {}))
        row["has_anchor"] = cid in anchors
        row["citation_signal"] = citation_signal(str(row["comment_text"]))
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    atomic_write_csv(path, rows, fieldnames=fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = extract_comments(args.docx)
    atomic_write_json(args.out_dir / "comments.json", rows)
    write_csv(args.out_dir / "comments.csv", rows)
    print(json.dumps({"docx": str(args.docx), "comments": len(rows), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
