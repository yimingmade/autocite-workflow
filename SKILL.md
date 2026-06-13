---
name: autocite
description: Use when the user types /autocite or asks to convert Word manuscript comments into verified EndNote CWYW temporary citations. Handles .docx comment extraction, local PDF paper-code mapping, PubMed/DOI lookup, EndNote record-number verification, inline {Author, Year #RecordNumber} insertion, and two-sheet citation audit workbooks.
---

# Autocite

## Core Rule

When invoked by `/autocite`, read `references/reference-add-workflow.md` before acting. Treat the workflow as a fragile manuscript operation: verify paths, back up DOCX files before mutation, and never insert a citation unless the EndNote record number is confirmed from the final library.

## Required Workflow

1. Before the first run on a machine, run `scripts/ensure_dependencies.py` from the repository root. It checks and installs Python requirements from `requirements.txt`, then checks for `pdftotext` and attempts Poppler installation when supported. If installing as an agent skill, use `scripts/install.sh --codex`, `scripts/install.sh --claude`, or `scripts/install.sh --all`.
2. Resolve inputs: manuscript `.docx`, local `papers/` folder, and output folder. If no output folder is given, use `<manuscript_dir>/autocite-runs/<docx-stem>.<YYYYMMDD-HHMMSS>/`.
3. Create or update `<run_dir>/status.json` with `scripts/run_status.py` at each major phase so interrupted runs can be inspected and resumed.
4. For the early deterministic phase, prefer `scripts/autocite_run.py --docx <manuscript.docx> --papers-dir <papers_dir>` when the user wants a one-command start. It runs dependency checks, comment extraction, optional PDF extraction, deterministic candidate template creation, and status updates, then stops at `awaiting_endnote`.
5. Run `scripts/docx_comment_audit.py` to extract comment ID, author, date, comment text, anchor text, paragraph context, and citation signal.
6. Run `scripts/extract_pdf_references.py` when a `papers/` folder is available, then use paper codes, `{brace}` codes, aliases, `[code] [N]`, and `[code] + [N]` rules from the workflow reference.
7. Create a fresh EndNote writeout using `scripts/prepare_endnote_writeout.py`; the default folder is `<manuscript_dir>/autocite-<DDMMYY>/` and the default suffix is `autocite-cwyw`.
8. Populate the EndNote writeout before editing the manuscript. Use direct SQLite/template writeout only when a valid template `.enl` and `.Data` are available; otherwise create the blank library in EndNote at the inferred path, import PubMed NBIB/RIS/PDF/manual RIS bundles, then close EndNote before reading record numbers.
9. Build importable RIS bundles with `scripts/write_import_ris.py` when references are resolved outside EndNote.
   - For direct SQLite/template writeout, use `scripts/populate_endnote_sqlite.py` to write the resolved references into both the fresh `.enl` and `.Data/sdb/sdb.eni` before reading record numbers.
10. Read back record numbers with `scripts/endnote_record_map.py`.
11. Run `scripts/generate_candidate_template.py` to create `candidate_map.deterministic.json` and `.csv`.
12. Produce three independent read-only agent candidate files named `candidate_map.agent1.json`, `candidate_map.agent2.json`, and `candidate_map.agent3.json`, using the prompt and schema in `references/reference-add-workflow.md`.
13. Reconcile `candidate_map.deterministic.json` plus the three agent files with `scripts/reconcile_reference_candidates.py`. Any disagreement, unresolved source, or weak match is low confidence.
14. Insert only high or moderate confidence citations using `scripts/insert_temp_citations.py`.
15. Verify citation syntax and record numbers with `scripts/verify_citation_syntax.py`.
16. Produce the main audit workbook with `scripts/create_audit_workbook.py`.

## EndNote Invariants

- Infer the library stem from the manuscript title.
- Use `<manuscript_dir>/autocite-<DDMMYY>/<title> autocite-cwyw.enl` and `<manuscript_dir>/autocite-<DDMMYY>/<title> autocite-cwyw.Data`.
- If the inferred library already exists, create a timestamped fresh library unless the user explicitly requests reuse.
- Treat the writeout as valid only when `.enl`, `.Data`, and `.Data/sdb/sdb.eni` exist and show matching active record counts.
- Use the EndNote `Record Number` from the final library as `#RecordNumber`.
- Do not use older global Codex EndNote paths unless the user explicitly requests them.
- When a valid EndNote template or prior complete library pair is available, `prepare_endnote_writeout.py --clear-template-records` may create a fresh empty writeout automatically in the `autocite-<DDMMYY>` folder before population.
- If no valid template, prior complete library pair, or GUI-created blank library is available, stop before DOCX edits and ask the user to create/provide one.

## Search Fallbacks

If an EndNote search fails:

1. Parse the citation text into likely author surnames, abbreviated author names, article title, journal, DOI, PMID, year, volume, and page numbers.
2. If words are clumped, spacing is missing, dashes are corrupted, punctuation is substituted, or special characters look wrong, recover likely title candidates with `scripts/build_search_queries.py`.
3. Search EndNote with the clean full title when available.
4. If PubMed MCP is configured, use it for PubMed lookup. If no PubMed MCP is configured, do not block the workflow; use direct public HTTP APIs in this order:
   - NCBI E-utilities for PubMed search, PMID validation, and PMID metadata verification.
   - Crossref REST API for DOI metadata when PubMed does not resolve the DOI or the article is outside PubMed.
   - OpenAlex as a fallback or enrichment layer for DOI, title, author, year, journal, and related scholarly metadata.
   - Use `scripts/reference_lookup.py` to run this no-MCP lookup route and optionally write JSON or RIS metadata.
5. If a DOI is present or recovered, first try PubMed lookup by DOI through PubMed MCP or NCBI E-utilities, confirm paper title, first author, year, DOI, and PMID when available, then search EndNote by the confirmed DOI. If PubMed does not resolve it, verify DOI metadata with Crossref, then use OpenAlex as fallback or enrichment.
6. If DOI search fails or no DOI is available, search PubMed by recovered title or title fragment plus author surname using PubMed MCP or NCBI E-utilities, then confirm title, first author, year, DOI, and PMID when available. If PubMed is not applicable or no match is found, search Crossref, then OpenAlex.
7. If EndNote still fails, search up to three EndNote permutations:
   - distinctive title section plus author surname,
   - title stripped of `;`, `:`, `,`, quotes, hyphens, en dashes, and em dashes plus author surname,
   - shorter title phrase plus journal, year, or volume/page cue.
8. If still unresolved or ambiguous, keep the comment low confidence and exclude it from insertion.

## Output Contract

The main user-facing output is `reference-citation-audit.xlsx` with exactly two sheets:

- `Excluded Comments`: low-confidence or unresolved comments.
- `Resolved Comments`: comment audit, anchor text, paragraph context, resolved references, confidence, inserted citation, EndNote record number, source method, and agent agreement status.

Apply confidence colouring in the workbook: high blue, moderate yellow, low red. Keep JSON and CSV logs for recovery and debugging.

Write JSON, CSV, RIS, status, DOCX backup, EndNote template copy, and audit workbook outputs through `scripts/io_utils.py` atomic helpers or equivalent temporary-file replacement. Do not leave partially written artefacts as the final output path.

## Verification

Before reporting completion:

- Confirm DOCX visible text changed only by intended temporary citation insertions.
- Confirm every inserted temporary citation matches `{Author, Year #RecordNumber}` syntax.
- Confirm every `#RecordNumber` exists in the final `.enl` and `.Data/sdb/sdb.eni`.
- Confirm the audit workbook has exactly two sheets and confidence formatting.
- Render the DOCX to PDF when LibreOffice is available.
- Use subagents for independent read-only checks when the user requests agent verification or when the run is high stakes.

If deterministic tooling fails, troubleshoot agentically: inspect OOXML, SQLite tables, EndNote import state, PDF text extraction, and search logs. Do not silently skip failed comments.
