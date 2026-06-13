#!/usr/bin/env python3
"""Fallback DOI, PMID, and title lookup without PubMed MCP."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from io_utils import atomic_write_text


NCBI_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
DEFAULT_HEADERS = {"User-Agent": "autocite-workflow/0.1"}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).strip()


def normalise_doi(value: str) -> str:
    doi = clean(value)
    doi = re.sub(r"(?i)^doi:\s*", "", doi)
    doi = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", doi)
    return doi.rstrip(".,;)").lower()


def extract_year(value: Any) -> str:
    match = re.search(r"(?:19|20)\d{2}", clean(value))
    return match.group(0) if match else ""


def first_author(value: str) -> str:
    name = clean(value)
    if not name:
        return ""
    if "," in name:
        return clean(name.split(",", 1)[0])
    return clean(name.split()[0])


def fetch_json(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(full_url, headers={**DEFAULT_HEADERS, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def pubmed_summary_to_record(item: dict[str, Any]) -> dict[str, str]:
    article_ids = item.get("articleids") or []
    ids = {
        clean(row.get("idtype")).lower(): clean(row.get("value"))
        for row in article_ids
        if isinstance(row, dict)
    }
    authors = [clean(author.get("name")) for author in item.get("authors", []) if isinstance(author, dict)]
    return {
        "source_method": "ncbi_eutilities",
        "pmid": clean(item.get("uid") or ids.get("pubmed")),
        "doi": normalise_doi(ids.get("doi", "")),
        "title": clean(item.get("title")),
        "first_author": first_author(authors[0]) if authors else "",
        "authors": "; ".join(author for author in authors if author),
        "year": extract_year(item.get("pubdate")),
        "journal": clean(item.get("fulljournalname") or item.get("source")),
        "evidence": "Resolved through NCBI E-utilities",
    }


def pubmed_search(query: str, fetch_json_func: Callable[..., dict[str, Any]] = fetch_json, max_results: int = 5) -> list[dict[str, str]]:
    search = fetch_json_func(
        NCBI_SEARCH_URL,
        params={"db": "pubmed", "retmode": "json", "retmax": max_results, "term": query},
    )
    pmids = [clean(value) for value in search.get("esearchresult", {}).get("idlist", []) if clean(value)]
    if not pmids:
        return []
    summary = fetch_json_func(
        NCBI_SUMMARY_URL,
        params={"db": "pubmed", "retmode": "json", "id": ",".join(pmids)},
    )
    result = summary.get("result", {})
    return [pubmed_summary_to_record(result[pmid]) for pmid in result.get("uids", pmids) if isinstance(result.get(pmid), dict)]


def lookup_pubmed_by_pmid(pmid: str, fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    records = pubmed_search(f"{clean(pmid)}[PMID]", fetch_json_func=fetch_json_func, max_results=1)
    return records[0] if records else None


def lookup_pubmed_by_doi(doi: str, fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    doi = normalise_doi(doi)
    records = pubmed_search(f'"{doi}"[AID]', fetch_json_func=fetch_json_func, max_results=1)
    return records[0] if records else None


def title_query(title: str, author: str = "", year: str = "") -> str:
    parts = [f'"{clean(title)}"[Title]']
    if author:
        parts.append(f'{clean(author)}[Author]')
    if year:
        parts.append(f'{clean(year)}[Date - Publication]')
    return " AND ".join(parts)


def crossref_record(message: dict[str, Any]) -> dict[str, str]:
    authors = []
    for author in message.get("author", []) or []:
        family = clean(author.get("family"))
        given = clean(author.get("given"))
        authors.append(clean(f"{family}, {given}") if given else family)
    published = (
        message.get("published-print")
        or message.get("published-online")
        or message.get("published")
        or {}
    )
    date_parts = published.get("date-parts") or []
    year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
    return {
        "source_method": "crossref_lookup",
        "pmid": "",
        "doi": normalise_doi(message.get("DOI", "")),
        "title": clean((message.get("title") or [""])[0]),
        "first_author": first_author(authors[0]) if authors else "",
        "authors": "; ".join(author for author in authors if author),
        "year": year,
        "journal": clean((message.get("container-title") or [""])[0]),
        "evidence": "Resolved through Crossref REST API",
    }


def lookup_crossref_by_doi(doi: str, fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    encoded = urllib.parse.quote(normalise_doi(doi), safe="")
    data = fetch_json_func(f"{CROSSREF_WORKS_URL}/{encoded}")
    message = data.get("message")
    return crossref_record(message) if isinstance(message, dict) else None


def lookup_crossref_by_query(title: str, author: str = "", year: str = "", fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    query = " ".join(part for part in [title, author, year] if clean(part))
    data = fetch_json_func(CROSSREF_WORKS_URL, params={"query.bibliographic": query, "rows": 1})
    items = data.get("message", {}).get("items", [])
    return crossref_record(items[0]) if items else None


def openalex_record(work: dict[str, Any]) -> dict[str, str]:
    doi = normalise_doi(work.get("doi", ""))
    ids = work.get("ids") or {}
    pmid = clean(ids.get("pmid"))
    pmid_match = re.search(r"(\d+)", pmid)
    source = ((work.get("primary_location") or {}).get("source") or {})
    authors = [
        clean(((authorship.get("author") or {}).get("display_name")))
        for authorship in work.get("authorships", []) or []
        if isinstance(authorship, dict)
    ]
    return {
        "source_method": "openalex_lookup",
        "pmid": pmid_match.group(1) if pmid_match else "",
        "doi": doi,
        "title": clean(work.get("title")),
        "first_author": first_author(authors[0]) if authors else "",
        "authors": "; ".join(author for author in authors if author),
        "year": str(work.get("publication_year") or ""),
        "journal": clean(source.get("display_name")),
        "evidence": "Resolved through OpenAlex fallback",
    }


def lookup_openalex_by_doi(doi: str, fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    data = fetch_json_func(OPENALEX_WORKS_URL, params={"filter": f"doi:https://doi.org/{normalise_doi(doi)}", "per-page": 1})
    results = data.get("results", [])
    return openalex_record(results[0]) if results else None


def lookup_openalex_by_query(title: str, author: str = "", year: str = "", fetch_json_func: Callable[..., dict[str, Any]] = fetch_json) -> dict[str, str] | None:
    query = " ".join(part for part in [title, author, year] if clean(part))
    data = fetch_json_func(OPENALEX_WORKS_URL, params={"search": query, "per-page": 1})
    results = data.get("results", [])
    return openalex_record(results[0]) if results else None


def try_lookup(func, *args, **kwargs) -> dict[str, str] | None:
    try:
        return func(*args, **kwargs)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return None


def unresolved(reason: str) -> dict[str, str]:
    return {
        "source_method": "unresolved",
        "pmid": "",
        "doi": "",
        "title": "",
        "first_author": "",
        "authors": "",
        "year": "",
        "journal": "",
        "evidence": reason,
    }


def lookup_reference(
    doi: str = "",
    pmid: str = "",
    title: str = "",
    author: str = "",
    year: str = "",
    fetch_json: Callable[..., dict[str, Any]] = fetch_json,
) -> dict[str, str]:
    if pmid:
        record = try_lookup(lookup_pubmed_by_pmid, pmid, fetch_json)
        if record:
            return record

    if doi:
        record = try_lookup(lookup_pubmed_by_doi, doi, fetch_json)
        if record:
            return record
        record = try_lookup(lookup_crossref_by_doi, doi, fetch_json)
        if record:
            return record
        record = try_lookup(lookup_openalex_by_doi, doi, fetch_json)
        if record:
            return record

    if title:
        record = try_lookup(pubmed_search, title_query(title, author, year), fetch_json, 1)
        if isinstance(record, list) and record:
            return record[0]
        record = try_lookup(lookup_crossref_by_query, title, author, year, fetch_json)
        if record:
            return record
        record = try_lookup(lookup_openalex_by_query, title, author, year, fetch_json)
        if record:
            return record

    return unresolved("No matching reference found through NCBI E-utilities, Crossref, or OpenAlex")


def ris(record: dict[str, str]) -> str:
    lines = ["TY  - JOUR"]
    if record.get("title"):
        lines.append(f"TI  - {record['title']}")
    for author in [clean(value) for value in record.get("authors", "").split(";") if clean(value)]:
        lines.append(f"AU  - {author}")
    if record.get("year"):
        lines.append(f"PY  - {record['year']}")
    if record.get("journal"):
        lines.append(f"JO  - {record['journal']}")
    if record.get("doi"):
        lines.append(f"DO  - {record['doi']}")
    if record.get("pmid"):
        lines.append(f"AN  - {record['pmid']}")
    lines.append("ER  -")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lookup reference metadata without PubMed MCP.")
    parser.add_argument("--doi", default="")
    parser.add_argument("--pmid", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--year", default="")
    parser.add_argument("--out-json")
    parser.add_argument("--out-ris")
    args = parser.parse_args()

    if not any([args.doi, args.pmid, args.title]):
        parser.error("Provide at least one of --doi, --pmid, or --title")

    record = lookup_reference(
        doi=args.doi,
        pmid=args.pmid,
        title=args.title,
        author=args.author,
        year=args.year,
    )
    payload = json.dumps(record, indent=2, ensure_ascii=False)
    if args.out_json:
        atomic_write_text(Path(args.out_json), payload + "\n")
    if args.out_ris:
        atomic_write_text(Path(args.out_ris), ris(record))
    print(payload)
    if record["source_method"] == "unresolved":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
