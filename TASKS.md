# Local Task Board

Status legend: `[ ]` pending, `[~]` in progress, `[x]` verified, `[!]` blocked.

## P0 - Understand and freeze the contract

- [x] Read the assignment and identify mandatory stages and deliverables.
- [x] Inspect the source PDF and confirm that it is image-based.
- [x] Inspect summary pages 5-7 and locate note 11.
- [x] Freeze the problem statement in the local project contract.
- [x] Define and version the final JSON result, JSON run-manifest, and JSONL event-log schemas.
- [x] Define configuration schema for source, page range, note numbers, models, and quality-gate thresholds/actions.
- [x] Define one-based PDF page, zero-based page index, and printed-page fields in the schema.
- [x] Define and implement zero/one/many relation cardinality with explicit ambiguity and abstention fields.
- [x] Include company, reporting periods, currency, and source provenance in document metadata.
- [x] Justify the hierarchical JSON result and append-only JSONL event-log formats in README Section 6.

Acceptance criteria:

- Every mandatory assignment requirement maps to code, output, validation, or README evidence.
- No target page or note number is embedded in business logic.

## P0 - Project foundation

- [x] Initialize Git when explicitly agreed.
- [x] Create Python package structure and dependency configuration.
- [x] Add a single documented CLI entry point.
- [x] Verify the installed `ykt-case` console entry point without `PYTHONPATH`; help, config smoke test, direct package import, dependency check, and 74 tests pass after the normal-wheel fix and current regression additions.
- [x] Separate local run commands and engineering error records from the final README.
- [x] Add logging, deterministic seed handling, and run metadata.
- [x] Add source/config checksums and a reproducible run manifest.
- [~] Add unit-test and lint commands; unit-test command is verified, lint command remains pending.

Acceptance criteria:

- A clean setup can run one smoke-test command.
- Machine-specific paths are absent from committed configuration.

## P0 - PDF rendering and OCR

- [x] Render configured PDF pages at a controlled DPI.
- [ ] Detect/correct page orientation and skew.
- [x] Implement OCR output with text, bounding boxes, and OCR confidence.
- [x] Preserve raw OCR artifacts for debugging.
- [x] Compare Tesseract PSM 3, 4, 6, and 11 on a fixed reviewed sample.
- [x] Define OCR quality gates and explicit continue-with-warning or stop behavior.
- [x] Record fallback trigger, failed semantic result, baseline fallback result, and resulting semantic-evidence quality loss.

Acceptance criteria:

- Summary pages and note pages produce word-level coordinates and confidence.
- Known values and headers on the inspected pages are recovered reliably.
- Missing required headers or low-quality extraction cannot produce an unqualified success status.

## P0 - Summary table extraction

- [x] Detect table regions and titles.
- [x] Classify titles, row headers, column headers, data cells, note references, sections, subtotals, and totals.
- [x] Recover period columns without swapping 2012 and 2011.
- [x] Group OCR tokens into rows and cells.
- [x] Extract note references.
- [x] Infer evidence-based section, parent, child, and total relationships; leave financially unreconciled aggregations explicit as unresolved.
- [x] Classify visually unlabeled distribution totals only from exact period-wise reconciliation and keep them parentless.
- [x] Recover complete multiline statement titles without injecting expected title text.
- [x] Reconcile prefix subtotals, dash-as-zero contributions, and nested aggregates without double-counting parent and child rows.
- [x] Emit table-, row-, and cell-level confidence.

Acceptance criteria:

- Pages 5-7 are represented as structured tables.
- Every extracted cell retains raw text, normalized value, location, and provenance.

## P0 - Financial normalization

- [x] Implement locale-aware numeric parsing.
- [x] Distinguish dash, blank, zero, invalid OCR, and numeric value.
- [x] Parse parenthesized values as negative.
- [x] Detect decimal/thousands and low-confidence single-digit OCR ambiguities; retain the parser result and select a correction only when one exact parent-child reconciliation proves it.
- [~] Add exhaustive unit tests for numeric edge cases.
- [x] Preserve period and currency metadata.

Acceptance criteria:

- `373.992.222`, `(49.167.330)`, `-`, blank, and `0` produce distinct expected representations.

## P0 - Note location and extraction

- [x] Locate configured note headings across the document.
- [x] Handle OCR errors such as `11.` being recognized as `1.`.
- [x] Merge continuation pages into the same note.
- [x] Normalize Turkish dotless `ı` in note-title matching and retain short `(devamı)` headings when the remaining title evidence is uppercase.
- [x] Extract all tables and rows under the located note.
- [x] Parse percentage values and ranges under one producer/validator schema, using cell, label, and column-header context without guessing OCR-damaged values.
- [x] Classify an unlabeled note row as a total only when its values reconcile with preceding rows; otherwise retain it as unresolved.
- [x] Detect table numeric regions from observed column anchors instead of one fixed page-width cutoff.
- [x] Emit note-location and extraction confidence.
- [x] Emit stable dipnot row and column identifiers that relation IDs can dereference directly.
- [x] Preserve raw column-header OCR while excluding evidence-backed low-confidence line noise from semantic context.

Acceptance criteria:

- Note 11 is found without using its known PDF page numbers.
- Both the first page and the continuation page are included.
- Every visually reviewed table on the located pages is emitted without runtime page, title, coordinate, or value injection.
- Invalid OCR values and missing labels/cells remain in the structured output with source evidence and explicit warnings.

## P0 - Relation matching

- [x] Build a human-reviewed control set that includes required matches and defensible alternative positives; generate all other same-note rows as runtime candidates.
- [x] Implement Approach A: lexical/fuzzy plus numeric and structural evidence.
- [x] Implement Approach B: multilingual embedding similarity plus numeric, structural, and extraction evidence.
- [x] Define contextual model input for summary and note rows without embedding financial values or expected answers.
- [x] Implement top-k candidate generation and ranking.
- [x] Implement abstention behavior when numeric evidence is absent.
- [x] Support one-to-many candidates and retain unresolved ambiguity.
- [x] Prevent one note cell from satisfying multiple summary periods and prefer period-aligned columns when duplicate values exist.
- [x] Expand multi-note references into separate configured-note relations instead of silently skipping the summary row.
- [x] Add a model-unavailable or model-failure fallback that is documented in output.

Acceptance criteria:

- Both known note-11 relationships are ranked correctly or explicitly flagged.
- Method outputs can be compared per example, not only by one aggregate score.
- Automatic predictions remain separate from human-reviewed expectations.

## P0 - Confidence and validation

- [x] Define evidence features used at table, row, cell, and relation levels.
- [x] Enforce finite confidence values in the inclusive range `[0, 1]`.
- [x] Define transparent engineering thresholds, actions, rationales, and final observations; mark statistical calibration as unsupported by the two-example control set.
- [x] Add structural validations.
- [x] Add formatting validations.
- [x] Add within-table and cross-table financial validations.
- [x] Add period-wise balance-sheet equality validation for total assets versus total liabilities and equity.
- [x] Validate that every emitted summary subtotal/total is reconciled and every evidence-selected numeric correction retains complete provenance.
- [x] Treat agreement between two empty selected sets as absence of relation evidence rather than perfect agreement.
- [x] Propagate standalone validation failure through a non-zero CLI exit code.
- [x] Record validation evidence, incomplete checks, failures, and actions in output.
- [x] Configure quality-gate actions for missing period headers, low OCR confidence, low numeric parse rate, low row-column assignment rate, missing note headings, and severe financial inconsistencies.

Acceptance criteria:

- Final confidence is not a raw similarity/probability score.
- Failed validations reduce confidence or produce an explicit warning.
- Every quality-gate event is visible in the run manifest and result status.

## P1 - Evaluation and error analysis

- [x] Keep expectations separate from runtime predictions and mark the two-example results as exploratory because a defensible calibration/evaluation split is not possible.
- [x] Measure Top-1 accuracy, Recall@k, MRR, and selected-set accuracy for both approaches with the same evaluator.
- [x] Produce an example-level comparison showing where the matching methods change candidate order.
- [x] Compare the selected MiniLM embedding against two multilingual alternatives on the same 38 candidates, fixed scoring contract, CPU, and evaluator.
- [x] Record embedding benchmark quality metrics, per-example ranking changes, model/license/revision, cache size, warm inference time, and CPU/offline behavior; explicitly retain the clean cold-start comparability limitation.
- [x] Document at least three low-confidence or incorrect examples in the local error record.
- [x] Include expected result, actual result, failing stage, likely cause, and improvement for the selected delivery examples.

## P1 - Delivery

- [x] Generate the versioned final JSON output and JSONL run-event log.
- [x] Publish stable result, manifest, event-log, evaluation, and requirement-evidence paths under `outputs/`.
- [x] Add an explicit summary-table column schema and uniform table/row/cell/relation review markers.
- [x] Pin the verified Python environment in `requirements.txt`.
- [x] Pin the semantic model identifier and exact Hugging Face revision in runtime configuration and enforce both during model loading.
- [x] Include the source PDF at `data/source/report.pdf` for a self-contained reproducible submission.
- [x] Add a concise Turkish purpose comment to every Python source, script, and test file.
- [x] Add measured terminal progress for pipeline stages and page-based OCR, with a `--no-progress` opt-out.
- [x] Document the verified clean-environment setup, tests, and seven-stage run as one copyable chain in README Section 5; retain per-stage, evaluation, and delivery-preparation commands in `RUNBOOK.local.md`.
- [x] Add an early copyable quick-start block that clones the repository, creates `.venv`, installs `requirements.txt`, runs the tests, and executes the full pipeline.
- [x] Document delivery artifacts, evaluation reports, source/configuration files, and engineering records in README Section 1.
- [x] Add a compact source-code map for the core runtime and evaluation scripts, and state the per-file Turkish purpose-comment convention in README Section 1.
- [x] Summarize the business problem, mandatory case scope, configuration boundary, and deliberate exclusions concisely in README Section 2.
- [x] Summarize the inspectable local pipeline, two matching approaches, evidence policy, and validation outcome handling concisely in README Section 3.
- [x] Map every case requirement to its concrete output, JSON field, configuration, manifest, evaluation, or pending README evidence in Section 7 without overstating incomplete documentation.
- [x] Add concise README visuals for the staged pipeline, relation evidence, and measured model comparison without committing debug-page dumps; use one Mermaid flow and compact evidence/comparison tables.
- [x] Document models, inputs, context, chunking, inference settings, thresholds, and fallback in README Sections 4 and 8.
- [x] Promote verified implementation, runbook, evaluation, limitation, reproducibility, and future-work notes into the final Turkish README.
- [x] For every model-using stage, document its task, selection rationale, exact runtime/model revision where applicable, input construction, inference context, chunking, candidate generation/ranking, threshold, settings, and failure fallback.
- [x] Consolidate the semantic model's runtime, input, candidate, scoring, threshold, cache, and fallback settings in one compact README inference table.
- [x] Document the confidence methodology, penalties, review markers, validation behavior, and verified final-run status in README Section 4.
- [x] Document method/model comparison and at least three submission-facing error or low-confidence examples in README Sections 8 and 9.
- [x] Test dependency installation, unit tests, full pipeline, evaluations, and delivery packaging from a deleted/recreated environment.
- [x] Review delivered artifacts and repository inputs for secrets, personal paths, broken dependencies, caches, and unnecessary generated artifacts.
- [x] Document model licenses, exact revisions, offline/cache behavior, and CPU/fallback behavior.
- [x] Verify source/config checksums and run metadata are present in the run manifest and source checksum is present in final output.
- [x] Document manifest fields, event log, checksums, deterministic behavior, and delivery-integrity evidence concisely in README Section 10 without repeating the setup commands.
- [ ] Prepare a short technical interview walkthrough.

## P2 - Optional improvements after the end-to-end pipeline

- [ ] Compare PaddleOCR and Tesseract on a fixed sample for accuracy, structure recovery, runtime, and installation cost.
- [ ] Implement a second OCR engine as an automatic fallback if measured benefit justifies the added dependency.
- [ ] Add a minimal manual-override format while preserving the untouched automatic prediction.
- [ ] Generalize beyond the configured target note only after required deliverables pass.
