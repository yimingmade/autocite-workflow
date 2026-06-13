#!/usr/bin/env python3
"""Index local PDFs and extract likely numbered reference lists."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

from io_utils import atomic_write_csv, atomic_write_json, atomic_write_text


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_stem(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")[:140]


def run(args: list[str], timeout: int = 90) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return proc.stdout


def pdfinfo(path: Path) -> dict[str, str]:
    info = {"title": "", "pages": ""}
    for line in run(["pdfinfo", str(path)], timeout=20).splitlines():
        if line.startswith("Title:"):
            info["title"] = clean(line.split(":", 1)[1])
        elif line.startswith("Pages:"):
            info["pages"] = clean(line.split(":", 1)[1])
    return info


def pdftotext(path: Path, text_dir: Path) -> str:
    text_dir.mkdir(parents=True, exist_ok=True)
    out_path = text_dir / f"{safe_stem(path)}.raw.txt"
    if out_path.exists():
        return out_path.read_text(encoding="utf-8", errors="replace")
    text = run(["pdftotext", "-raw", str(path), "-"], timeout=180)
    atomic_write_text(out_path, text)
    return text


def bibliography_segment(text: str) -> str:
    markers = list(re.finditer(r"(?i)\b(references|bibliography)\b", text))
    if not markers:
        return text[-50000:]
    return text[markers[-1].start() :]


def parse_numbered_refs(text: str) -> list[dict[str, object]]:
    segment = bibliography_segment(text)
    styles = [
        r"(?m)^\s*(\d{1,3})\.\s+",
        r"(?m)^\s*\[(\d{1,3})\]\s+",
        r"(?m)^\s*(\d{1,3})\s+(?=[A-Z][A-Za-z'’-]+[, ])",
    ]
    best: list[tuple[int, int, int]] = []
    for pattern in styles:
        positions = [(int(m.group(1)), m.start(), m.end()) for m in re.finditer(pattern, segment)]
        if len(positions) > len(best):
            best = positions
    refs: list[dict[str, object]] = []
    for idx, (number, _start, end) in enumerate(best):
        next_start = best[idx + 1][1] if idx + 1 < len(best) else min(len(segment), end + 2200)
        body = clean(segment[end:next_start])
        if body:
            refs.append({"number": number, "text": body})
    return refs


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    atomic_write_csv(path, rows, fieldnames=fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--papers-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    text_dir = args.out_dir / "pdf_text"
    paper_rows: list[dict[str, object]] = []
    reference_lists: dict[str, object] = {}

    for path in sorted(args.papers_dir.rglob("*.pdf")):
        info = pdfinfo(path)
        text = pdftotext(path, text_dir)
        codes = re.findall(r"\{([^}]+)\}", path.name)
        aliases = sorted({*codes, clean(path.stem.replace("_", " ").replace("-", " "))})
        row = {
            "pdf_id": safe_stem(path),
            "filename": path.name,
            "path": str(path),
            "codes": "; ".join(codes),
            "aliases": "; ".join(a for a in aliases if a),
            "title_from_pdfinfo": info["title"],
            "pages": info["pages"],
            "text_chars": len(text),
        }
        paper_rows.append(row)
        reference_lists[row["pdf_id"]] = {"paper": row, "references": parse_numbered_refs(text)}

    atomic_write_json(args.out_dir / "paper_index.json", paper_rows)
    atomic_write_json(args.out_dir / "pdf_reference_lists.json", reference_lists)
    write_csv(args.out_dir / "paper_index.csv", paper_rows)
    print(json.dumps({"papers": len(paper_rows), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
