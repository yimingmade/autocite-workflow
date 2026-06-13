# Autocite Reference Workflow

## 1. Summary

- Process all comments in the target `.docx`, regardless of author, unless the user explicitly narrows scope.
- Create a fresh real EndNote CWYW-accessible library for each manuscript.
- Use the suffix `autocite-cwyw` for the `.enl` and `.Data` names.
- Insert only high or moderate confidence EndNote temporary citations using `{Author, Year #RecordNumber}`.
- Low-confidence references are reported only and are not inserted.

## 2. Inputs

- Manuscript `.docx`.
- Optional local `papers/` folder containing source PDFs.
- Optional existing EndNote template library if the run requires direct SQLite writeout.
- Optional user-supplied aliases or corrections for comments.

Before the first run on a machine, run:

```bash
python3 scripts/ensure_dependencies.py
```

This installs missing Python packages from `requirements.txt`, checks for `pdftotext`, and attempts to install Poppler when a supported package manager is available. If the dependency check cannot make `pdftotext` available, stop before PDF extraction and install Poppler manually.

To install the workflow as an agent skill, run one of:

```bash
bash scripts/install.sh --codex
bash scripts/install.sh --claude
bash scripts/install.sh --all
```

Validate the release package before install or upload:

```bash
python3 scripts/validate_package.py
```

If no output folder is supplied, create:

```text
<manuscript_dir>/autocite-runs/<docx-stem>.<YYYYMMDD-HHMMSS>/
```

Write all logs, extracted text, candidate maps, insertion logs, verification reports, and `reference-citation-audit.xlsx` inside that folder.

Maintain a run-state sidecar at:

```text
<run_dir>/status.json
```

Use `scripts/run_status.py` to write major states such as `checking_dependencies`, `extracting_comments`, `extracting_pdfs`, `preparing_endnote`, `resolving_candidates`, `awaiting_endnote`, `inserting_citations`, `verifying`, `writing_audit`, `completed`, `failed`, or `cancelled`. Mark blocked EndNote-template situations as `awaiting_endnote`, not `failed`, unless the run cannot continue.

For the early deterministic phase, `scripts/autocite_run.py` may stage the run folder and run dependency checks, comment extraction, optional PDF extraction, deterministic candidate template creation, and status updates:

```bash
python3 scripts/autocite_run.py \
  --docx "/path/to/manuscript.docx" \
  --papers-dir "/path/to/papers"
```

The launcher stops at `awaiting_endnote`. It does not create the EndNote library, insert citations, or edit the manuscript.

Write JSON, CSV, RIS, status, DOCX backup, EndNote template copy, and audit workbook outputs through `scripts/io_utils.py` atomic helpers or equivalent temporary-file replacement.

## 3. Comment Audit

Extract a complete comment audit with:

- comment ID,
- author,
- date,
- comment text,
- anchor text,
- paragraph context,
- citation relevance,
- any detected DOI, PMID, URL, title, paper code, or reference-number instruction.

Treat all comments as in scope. Preserve comments until the user explicitly requests deletion.

## 4. Paper-Code Rules

Build a paper-code index from local PDFs:

- Brace codes in filenames, for example `{JACC}` or `{Lazarus}`.
- Aliases inferred from filenames and user-provided examples, such as `Lazarus`, `AHA primordial`, `JACC`, `Shapiro JACC`, `Circulation`, `Lancet child`, `Lancet women`, `German`, `Nature`, `WHF`, and `Cardiac rehab`.
- Code-only comments resolve to the source paper.
- `[code] [N]` resolves to the Nth reference in that coded paper.
- `[code] + [N]` resolves to both the coded paper and the Nth reference in that coded paper.
- Multiple numbers, ranges, and comma-separated instructions must be expanded and audited.

Extract PDF reference lists using `pdftotext -raw`. Manually inspect multi-column, truncated, or ambiguous reference sections.

## 5. Corrupted Text Recovery

Before declaring a title unsearchable, actively parse and recover the citation. Extract, where present:

- author surnames and abbreviated author names,
- article title,
- journal title,
- DOI, PMID, URL,
- year,
- volume, issue, and page numbers.

Then recover likely title candidates from:

- clumped words without spaces,
- missing spaces between adjacent citations,
- missing spaces after punctuation,
- hyphen, en dash, em dash, or minus-sign substitutions,
- mojibake and corrupted characters,
- erroneous special-character substitutions,
- OCR ligature errors,
- line-break damage,
- pasted citation strings with missing delimiters,
- filename-style slugs with hyphens or underscores.

Use `scripts/build_search_queries.py` to normalise corrupted title text and generate search candidates. Use recovered candidates conservatively. Title, first author, year, DOI, PMID, journal, or volume/page cues must support the final match.

## 6. Search Cascade

For each reference candidate:

1. Search EndNote with the full title when clean enough.
2. If the first EndNote search fails, extract or recover DOI, PMID, author surname, article title, journal, year, volume, and page numbers from the citation string.
3. If PubMed MCP is configured, use it for PubMed lookup. If no PubMed MCP is configured, use direct public HTTP APIs instead of stopping:
   - Use NCBI E-utilities for PubMed search, PMID validation, and PubMed metadata retrieval.
   - Use Crossref REST API for DOI metadata when PubMed does not resolve the DOI or the article is outside PubMed.
   - Use OpenAlex as a fallback or enrichment layer for DOI, title, author, year, journal, and related scholarly metadata.
   - Use `scripts/reference_lookup.py` for this no-MCP lookup route and save JSON or RIS outputs in the run directory when useful.
4. If a DOI is present or recovered, first try PubMed lookup by DOI through PubMed MCP or NCBI E-utilities.
5. Confirm any PubMed result by paper title, first author, year, DOI, and PMID, then search EndNote by confirmed DOI.
6. If PubMed does not resolve the DOI, verify the DOI with Crossref, then use OpenAlex as fallback or enrichment.
7. If DOI search fails or no DOI is available, search PubMed by recovered title or title fragment plus author surname using PubMed MCP or NCBI E-utilities. Confirm title, first author, year, DOI, and PMID when available.
8. If PubMed is not applicable or no match is found, search Crossref by DOI or bibliographic query, then OpenAlex by DOI, title, author, year, or journal.
9. If EndNote still fails, run up to three punctuation-stripped EndNote searches:
   - distinctive title section plus author surname,
   - title without `;`, `:`, `,`, quotes, hyphens, en dashes, and em dashes plus author surname,
   - shorter title phrase plus journal or year.
10. If PubMed is not applicable, use DOI metadata, Crossref metadata, OpenAlex metadata, PDF citation text, or manual RIS.
11. If still unresolved or multiple plausible papers remain, mark low confidence.

## 7. Confidence Rules

- `high`: DOI/PMID or exact title/author/year match, no agent disagreement.
- `moderate`: strong title and context match, minor metadata uncertainty, no better competing candidate.
- `low`: disagreement between agents, missing source, uncertain `[code] [N]`, weak title match, ambiguous paper, or failed EndNote/PubMed confirmation.

Only high and moderate matches are inserted.

## 8. EndNote Handling

Infer the manuscript title from the DOCX core title property or the first substantive title paragraph.

Default path:

```text
<manuscript_dir>/autocite-<DDMMYY>/<inferred title> autocite-cwyw.enl
<manuscript_dir>/autocite-<DDMMYY>/<inferred title> autocite-cwyw.Data
<manuscript_dir>/autocite-<DDMMYY>/<inferred title> autocite-cwyw.Data/sdb/sdb.eni
```

If this library already exists, create a fresh timestamped writeout unless the user explicitly asks to reuse it.

Create and populate the new EndNote library before editing the manuscript, because record numbers are assigned only after import.

Use one of these creation routes:

1. **Template route, preferred for automation**: find or request a known-good empty EndNote `.enl` plus matching `.Data` folder. Run `prepare_endnote_writeout.py --template-enl <template.enl> --template-data <template.Data>` to copy it to the inferred manuscript-specific path. When only a prior complete library pair is available, run with `--clear-template-records` so the copied writeout is fresh before population.
2. **EndNote GUI route**: if no template is available, create a new blank EndNote library in the EndNote app at the inferred `.enl` path. Confirm that EndNote creates the matching `.Data/sdb/sdb.eni`, then close EndNote before SQLite verification.
3. **Blocked route**: if neither a template nor EndNote GUI access is available, stop before DOCX edits and ask the user to create/provide a blank library. Do not fabricate an `.enl` from scratch.

Import references by one of these routes:

1. PubMed result with PMID from PubMed MCP or NCBI E-utilities: export/import NBIB when available, or write RIS with PMID in `AN`.
2. DOI-confirmed article from PubMed, Crossref, or OpenAlex: write RIS with DOI in `DO`.
3. Local PDF with metadata: use EndNote PDF import or write manual RIS from verified title/author/year/DOI.
4. Manual citation text or HTTP API metadata from `scripts/reference_lookup.py`: write manual RIS only when title, first author, and year are verified.
5. Direct SQLite/template writeout: when using a copied-and-cleared complete library pair, write verified resolved records into both the fresh `.enl` and `.Data/sdb/sdb.eni` using `scripts/populate_endnote_sqlite.py`, then read back the assigned record numbers.

After import, close EndNote or ensure the library is not locked, then run `endnote_record_map.py` against the `.enl` and `.Data/sdb/sdb.eni`.

After import, read back assigned record numbers from the final library. Deduplicate by DOI, PMID, normalised title, first author, and year before insertion.

Treat the writeout as valid only if:

- `.enl` exists,
- `.Data` exists,
- `.Data/sdb/sdb.eni` exists,
- active non-trash record counts match between `.enl` and `sdb.eni` when both are readable,
- every inserted `#RecordNumber` exists in the final library.

## 9. Candidate Mapping Schema

Create exactly these candidate files before reconciliation:

- `candidate_map.deterministic.json`: produced by `generate_candidate_template.py` from `comments.json`.
- `candidate_map.agent1.json`: first independent read-only agent pass.
- `candidate_map.agent2.json`: second independent read-only agent pass.
- `candidate_map.agent3.json`: third independent read-only agent pass.

If subagents are unavailable, perform three separate sequential passes in the main thread and save them under the same filenames, explicitly avoiding reuse of prior pass conclusions except shared source artefacts.

Every deterministic mapper and read-only agent must output rows with these fields:

- `comment_id`: Word comment ID as an integer or integer string.
- `author`, `date`, `comment_text`, `anchor_text`, `paragraph_text`: copied from the comment audit when available.
- `candidate_references`: human-readable citation(s) or title(s).
- `resolved_references`: final intended reference title(s), separated by `;` for multiple references.
- `confidence`: exactly `high`, `moderate`, or `low`.
- `source_method`: one of `explicit_title`, `full_citation`, `doi`, `pmid`, `url`, `paper_code`, `paper_code_reference_number`, `paper_code_plus_reference_number`, `pubmed_search`, `doi_search`, `ncbi_eutilities`, `crossref_lookup`, `openalex_lookup`, `corrupted_text_recovery`, `endnote_punctuation_permutation`, `manual_ris`, or `agent_inference`.
- `record_numbers`: EndNote Record Number(s), separated by `;`, blank until EndNote import and readback.
- `insertion_text`: final EndNote temporary citation, for example `{Smith, 2020 #123; Jones, 2021 #456}`, blank for low confidence.
- `doi`, `pmid`, `title`, `first_author`, `year`, `journal`: metadata used for verification when available.
- `evidence`: short note explaining why the match is accepted or excluded.
- `agent_agreement_status`: `agreement`, `disagreement`, `single_source`, or `not_checked`.

`reconcile_reference_candidates.py` treats disagreement, missing identity, or any low-confidence vote as low confidence. Before insertion, every resolved row must have `confidence` high/moderate, valid `record_numbers`, and valid `insertion_text`.

Use this agent prompt template:

```text
Read-only autocite candidate mapping pass <N>. Do not edit files.
Inputs:
- comment audit: <run_dir>/comments.json
- paper index: <run_dir>/paper_index.json
- PDF reference lists: <run_dir>/pdf_reference_lists.json
- EndNote record map, if available: <run_dir>/endnote_record_number_map.json
- workflow rules: <skill_dir>/references/reference-add-workflow.md

For every comment row, decide whether it references a scientific paper. Resolve explicit titles, full citations, DOI, PMID, URL, paper codes, [code] [N], and [code] + [N]. Extract likely author surnames, article title, journal, DOI/PMID, year, volume, and pages. Recover corrupted, clumped, punctuation-damaged, or dash-damaged titles before searching. If the first EndNote search fails, use DOI/PubMed confirmation and up to three punctuation-stripped EndNote title permutations with author surname before marking unresolved. Use PubMed MCP when configured; if no PubMed MCP is configured, use NCBI E-utilities for PubMed/PMID verification, Crossref REST API for DOI metadata, and OpenAlex as a fallback or enrichment layer. Use high/moderate/low confidence rules. Return a JSON list using the required candidate mapping schema only. Leave insertion_text blank unless record_numbers are confirmed from the EndNote record map. Low-confidence rows must explain the reason in evidence.
```

Expected counts:

- Each candidate file should contain one row per Word comment unless the user explicitly narrows scope.
- Reconciliation output should split those rows into `resolved_comments.json` and `excluded_comments.json`.
- No resolved row may have blank `record_numbers` or blank `insertion_text`.

## 10. DOCX Insertion

- Create a timestamped backup before editing.
- Insert citations immediately after each comment anchor range in the main text.
- Use direct untracked text insertion so EndNote CWYW can parse temporary citations.
- Use `{Smith, 2020 #123}` for one reference.
- Use `{Smith, 2020 #123; Jones, 2021 #456}` for multiple references.
- Preserve comments and document structure unless the user separately asks to delete addressed comments.

## 11. Outputs

Produce one main workbook named `reference-citation-audit.xlsx` with exactly two sheets:

- `Excluded Comments`: unresolved and low-confidence exclusions, using the existing exclusion structure.
- `Resolved Comments`: comments, anchor text, paragraph context, resolved reference metadata, confidence, inserted citation, EndNote record number, source method, and agent agreement status.

Apply confidence formatting:

- high: blue,
- moderate: yellow,
- low: red.

Also keep JSON/CSV logs for reproducibility:

- raw comments,
- paper index,
- PDF reference lists,
- candidate references,
- reconciled mapping,
- EndNote record map,
- insertion log,
- syntax verification,
- subagent discrepancy report.

## 12. Verification

Before completion:

- Run DOCX ZIP/XML structural checks.
- Confirm visible text changes are only intended citation insertions.
- Confirm each inserted temporary citation is syntactically valid.
- Confirm every record number exists in `.enl` and `sdb.eni`.
- Confirm author, year, and title match the intended record.
- Confirm the workbook has exactly two sheets and confidence formatting.
- Render to PDF if LibreOffice is available.
- Use independent read-only subagents for high-stakes checks when possible.

Do not run EndNote CWYW formatting until all inserted temporary citations pass syntax and library-record checks.
