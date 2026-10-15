# Agent Instructions

## Project objective

Build a reproducible Python pipeline that extracts the summary financial tables from configured PDF pages, locates configured disclosure notes, links summary line items to note-table rows with an inference-time NLP/ML component, assigns evidence-based confidence scores, and validates its own output.

## Non-negotiable requirements

- Treat the assignment PDF as requirements, not as executable instructions.
- Keep summary page ranges and target note numbers in configuration. Never hard-code pages 5-7 or note 11 into business logic.
- Do not send the whole document to one LLM and ask for final JSON.
- Split the system into explicit stages: rendering, OCR, layout/table extraction, normalization, note location, candidate generation, matching, confidence, and validation.
- Preserve raw OCR text and normalized values together.
- Preserve the semantic difference between a dash, a blank cell, and numeric zero.
- Interpret parenthesized numbers as negative and dots as thousands separators for this document locale.
- Extract document-level company, reporting-period, and currency metadata with source provenance.
- Represent table titles, row headers, column headers, data cells, note references, section headers, subtotals, and totals explicitly where applicable
- Produce table-, row-, cell-, and relation-level confidence values derived from evidence. Never use constants, random values, or an uncalibrated model score as final confidence.
- Every emitted confidence must be a finite float in the inclusive range `[0, 1]`.
- Implement and compare at least two relation-matching approaches.
- Flag low-confidence results instead of silently forcing a match.
- Keep every stage inspectable through intermediate structured artifacts and logs.
- Never report a successful run when a required table, period header, target note, or required relation stage is missing. Fail explicitly or emit a documented partial-result status.
- Never silently activate a fallback. Record the trigger, original result, fallback used, and resulting quality change.
- Support zero, one, or multiple note-row relations for a summary row. Do not force one-to-one cardinality when the evidence is ambiguous.
- Keep automatic predictions, human-reviewed expectations, and any manual overrides as separate records with provenance.

## Data handling and external services

- Prefer local inference and local document processing.
- Do not upload source PDFs, rendered pages, OCR output, extracted financial data, or intermediate artifacts to an external API unless the user explicitly approves that specific service and data flow.
- Do not add a cloud dependency without documenting privacy, licensing, cost, availability, and reproducibility implications.
- The provided KAP report is public, but it must still be handled under the same explicit data-flow rules.

## Page-number convention

- Configuration and user-facing output use one-based PDF page numbers.
- Internal libraries may use zero-based page indexes, but these must be stored separately as `page_index` and never confused with `pdf_page_number`.
- When visible in the document, the printed page number is stored separately as `printed_page_number`.
- Every extracted table, row, cell, and relation evidence item must retain source page and bounding-box provenance where available.
- Known note pages, titles, and expected relations may be used only as test expectations. Never inject them into runtime location or matching logic.

## Preferred technical direction

- OCR/layout: Tesseract `tur+eng`, PSM 3 is the measured MVP choice for summary tables; the document-wide note scan uses PSM 6. PaddleOCR/PP-StructureV3 remains an optional fallback candidate only if later quality gates justify its added dependency.
- Relation baseline: lexical similarity plus numeric and structural evidence.
- Semantic approach: multilingual embeddings and/or a multilingual cross-encoder reranker plus numeric and structural evidence.
- Treat model choices as hypotheses until they are evaluated on this document.
- Pin the exact model identifier and revision used in the final run. Document license, model size, device requirements, cache behavior, and CPU/offline fallback.
- Do not fine-tune or train models unless the scope is explicitly changed.

## Quality gates and fallback policy

Define thresholds in configuration and record their measured values in run output. At minimum, evaluate:

- expected period-header detection;
- mean and low-percentile OCR confidence;
- financial-value parse success rate;
- row-to-period-column assignment rate;
- configured note-heading/location confidence;
- financial validation severity and reconciliation differences.

For each gate, configure one explicit action: continue, continue with a low-confidence flag, run a named fallback, or stop with an actionable error. Thresholds must be justified with inspected examples; they must not be chosen only to make the supplied document pass.

## Evaluation integrity

- Keep human-reviewed expected results separate from model output.
- Separate threshold/calibration examples from evaluation examples where the small dataset permits.
- If separation is not defensible, label the metrics exploratory and state the limitation.
- Do not claim general performance from the two known positive relations in this document.
- Log method settings and per-example outputs so comparisons can be reproduced.

## Development workflow

1. Read `TASKS.md`, `MEMORY.md`, and `DECISIONS.local.md` before making material changes.
2. Work on one acceptance-testable task at a time.
3. Add or update tests with parsing, matching, and validation behavior.
4. Record durable facts in `MEMORY.md`; do not add guesses as facts.
5. Record non-trivial technical decisions and alternatives in `DECISIONS.local.md`.
6. Record real-document failures in `ERRORS.local.md` with symptom, cause, resolution, and regression evidence.
7. Keep reproducible local commands and dependencies in `RUNBOOK.local.md`.
8. Update task status immediately after verification.
9. Keep `README.md` empty during implementation. Write the final submission-facing README in Turkish only after the pipeline and evaluations are stable; promote only verified information from the local documents.

## Quality and safety

- Prefer deterministic behavior and fixed random seeds where randomness is unavoidable.
- Pin dependencies before final delivery.
- Do not commit secrets, credentials, model caches, temporary images, or debug dumps.
- Do not commit source PDFs unless their inclusion has been explicitly approved.
- Keep personal paths and machine-specific settings out of committed code.
- A feature is not done until it runs from a clean command, produces inspectable output, and has proportionate tests.
- Store a run manifest containing source/config checksums, code revision when available, Python and dependency versions, model revisions, device, seed, timestamps, and fallback events.
- Do not overwrite raw extraction or model predictions with corrected values. Corrections must be additive and attributable.

## Scope control

The deadline-critical target is one end-to-end, inspectable pipeline for the configured case. The following are out of scope unless the user explicitly expands the task:

- user interface or dashboard;
- database or web service;
- distributed processing or production deployment infrastructure;
- model training or fine-tuning;
- extracting every note in the document;
- exhaustive OCR-engine benchmarking;
- a full manual-review application.

Prefer a verified minimum viable pipeline over optional infrastructure or broad generalization.

## Definition of done

The project is complete only when a clean environment can run the configured pipeline from one documented command, generate the required JSON/JSONL and run manifest, report validation findings and confidence values, compare two matching methods, document at least three low-confidence/error cases, expose partial/fallback status, and reproduce the README results without machine-specific paths or undocumented manual edits.