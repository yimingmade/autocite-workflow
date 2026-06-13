#!/usr/bin/env python3
"""Build robust title and author search permutations for failed EndNote searches."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata

MOJIBAKE = {
    "â€“": "-",
    "â€”": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€\u009d": '"',
    "Ã©": "e",
    "Ã¼": "u",
    "Ã¶": "o",
    "Ã¡": "a",
    "Ã±": "n",
}

VOCAB = {
    "a",
    "accuracy",
    "advanced",
    "and",
    "angiotensin",
    "antiobesity",
    "antagonists",
    "associated",
    "bariatric",
    "basic",
    "basics",
    "blood",
    "cardiologists",
    "cardiometabolic",
    "cardiovascular",
    "chronic",
    "cirrhosis",
    "diagnosis",
    "disease",
    "effects",
    "effect",
    "fibrosis",
    "for",
    "global",
    "health",
    "hepatic",
    "hypertension",
    "identifying",
    "in",
    "incident",
    "increased",
    "independent",
    "kidney",
    "liver",
    "management",
    "metabolic",
    "mineralocorticoid",
    "nonalcoholic",
    "of",
    "on",
    "pharmacological",
    "phentermine",
    "pilot",
    "presence",
    "pressure",
    "recommendations",
    "receptor",
    "risk",
    "screening",
    "severity",
    "spectrum",
    "steatosis",
    "steatotic",
    "study",
    "surgery",
    "therapy",
    "the",
    "with",
}
ACRONYMS = {"nafld": "NAFLD", "masld": "MASLD", "mash": "MASH", "nash": "NASH", "cvd": "CVD", "ckd": "CKD", "t2d": "T2D"}


def split_known_clump_token(token: str) -> str:
    if len(token) < 7 or not token.isalpha():
        return token
    lower = token.lower()
    words = set(VOCAB) | set(ACRONYMS)
    best: list[str] | None = None

    def solve(pos: int) -> list[str] | None:
        if pos == len(lower):
            return []
        matches: list[list[str]] = []
        for end in range(len(lower), pos, -1):
            piece = lower[pos:end]
            if piece not in words:
                continue
            tail = solve(end)
            if tail is not None:
                matches.append([piece, *tail])
        if not matches:
            return None
        return min(matches, key=len)

    best = solve(0)
    if not best or len(best) < 2:
        return token
    rendered = [ACRONYMS.get(word, word) for word in best]
    if token[:1].isupper() and rendered[0] not in ACRONYMS.values():
        rendered[0] = rendered[0].capitalize()
    return " ".join(rendered)


def split_known_clumps(value: str) -> str:
    return re.sub(r"\b[A-Za-z]{7,}\b", lambda m: split_known_clump_token(m.group(0)), value)


def clean(value: str) -> str:
    for bad, good in MOJIBAKE.items():
        value = value.replace(bad, good)
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[_/]+", " ", value)
    value = re.sub(r"([A-Z]{2,})(?=[a-z])", r"\1 ", value)
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = re.sub(r"(?<=[.,;:])(?=[A-Za-z])", " ", value)
    value = re.sub(r"[-–—]+", " ", value)
    value = split_known_clumps(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;:,")


def strip_punctuation(value: str) -> str:
    value = re.sub(r"[;:,\"'`’‘“”()\[\]{}<>]", " ", value)
    value = re.sub(r"[-–—]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def distinctive_phrase(title: str, max_words: int = 12) -> str:
    stop = {"the", "and", "of", "in", "for", "with", "a", "an", "to", "on", "by", "from"}
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title) if w.lower() not in stop]
    return " ".join(words[:max_words])


def queries(raw_title: str, author: str = "", journal_or_year: str = "") -> dict[str, object]:
    normalised = clean(raw_title)
    no_punct = strip_punctuation(normalised)
    author = clean(author)
    suffix = f" {author}" if author else ""
    candidates = [
        f"{normalised}{suffix}".strip(),
        f"{no_punct}{suffix}".strip(),
        f"{distinctive_phrase(no_punct)}{suffix}".strip(),
    ]
    if journal_or_year:
        candidates.append(f"{distinctive_phrase(no_punct, 8)} {clean(journal_or_year)}".strip())
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate.lower() not in {q.lower() for q in deduped}:
            deduped.append(candidate)
    return {
        "raw_title": raw_title,
        "normalised_title": normalised,
        "punctuation_stripped_title": no_punct,
        "author": author,
        "queries": deduped[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--journal-or-year", default="")
    args = parser.parse_args()
    print(json.dumps(queries(args.title, args.author, args.journal_or_year), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
