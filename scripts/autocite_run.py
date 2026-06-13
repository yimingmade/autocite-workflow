#!/usr/bin/env python3
"""Stage and run the deterministic early Autocite workflow steps."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import run_status
from io_utils import atomic_write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


CommandRunner = Callable[[list[object]], int]


def default_run_dir(docx: Path, timestamp: str | None = None) -> Path:
    stamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    return docx.expanduser().absolute().parent / "autocite-runs" / f"{docx.stem}.{stamp}"


def subprocess_runner(command: list[object]) -> int:
    return subprocess.run([str(part) for part in command], check=False).returncode


def run_checked(
    command: list[object],
    *,
    runner: CommandRunner,
    run_dir: Path,
    failure_step: str,
) -> None:
    code = runner(command)
    if code != 0:
        reason = f"command failed with exit code {code}: {' '.join(str(part) for part in command)}"
        run_status.write_status(run_dir, "failed", step=failure_step, reason=reason)
        raise RuntimeError(reason)


def run_early_workflow(
    *,
    docx: Path,
    out_dir: Path | None = None,
    papers_dir: Path | None = None,
    check_dependencies: bool = True,
    runner: CommandRunner = subprocess_runner,
) -> dict[str, object]:
    docx = docx.expanduser().absolute()
    if not docx.exists():
        raise FileNotFoundError(f"manuscript DOCX not found: {docx}")

    run_dir = (out_dir or default_run_dir(docx)).expanduser().absolute()
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "docx": str(docx),
        "papers_dir": str(papers_dir.expanduser().absolute()) if papers_dir else "",
        "run_dir": str(run_dir),
    }
    atomic_write_json(run_dir / "autocite_run_manifest.json", manifest)

    if check_dependencies:
        run_status.write_status(run_dir, "checking_dependencies", step="ensure_dependencies")
        run_checked(
            [sys.executable, SCRIPTS / "ensure_dependencies.py"],
            runner=runner,
            run_dir=run_dir,
            failure_step="ensure_dependencies",
        )

    run_status.write_status(run_dir, "extracting_comments", step="docx_comment_audit")
    run_checked(
        [
            sys.executable,
            SCRIPTS / "docx_comment_audit.py",
            "--docx",
            docx,
            "--out-dir",
            run_dir,
        ],
        runner=runner,
        run_dir=run_dir,
        failure_step="docx_comment_audit",
    )

    if papers_dir:
        papers_dir = papers_dir.expanduser().absolute()
        if not papers_dir.is_dir():
            reason = f"papers directory not found: {papers_dir}"
            run_status.write_status(run_dir, "failed", step="extract_pdf_references", reason=reason)
            raise FileNotFoundError(reason)
        run_status.write_status(run_dir, "extracting_pdfs", step="extract_pdf_references")
        run_checked(
            [
                sys.executable,
                SCRIPTS / "extract_pdf_references.py",
                "--papers-dir",
                papers_dir,
                "--out-dir",
                run_dir,
            ],
            runner=runner,
            run_dir=run_dir,
            failure_step="extract_pdf_references",
        )

    run_status.write_status(run_dir, "resolving_candidates", step="generate_candidate_template")
    run_checked(
        [
            sys.executable,
            SCRIPTS / "generate_candidate_template.py",
            "--comments",
            run_dir / "comments.json",
            "--out-dir",
            run_dir,
        ],
        runner=runner,
        run_dir=run_dir,
        failure_step="generate_candidate_template",
    )

    summary = {
        **manifest,
        "next_step": "prepare_endnote",
        "next_step_note": "Prepare or provide a valid EndNote .enl/.Data pair before insertion.",
    }
    atomic_write_json(run_dir / "autocite_run_summary.json", summary)
    run_status.write_status(
        run_dir,
        "awaiting_endnote",
        step="prepare_endnote",
        reason="Early deterministic workflow completed; EndNote preparation is next.",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run early deterministic Autocite workflow steps.")
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--papers-dir", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--skip-dependency-check", action="store_true")
    args = parser.parse_args()

    try:
        summary = run_early_workflow(
            docx=args.docx,
            out_dir=args.out_dir,
            papers_dir=args.papers_dir,
            check_dependencies=not args.skip_dependency_check,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
