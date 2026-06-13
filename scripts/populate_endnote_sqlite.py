#!/usr/bin/env python3
"""Populate a fresh EndNote-shaped SQLite writeout from comment candidates."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from io_utils import atomic_write_csv, atomic_write_json


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).strip()


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def compact(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def first_author(author_field: object) -> str:
    first = clean(str(author_field or "").split("\r", 1)[0])
    if "," in first:
        return first.split(",", 1)[0].strip()
    return first.split(" ", 1)[0].strip()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    atomic_write_csv(path, rows, fieldnames=fields)


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.create_function("EN_MAKE_SORT_KEY", 3, lambda value, *_args: clean(value).lower())
    conn.create_collation("ENCI_Base", lambda left, right: (clean(left).lower() > clean(right).lower()) - (clean(left).lower() < clean(right).lower()))
    conn.create_collation("ENCIN_Base", lambda left, right: (clean(left).lower() > clean(right).lower()) - (clean(left).lower() < clean(right).lower()))
    return conn


def source_records(path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(refs)").fetchall()]
    rows = conn.execute("SELECT * FROM refs WHERE coalesce(trash_state, 0) = 0").fetchall()
    conn.close()
    records = []
    for values in rows:
        record = dict(zip(cols, values))
        record["old_record_number"] = record.get("id")
        record["_norm_title"] = norm(record.get("title"))
        record["_compact_title"] = compact(record.get("title"))
        records.append(record)
    return records


def record_identity(record: dict[str, Any]) -> str:
    for key in ("electronic_resource_number", "accession_number"):
        value = clean(record.get(key)).lower()
        if value:
            return f"{key}:{value}"
    title = norm(record.get("title"))
    year = clean(record.get("year"))
    author = first_author(record.get("author")).lower()
    return f"title:{title}|{year}|{author}"


def repair_record_year(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    year = clean(out.get("year"))
    if year.isdigit() and int(year) > 2026:
        title_years = [match for match in re.findall(r"(?:19|20)\d{2}", clean(out.get("title"))) if int(match) <= 2026]
        if title_years:
            out["year"] = title_years[0]
    return out


def content_words(title: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "into", "that", "this", "are", "was", "were", "has", "have", "via", "its"}
    return [word for word in norm(title).split() if len(word) >= 4 and word not in stop]


def exact_source_hits(text: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text_norm = norm(text)
    text_compact = compact(text)
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        title = clean(record.get("title"))
        if len(title) < 24:
            continue
        title_norm = record["_norm_title"]
        title_compact = record["_compact_title"]
        if len(content_words(title)) < 4:
            continue
        matched = title_norm in text_norm or (len(title_compact) >= 32 and title_compact in text_compact)
        if not matched:
            continue
        identity = record_identity(record)
        if identity in seen:
            continue
        seen.add(identity)
        hits.append(record)
    return hits


def lookup_by_doi_or_pmid(text: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dois = {m.group(0).rstrip(").,;") for m in re.finditer(r"10\.\d{4,9}/[^\s)]+", text, flags=re.I)}
    pmids = {m.group(1) for m in re.finditer(r"PMID\s*:\s*(\d+)", text, flags=re.I)}
    hits = []
    seen: set[str] = set()
    for record in records:
        doi = clean(record.get("electronic_resource_number")).lower()
        pmid = clean(record.get("accession_number"))
        if (doi and doi.lower() in {d.lower() for d in dois}) or (pmid and pmid in pmids):
            identity = record_identity(record)
            if identity not in seen:
                seen.add(identity)
                hits.append(record)
    return hits


def find_source_for_reference_text(text: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    doi_pmid = lookup_by_doi_or_pmid(text, records)
    if doi_pmid:
        return doi_pmid[0]
    hits = exact_source_hits(text, records)
    if hits:
        return hits[0]
    return None


def parse_reference_text(text: str) -> dict[str, Any] | None:
    value = clean(text)
    years = re.findall(r"(?:19|20)\d{2}", value)
    year = years[-1] if years else ""
    if not year:
        return None
    first = value.split(".", 1)[0]
    author = first_author(first)
    title = ""
    parts = [clean(part) for part in re.split(r"\.\s+", value) if clean(part)]
    if len(parts) >= 2:
        title = parts[1]
    if not title and ":" in value:
        title = value.split(":", 1)[0]
    title = re.sub(r"\b(?:19|20)\d{2}\b.*$", "", title).strip(" .;,")
    if len(title) < 12:
        return None
    doi_match = re.search(r"10\.\d{4,9}/[^\s)]+", value, flags=re.I)
    pmid_match = re.search(r"PMID\s*:\s*(\d+)", value, flags=re.I)
    return {
        "author": author,
        "year": year,
        "title": title,
        "secondary_title": "",
        "electronic_resource_number": doi_match.group(0).rstrip(").,;") if doi_match else "",
        "accession_number": pmid_match.group(1) if pmid_match else "",
        "url": "",
        "source_kind": "parsed_reference_text",
    }


def numbers_after_keyword(text: str, keyword: str) -> list[int]:
    match = re.search(rf"\b{re.escape(keyword)}\b\s*([0-9,\s]+)", text, flags=re.I)
    if not match:
        return []
    return [int(n) for n in re.findall(r"\d+", match.group(1))]


def plus_numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\+\s*(\d+)", text)]


def pdf_reference(pdf_refs: dict[str, Any], key: str, number: int) -> str:
    for row in pdf_refs.get(key, {}).get("references", []):
        if int(row.get("number", -1)) == number:
            return clean(row.get("text"))
    return ""


def skeleton_record(record: dict[str, Any]) -> dict[str, Any]:
    out = repair_record_year(record)
    out.pop("old_record_number", None)
    for key in list(out):
        if key.startswith("_"):
            out.pop(key, None)
    return out


def resolve_comment(comment: dict[str, Any], records: list[dict[str, Any]], pdf_refs: dict[str, Any], author_filter: str) -> tuple[list[dict[str, Any]], str, str]:
    if clean(comment.get("author")) != author_filter:
        return [], "low", f"Excluded by author filter: {clean(comment.get('author'))}"

    text = clean(comment.get("comment_text"))
    lowered = text.lower()
    if not text or "target journal" in lowered or "help renumber" in lowered or "sex and race disparities" in lowered:
        return [], "low", "Editorial or non-reference comment"

    resolved: list[dict[str, Any]] = []
    evidence: list[str] = []

    for record in lookup_by_doi_or_pmid(text, records):
        resolved.append(record)
        evidence.append(f"Matched source EndNote metadata by DOI/PMID old #{record.get('old_record_number')}")

    for number in numbers_after_keyword(text, "nature"):
        ref_text = pdf_reference(pdf_refs, "Nature_70068_2_art_file_625276_sv5stb", number)
        if not ref_text:
            evidence.append(f"Nature reference {number} not found")
            continue
        source = find_source_for_reference_text(ref_text, records)
        if source:
            resolved.append(source)
            evidence.append(f"Matched Nature reference {number} to old #{source.get('old_record_number')}")
        else:
            parsed = parse_reference_text(ref_text)
            if parsed:
                parsed["evidence"] = f"Parsed Nature reference {number}"
                resolved.append(parsed)
                evidence.append(f"Parsed Nature reference {number}")

    lipid_title = "the effect of lipid-lowering treatment on indices of masld in familial"
    if lipid_title in lowered:
        source_paper = find_source_for_reference_text(text, records)
        if source_paper:
            resolved.append(source_paper)
            evidence.append(f"Matched local lipid-lowering source paper to old #{source_paper.get('old_record_number')}")
        for number in plus_numbers(text):
            ref_text = pdf_reference(pdf_refs, "Boutari_et_al_1", number)
            if not ref_text:
                evidence.append(f"Lipid-lowering paper reference {number} not found")
                continue
            source = find_source_for_reference_text(ref_text, records)
            if source:
                resolved.append(source)
                evidence.append(f"Matched lipid-lowering reference {number} to old #{source.get('old_record_number')}")
            else:
                parsed = parse_reference_text(ref_text)
                if parsed:
                    parsed["evidence"] = f"Parsed lipid-lowering reference {number}"
                    resolved.append(parsed)
                    evidence.append(f"Parsed lipid-lowering reference {number}")

    if "reference our gbd cvd paper 2025-2050" in lowered:
        for record in records:
            if int(record.get("old_record_number") or 0) == 373:
                resolved.append(record)
                evidence.append("Matched explicit GBD CVD 2025-2050 instruction to old #373")

    for record in exact_source_hits(text, records):
        resolved.append(record)
        evidence.append(f"Exact title match to old #{record.get('old_record_number')}")

    if not resolved and re.search(r"(?:19|20)\d{2}|10\.\d{4,9}/|PMID\s*:", text, flags=re.I):
        evidence.append("Requires corrupted-text recovery plus EndNote/PubMed search cascade before insertion")

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in resolved:
        identity = record_identity(record)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(record)

    if not deduped:
        return [], "low", "; ".join(evidence) or "No reliable reference identity resolved"

    confidence = "high" if all(record.get("old_record_number") for record in deduped) else "moderate"
    return deduped, confidence, "; ".join(evidence)


def insert_records(db_path: Path, records: list[dict[str, Any]]) -> None:
    conn = connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(refs)").fetchall()]
        writable_cols = [col for col in cols if col != "id"]
        conn.execute("DELETE FROM file_res")
        conn.execute("DELETE FROM refs")
        conn.execute("DELETE FROM refs_ord")
        conn.execute("DELETE FROM ret_watch")
        conn.execute("DELETE FROM tag_members")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'refs'")
        now = int(time.time())
        for index, record in enumerate(records, start=1):
            row = skeleton_record(record)
            row["id"] = index
            row["trash_state"] = 0
            row.setdefault("reference_type", 0)
            row.setdefault("added_to_library", now)
            row.setdefault("record_last_updated", now)
            values = [row.get(col, "") for col in writable_cols]
            placeholders = ",".join("?" for _ in writable_cols)
            conn.execute(f"INSERT INTO refs (id,{','.join(writable_cols)}) VALUES (?,{placeholders})", [index, *values])
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'refs'", (len(records),))
        if conn.total_changes and not conn.execute("SELECT 1 FROM sqlite_sequence WHERE name = 'refs'").fetchone():
            conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES ('refs', ?)", (len(records),))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--pdf-reference-lists", required=True, type=Path)
    parser.add_argument("--source-sdb", required=True, type=Path)
    parser.add_argument("--target-enl", required=True, type=Path)
    parser.add_argument("--target-sdb", required=True, type=Path)
    parser.add_argument("--author-filter", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    comments = load_json(args.comments)
    pdf_refs = load_json(args.pdf_reference_lists)
    records = source_records(args.source_sdb)

    unique_records: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    resolved_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []

    for comment in comments:
        refs, confidence, evidence = resolve_comment(comment, records, pdf_refs, args.author_filter)
        if not refs:
            excluded_rows.append({**comment, "confidence": "low", "exclusion_reason": evidence})
            continue
        target_refs = []
        for ref in refs:
            ref = repair_record_year(ref)
            identity = record_identity(ref)
            if identity not in unique_records:
                unique_records[identity] = ref
            target_refs.append(identity)
        resolved_rows.append(
            {
                "comment_id": comment.get("comment_id"),
                "author": comment.get("author"),
                "date": comment.get("date"),
                "comment_text": comment.get("comment_text"),
                "anchor_text": comment.get("anchor_text"),
                "paragraph_text": comment.get("paragraph_text"),
                "candidate_references": comment.get("comment_text"),
                "resolved_references": "; ".join(clean(unique_records[identity].get("title")) for identity in target_refs),
                "confidence": confidence,
                "source_method": "direct_sqlite_source_or_pdf",
                "record_identity_keys": "; ".join(target_refs),
                "record_numbers": "",
                "insertion_text": "",
                "doi": "; ".join(clean(unique_records[identity].get("electronic_resource_number")) for identity in target_refs),
                "pmid": "; ".join(clean(unique_records[identity].get("accession_number")) for identity in target_refs),
                "title": "; ".join(clean(unique_records[identity].get("title")) for identity in target_refs),
                "first_author": "; ".join(first_author(unique_records[identity].get("author")) for identity in target_refs),
                "year": "; ".join(clean(unique_records[identity].get("year")) for identity in target_refs),
                "journal": "; ".join(clean(unique_records[identity].get("secondary_title")) for identity in target_refs),
                "evidence": evidence,
                "agent_agreement_status": "not_checked",
            }
        )

    record_list = list(unique_records.values())
    insert_records(args.target_enl, record_list)
    insert_records(args.target_sdb, record_list)

    identity_to_number = {identity: str(index) for index, identity in enumerate(unique_records.keys(), start=1)}
    for row in resolved_rows:
        identities = [item.strip() for item in row["record_identity_keys"].split(";") if item.strip()]
        numbers = [identity_to_number[identity] for identity in identities]
        titles = [unique_records[identity].get("title") for identity in identities]
        authors = [first_author(unique_records[identity].get("author")) for identity in identities]
        years = [clean(unique_records[identity].get("year")) for identity in identities]
        row["record_numbers"] = "; ".join(numbers)
        row["insertion_text"] = "{" + "; ".join(f"{author}, {year} #{number}" for author, year, number in zip(authors, years, numbers)) + "}"
        row["resolved_references"] = "; ".join(clean(title) for title in titles)

    record_map = []
    for index, record in enumerate(record_list, start=1):
        record_map.append(
            {
                "record_number": index,
                "old_record_number": record.get("old_record_number", ""),
                "first_author": first_author(record.get("author")),
                "year": clean(record.get("year")),
                "title": clean(record.get("title")),
                "journal": clean(record.get("secondary_title")),
                "doi": clean(record.get("electronic_resource_number")),
                "pmid": clean(record.get("accession_number")),
            }
        )

    write_json(args.out_dir / "resolved_comments.json", resolved_rows)
    write_json(args.out_dir / "excluded_comments.json", excluded_rows)
    write_json(args.out_dir / "endnote_record_number_map.json", record_map)
    write_csv(args.out_dir / "resolved_comments.csv", resolved_rows)
    write_csv(args.out_dir / "excluded_comments.csv", excluded_rows)
    write_csv(args.out_dir / "endnote_record_number_map.csv", record_map)
    print(json.dumps({"resolved_comments": len(resolved_rows), "excluded_comments": len(excluded_rows), "records_written": len(record_map)}, indent=2))


if __name__ == "__main__":
    main()
