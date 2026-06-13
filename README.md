# Autocite Workflow

Autocite converts Word manuscript comments into verified EndNote CWYW temporary citations.

It extracts `.docx` comments, resolves reference instructions, prepares or verifies an EndNote library, inserts temporary citations such as `{Smith, 2024 #123}`, and writes a two-sheet audit workbook.

## Contents

1. Requirements
2. Installation
3. First Run Check
4. One-Command Early Run
5. Basic Usage
6. PubMed And DOI Lookup
7. EndNote Requirement
8. Run Status
9. Output Safety
10. Outputs

## Requirements

Required:

1. Python 3.10 or later.
2. Python packages in `requirements.txt`.
3. `pdftotext`, provided by Poppler, for extracting reference lists from PDFs.
4. EndNote desktop, or a valid EndNote `.enl` plus matching `.Data` template.

Optional:

1. PubMed MCP, when running inside an agent environment that supports MCP tools.
2. LibreOffice, for optional DOCX to PDF verification.

## Installation

Clone or download this repository, then run:

```bash
cd autocite-workflow
python3 scripts/ensure_dependencies.py
```

The preflight script installs missing Python packages from `requirements.txt`. It also checks for `pdftotext`; when a supported package manager is available, it attempts to install Poppler automatically.

To install Autocite as an agent skill:

```bash
bash scripts/install.sh --codex
bash scripts/install.sh --claude
bash scripts/install.sh --all
```

Useful installer checks:

```bash
python3 scripts/validate_package.py
python3 scripts/install_codex_skill.py --dry-run
python3 scripts/install_claude_skill.py --dry-run
```

The installers validate the package, then copy the workflow into the target skills folder:

1. Codex: `$CODEX_HOME/skills/autocite` or `~/.codex/skills/autocite`.
2. Claude Code: `$CLAUDE_HOME/skills/autocite` or `~/.claude/skills/autocite`.

Generated files, tests, `.git`, `.DS_Store`, `__pycache__`, and `.pyc` files are excluded from installed skill copies.

Manual alternatives:

```bash
python3 -m pip install -r requirements.txt
```

macOS:

```bash
brew install poppler
```

Debian or Ubuntu:

```bash
sudo apt-get install -y poppler-utils
```

## First Run Check

Before the first workflow run on a machine:

```bash
python3 scripts/ensure_dependencies.py
```

To check without installing:

```bash
python3 scripts/ensure_dependencies.py --check-only
```

If `pdftotext` cannot be installed automatically, install Poppler with your operating system package manager and rerun the check.

## One-Command Early Run

For the early deterministic phase, use:

```bash
python3 scripts/autocite_run.py \
  --docx "/path/to/manuscript.docx" \
  --papers-dir "/path/to/papers"
```

If no output folder is supplied, it creates:

```text
<manuscript_dir>/autocite-runs/<docx-stem>.<YYYYMMDD-HHMMSS>/
```

This launcher runs:

1. Dependency check with `scripts/ensure_dependencies.py`.
2. Word comment extraction with `scripts/docx_comment_audit.py`.
3. PDF reference extraction with `scripts/extract_pdf_references.py`, when `--papers-dir` is supplied.
4. Deterministic candidate template creation with `scripts/generate_candidate_template.py`.
5. Status updates through `scripts/run_status.py`.

It stops at `awaiting_endnote`. It does not create the EndNote library, insert citations, or edit the manuscript.

Useful variants:

```bash
python3 scripts/autocite_run.py \
  --docx "/path/to/manuscript.docx" \
  --out-dir run

python3 scripts/autocite_run.py \
  --docx "/path/to/manuscript.docx" \
  --papers-dir "/path/to/papers" \
  --skip-dependency-check
```

## Basic Usage

Create a run folder, then extract comments:

```bash
mkdir -p run
python3 scripts/docx_comment_audit.py \
  --docx "/path/to/manuscript.docx" \
  --out-dir run
```

If you have a folder of source PDFs:

```bash
python3 scripts/extract_pdf_references.py \
  --papers-dir "/path/to/papers" \
  --out-dir run
```

Create the deterministic candidate template:

```bash
python3 scripts/generate_candidate_template.py \
  --comments run/comments.json \
  --out-dir run
```

Then follow `references/reference-add-workflow.md` for EndNote library preparation, candidate reconciliation, insertion, verification, and audit workbook creation.

## PubMed And DOI Lookup

If PubMed MCP is configured in your agent environment, the workflow may use it for PubMed lookup.

If PubMed MCP is not available, use the built-in fallback:

1. NCBI E-utilities for PubMed search, PMID validation, and PubMed metadata.
2. Crossref REST API for DOI metadata when PubMed does not resolve the DOI.
3. OpenAlex as a fallback or enrichment layer.

Examples:

```bash
python3 scripts/reference_lookup.py --pmid 12345678
python3 scripts/reference_lookup.py --doi "10.1000/example"
python3 scripts/reference_lookup.py --title "Example cardiovascular trial" --author Smith --year 2024
```

Write lookup results to JSON or RIS:

```bash
python3 scripts/reference_lookup.py \
  --doi "10.1000/example" \
  --out-json run/reference_lookup.json \
  --out-ris run/reference_lookup.ris
```

## EndNote Requirement

This workflow does not use an EndNote MCP.

It requires either:

1. EndNote desktop to create or open a real `.enl` library with its matching `.Data` folder.
2. A valid existing EndNote template pair:
   - `.enl`
   - `.Data`

The final record number must come from the actual EndNote library. Do not insert a citation unless the `#RecordNumber` exists in the final `.enl` and `.Data/sdb/sdb.eni`.

## Run Status

Each run may maintain a machine-readable status sidecar:

```text
<run_dir>/status.json
```

Write or read it with:

```bash
python3 scripts/run_status.py --run-dir run --state extracting_comments --step docx_comment_audit
python3 scripts/run_status.py --run-dir run --read
```

Valid states include:

```text
created
checking_dependencies
extracting_comments
extracting_pdfs
preparing_endnote
resolving_candidates
awaiting_endnote
inserting_citations
verifying
writing_audit
completed
failed
cancelled
```

This makes interrupted runs easier to inspect, resume, or debug.

## Output Safety

Workflow outputs are written through temporary files before replacing the final path. This reduces the risk of half-written files when a run is interrupted.

The shared helper is `scripts/io_utils.py`. It is used for JSON, CSV, RIS, status, copied DOCX backups, EndNote template copies, and the audit workbook output.

## Outputs

The main user-facing output is:

```text
reference-citation-audit.xlsx
```

It must contain exactly two sheets:

1. `Excluded Comments`
2. `Resolved Comments`

Low-confidence or unresolved comments are reported only. Only high or moderate confidence citations are inserted.
