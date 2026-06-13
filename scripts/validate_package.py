#!/usr/bin/env python3
"""Validate the Autocite workflow package before install or release."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "autocite"

REQUIRED_FILES = (
    "README.md",
    "SKILL.md",
    "requirements.txt",
    "agents/openai.yaml",
    "references/reference-add-workflow.md",
    "scripts/autocite_run.py",
    "scripts/build_search_queries.py",
    "scripts/create_audit_workbook.py",
    "scripts/docx_comment_audit.py",
    "scripts/endnote_record_map.py",
    "scripts/ensure_dependencies.py",
    "scripts/extract_pdf_references.py",
    "scripts/generate_candidate_template.py",
    "scripts/install.sh",
    "scripts/install_claude_skill.py",
    "scripts/install_codex_skill.py",
    "scripts/insert_temp_citations.py",
    "scripts/io_utils.py",
    "scripts/populate_endnote_sqlite.py",
    "scripts/prepare_endnote_writeout.py",
    "scripts/reconcile_reference_candidates.py",
    "scripts/reference_lookup.py",
    "scripts/run_status.py",
    "scripts/validate_package.py",
    "scripts/verify_citation_syntax.py",
    "scripts/write_import_ris.py",
)

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".txt", ".sh", ".toml"}
IGNORED_NAMES = {".git", ".DS_Store", "__pycache__", "tests"}
LOCAL_PATH_PATTERNS = (
    (
        "local absolute path",
        re.compile(
            "("
            + "|".join(
                [
                    "/" + "Users/",
                    "/" + "home/",
                    "/" + "Volumes/",
                    "/" + "Applications/",
                    r"[A-Za-z]:\\\\" + "Users" + r"\\\\",
                ]
            )
            + ")"
        ),
    ),
    ("second-brain path", re.compile("YM_" + "SECOND_BRAIN")),
)


def iter_package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def read_frontmatter(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter bounded by ---")
    return match.group(1)


def validate_frontmatter(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        frontmatter = read_frontmatter(root / "SKILL.md")
    except Exception as exc:
        return [str(exc)]

    name_match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", frontmatter, re.MULTILINE)
    if not name_match:
        errors.append("SKILL.md frontmatter must include a lowercase hyphen-case name")
    elif name_match.group(1) != SKILL_NAME:
        errors.append(f"SKILL.md name must be {SKILL_NAME!r}")

    if not re.search(r"^description:\s*(>|[^\n]+)", frontmatter, re.MULTILINE):
        errors.append("SKILL.md frontmatter must include description")

    return errors


def validate_required_files(root: Path) -> list[str]:
    return [
        f"missing required file: {rel}"
        for rel in REQUIRED_FILES
        if not (root / rel).is_file()
    ]


def validate_no_generated_artifacts(root: Path) -> list[str]:
    errors = []
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if "tests" in rel_parts or "__pycache__" in rel_parts:
            continue
        if path.suffix == ".pyc":
            errors.append(f"generated artifact present: {path.relative_to(root).as_posix()}")
    return errors


def validate_no_local_paths(root: Path) -> list[str]:
    errors: list[str] = []
    for path in iter_package_files(root):
        if path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(text):
                errors.append(f"{rel} contains {label}")
    return errors


def validate_package(root: Path = REPO_ROOT) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    if not root.is_dir():
        errors.append(f"package root not found: {root}")
        return {"ok": False, "root": str(root), "required_files": list(REQUIRED_FILES), "errors": errors}

    errors.extend(validate_required_files(root))
    errors.extend(validate_frontmatter(root))
    errors.extend(validate_no_generated_artifacts(root))
    errors.extend(validate_no_local_paths(root))

    return {
        "ok": not errors,
        "root": str(root),
        "required_files": list(REQUIRED_FILES),
        "file_count": len(iter_package_files(root)),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Autocite workflow package.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = validate_package(args.root)
    if args.json:
        print(json.dumps(summary, indent=2))
    elif summary["ok"]:
        print(f"[OK] Autocite package is valid: {summary['root']}")
    else:
        print(f"[ERROR] Autocite package validation failed: {summary['root']}", file=sys.stderr)
        for error in summary["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
