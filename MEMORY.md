# Project Memory

This is local working memory. Store verified, durable facts here. Put choices and rationale in `DECISIONS.local.md`; put deliverable documentation in `README.md` or `docs/`.

## Assignment facts

- Objective: extract configured summary financial tables and link summary rows referencing a configured note to the correct rows in that note's tables.
- Required summary range for the provided case: PDF pages 5-7.
- Required target for the provided case: note 11.
- Page range and note number must come from configuration.
- Training a model is not required; inference with a ready model is required for relation matching.
- Exact text matching alone is insufficient.
- One end-to-end whole-document LLM-to-JSON call is explicitly unacceptable.
- Required confidence levels: table, row, cell, and relation.
- Final confidence cannot be a fixed/random value or a raw model score alone.
- Required validation groups: structural, format, and financial.
- At least two matching approaches and at least three low-confidence/error examples are required.
- Deliverables: source code, JSON/JSONL output, and README.

## Verified source-document facts

- The KAP source report has 95 PDF pages.
- It is an image-based/scanned report with no useful embedded text layer.
- PDF metadata reports page rotation; rendered orientation must be verified.
- Page 5 contains the asset side of the consolidated balance sheet.
- Page 6 contains liabilities and equity.
- Page 7 contains the consolidated statement of comprehensive income.
- Note 11 begins on PDF page 53 and continues on PDF page 54; these page numbers are test observations, not allowed business-logic constants.
- Known note pages, note titles, and expected relations are evaluation expectations only and must never be injected into runtime logic or model inputs.
- OCR may read the first `11.` note heading as `1.`; the continuation heading is a recovery signal.
- User-facing and configuration page numbers are one-based PDF page numbers. Internal zero-based indexes and printed page numbers must be stored separately.

## Human-reviewed expected relationships and ambiguities

1. Summary row `Yatırım Amaçlı Gayrimenkuller` links to the note-11 closing balance/net book value context.
   - 2012: `373.992.222`
   - 2011: `423.580.000`
   - The note contains multiple rows/totals with the same values. The schema must preserve candidate ambiguity or one-to-many supporting evidence rather than silently forcing a unique row.
2. Summary row `Yatırım Amaçlı Gayrimenkul Değerleme Farkları` links to `Makul değer değişikliğinden kaynaklanan kazanç`.
   - 2012: `3.896.434`
   - 2011: `151.350.000`

## Known OCR risks

- Adjacent digits in note numbers can merge or disappear.
- Turkish characters may be confused or dropped.
- Words such as `konut` may be recognized incorrectly.
- Lines and typography can interfere with row and cell segmentation.
- Period columns can be swapped if extraction ignores geometry.

## Agreed guardrails

- Local document processing and local inference are the default.
- No document or extracted financial data is sent to an external API without explicit approval.
- Missing required content, fallback use, and partial results must be reported explicitly.
- Raw extraction, automatic predictions, expected results, and manual corrections remain separate and attributable.
- The delivery target is a minimal end-to-end pipeline; UI, services, databases, training, and deployment infrastructure are out of scope.

## Required quality signals

- Expected period-header detection.
- OCR confidence distribution, not only a single mean.
- Financial-value parse success rate.
- Row-to-period-column assignment rate.
- Target note-location confidence.
- Financial reconciliation differences and validation severity.
- Each configured threshold maps to an explicit continue, flag, fallback, or stop action.

## Current technical direction

The OCR and both required matching approaches have been measured for the current MVP:

- Tesseract `tur+eng`, PSM 3 as the MVP OCR engine.
- PaddleOCR/PP-StructureV3 only as a later fallback candidate if quality gates show a material need.
- Lexical/fuzzy + numeric evidence as Approach A.
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` embeddings + numeric/structural evidence as Approach B; BGE-M3/reranker was rejected for the MVP as disproportionate to the short 38-candidate workload.

## Open questions

- Statistical confidence calibration remains unsupported without a larger labeled set; current thresholds are explicit engineering review thresholds.
- Minimum labeled control-set size that is defensible within the deadline.

## Current implementation state

- Git repository initialized on branch `main`.
- Packaging uses the pinned `setuptools==80.9.0` build backend through `pyproject.toml`. The verified runtime environment is fully pinned in `requirements.txt`, whose final entry installs the local package as a normal wheel rather than an editable `.pth` link. Terminal progress uses the pinned `tqdm==4.70.1` dependency.
- CLI progress is enabled by default: the end-to-end command reports seven pipeline stages, while summary OCR, document-wide note OCR, and note-table OCR report measured page counts. Model initialization uses a status message rather than an invented percentage. `--no-progress` disables all progress output.
- Minimal standard-library Python package and JSON configuration loader created.
- Configuration accepts arbitrary positive target note numbers; note 30 is covered by a test to guard against note-11 hard-coding.
- Assignment-specific financial integer parsing and confidence/page-identity primitives are implemented.
- Source report SHA-256: `25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0`.
- Configured PDF pages 5-7 render successfully at 300 DPI with correct visual orientation.
- The initial PSM 6 smoke test succeeded but misread the page-5 note reference `11` as `1]`.
- A reproducible comparison of PSM 3, 4, 6, and 11 selected PSM 3: 10/10 reviewed-token hits, 2/2 complete target rows, 2/2 clean numeric rows, and aggregate mean confidence `0.945077`.
- Tesseract `tur+eng`, PSM 3 produces word-level text, bounding boxes, and normalized confidence for pages 5-7.
- Period headers `2012` and `2011` were recovered on all three configured pages.
- Critical values `373.992.222`, `3.896.434`, and `151.350.000` were recovered on their expected summary pages.
- Seventeen automated tests pass after the Stage 2 closeout checks.
- Stage 2 produces three structured summary tables with dynamically detected period and note-reference columns; no fixed table coordinates or note-11 values are used.
- Pages 5 and 6 have `1.0` row-label and period-cell assignment rates.
- Page 7 has `1.0` period-cell assignment and `0.925926` row-label assignment; two repeated total lines have no recovered label and are emitted with explicit `missing_row_label` warnings.
- The Stage 2 document status is therefore `completed_with_warnings`.
- Both human-reviewed note-11 summary rows are present with correct raw and normalized values, but this observation remains evaluation evidence rather than runtime input.
- The document-wide note scan uses 110 DPI JPEG rendering and Tesseract `tur+eng`, PSM 6 independently from the summary-table OCR settings.
- The locator scanned all 95 pages and found the exact `11. ... (devamı)` heading on PDF page 54.
- It recovered PDF page 53 as the note start because OCR read its heading number as `1.` while its normalized title matched the verified continuation with similarity `1.0`.
- The resulting note-11 location is PDF pages 53-54 with evidence-based confidence `0.956727` and status `located_with_recovery`.
- A table row on PDF page 89 initially caused a false note-11 match; rejecting heading candidates containing multiple financial fragments and grouping exact numbers by title removed the false positive.
- Twenty-one automated tests pass after the note-location stage.
- The note-extraction stage re-renders only the located note pages at 300 DPI and runs Tesseract `tur+eng`, PSM 3; located page numbers come from `note_locations.json`, not runtime constants.
- The geometry-based extractor found all four visually reviewed note-11 tables: two movement tables on PDF page 53, the three-row valuation-assumptions table on page 54, and the five-row fair-value table on page 54.
- The first page-53 table has `1.0` row-label, cell-assignment, and parse-success rates. The second has `1.0`, `0.933333`, and `0.866667` respectively because OCR damaged or missed three cells.
- The page-54 assumptions table has `1.0` row-label and cell-assignment rates but `0.5` parse success because three percentage values are visibly present yet corrupted by OCR; raw text and warnings are retained instead of guessed corrections.
- The page-54 fair-value table has `0.8` row-label assignment and `1.0` cell assignment/parse success; its final total row is preserved with a `missing_row_label` warning.
- The note-extraction result is `completed_with_warnings`, contains table/row/cell confidence and source bounding boxes, and is stored at `work/structured/note_tables.json`.
- The current note-extraction artifact contains 4 tables, 19 rows, and 8 explicit warnings: 4 on the 2011 movement table, 3 on the assumptions table, and 1 on the fair-value total row.
- Twenty-four automated tests pass after the note-table extraction stage.
- Approach A creates candidates only between configured-note summary rows and the extracted rows of the same note; it does not read `evaluation/relation_expectations.json` at runtime.
- The current run generated 38 candidates: 2 target summary rows multiplied by 19 extracted note rows. Ranking uses numeric coverage, lexical similarity, structural compatibility, and extraction evidence quality.
- `summary-p5:row-13` selected `note-11-p54-t2:row-5` with full two-period numeric coverage and retained `ambiguous: true` because the same balances occur in several defensible note rows.
- `summary-p7:row-6` selected both `note-11-p53-t1:row-3` and `note-11-p53-t2:row-4`, covering the 2012 and 2011 values with a one-to-many relation.
- The independent evaluator reports selected-set accuracy, Top-1 accuracy, Recall@5, and MRR as `1.0` on the two human-reviewed relationships. These figures are exploratory case checks, not a generalization claim.
- Relation output preserves top-k candidates, per-feature scores, matched values, source bounding boxes, ambiguity, unmatched periods, and confidence at `work/matching/baseline_relations.json`.
- Twenty-nine automated tests pass after the baseline matching and relation-evaluation stage.
- Approach B uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through FastEmbed `0.9.0` and local ONNX Runtime on CPU. The model is multilingual, produces 384-dimensional embeddings, is declared as Apache-2.0, and the quantized FastEmbed artifact is approximately `0.22 GB`.
- The resolved FastEmbed model source is `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`.
- Semantic model inputs include row labels, row types, target note number, reporting periods, and note-table column headers. Financial values remain a separate exact-match feature, and human expectations are excluded from model inputs.
- Semantic scoring uses `0.50` numeric coverage, `0.25` embedding cosine similarity, `0.10` structural compatibility, and `0.15` extraction-evidence quality. It preserves the same zero/one/many selection and ambiguity behavior as the baseline.
- The real semantic run evaluated all 38 candidates, completed without fallback, and selected the same correct row sets as the baseline for both reviewed relationships.
- Baseline and semantic methods both report selected-set accuracy, Top-1, Recall@5, and MRR of `1.0` on the two-example control set. The metric delta is zero and remains exploratory rather than evidence of general performance.
- The selected sets and Top-1 candidates agree on both examples, but the lower Top-5 ordering differs on both. Semantic ranking promotes the net-book-value alternative for the first relationship and an unsupported `Bağcılar Arsa` row to third place for the second relationship.
- The exact cached model revision was successfully loaded with downloads disabled and produced a 384-dimensional vector, verifying local/offline reuse after initial setup.
- Thirty-three automated tests pass after semantic matching, fallback, provenance, and method-comparison coverage.
- Phase 6 emits `work/validation/validation_report.json` without modifying upstream OCR, extraction, or prediction artifacts.
- The validation layer runs four structural checks, three format-contract checks, detail-to-total financial reconciliations, and relation-period value-coverage checks. Non-applicable and OCR-incomplete checks are distinct from failures.
- The latest real Phase 6 run completed with warnings and no stop-gate failure: 15 checks passed, 0 failed, 3 were incomplete, and 1 was not applicable. The added balance-sheet equality check passed for both 2011 and 2012 with zero difference.
- Summary OCR minimum page mean and p10 confidence are `0.942237` and `0.921169`; period-header coverage and summary period-cell assignment are both `1.0`; minimum summary row-label assignment is `0.925926`.
- Note-location confidence is `0.956727`; minimum note cell assignment is `0.933333`. Minimum note parse success is `0.5`, so the configured `0.8` gate correctly emits a warning rather than an unqualified success.
- Five applicable financial detail-to-total checks pass exactly: three columns in the 2012 movement table and two columns in the fair-value table. Three checks in the OCR-damaged 2011 movement table remain incomplete; no expected values are substituted.
- Both semantic relations retain `1.0` period-value coverage. In the latest verified run, evidence-aggregated final confidence is `0.856148` for `summary-p5:row-13` after an ambiguity penalty and `0.893874` for `summary-p7:row-6`.
- Final relation confidence combines matcher confidence, numeric coverage, selected extraction quality, baseline-semantic agreement, and explicit ambiguity/fallback/partial-match penalties. It is a review-prioritization score, not a calibrated probability.
- Thirty-nine automated tests pass after the confidence, validation, financial-reconciliation, severe-difference, and quality-gate stage.
- A controlled embedding-model comparison is requested for the final technical narrative. It must reuse the same structured inputs, 38 candidates, weights, evaluator, and hardware; only the embedding model may change.
- Because the reviewed control set contains only two positive relationships, embedding models must not be ranked by aggregate accuracy alone. Candidate-order changes, semantic score margins, runtime, artifact size, license, revision, CPU/offline support, and failure behavior must also be reported.
- Limit the comparison to the current MiniLM model plus at most two defensible multilingual alternatives, and run it after the mandatory validation and one-command pipeline are stable so it cannot displace required delivery work.
- The mandatory stages run from one command with `--stage all`. The verified real run executed seven stages in order and produced stable delivery artifacts at `outputs/result.json`, `outputs/run_manifest.json`, and `outputs/run_events.jsonl`; timestamped diagnostic history remains under `work/`.
- The verified end-to-end run status is `completed_with_warnings`: 15 checks passed, 0 checks failed, 3 OCR-dependent financial checks were incomplete, 1 check was not applicable, 0 stop gates failed, and 3 warning gates failed.
- The clean first run on 2026-10-15 took approximately `175.83` seconds across recorded stage durations. The document-wide note location dominated runtime at `113.717586` seconds; semantic model download plus inference took `49.389478` seconds with an initially empty project cache.
- The final JSON is schema version `1.0`, contains two automatic semantic relations enriched with evidence-aggregated final confidence, preserves the original matcher confidence separately, and embeds validation evidence and warnings. Its verified status is `completed_with_warnings` and it contains no human-reviewed expectation labels or machine-specific absolute paths.
- The run manifest is schema version `1.0` and records the source/config SHA-256 values, Python/platform and package versions, Tesseract/Poppler versions, code revision state, seed, timestamps, per-stage status/duration/output checksum, fallback events, final-output checksum, and failure details when applicable.
- The clean verified run used source SHA-256 `25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0` and config SHA-256 `4141aa590a98e70ef6f8e4136fdf4ff3a6c5eca9fb8e89f15138d479e3a38ab3`. No fallback was used and final-output SHA-256 `b515a0ec3f048a7bc9960273ce28032a8791bcdd7c37399b6304c5d328eb7385` matched the manifest.
- Forty-one automated tests passed after adding orchestration, checksum, final-confidence promotion, and evaluation-label isolation coverage.
- Summary rows now expose stable `row_id`, `parent_row_id`, `child_row_ids`, `hierarchy_level`, `hierarchy_role`, `hierarchy_basis`, and evidence confidence. Subtotal/total rows additionally expose `aggregation_of_row_ids` and `aggregation_status`; only exact period-wise reconciliations are emitted as aggregation links.
- The latest real hierarchy run produced 51 parent links across the three summary tables and four exact reconciled aggregations on page 7: `BRÜT KAR`, `FAALİYET KARI`, and the two visually unlabeled distribution totals. The unlabeled totals are parentless and point to their two contributing rows; other unreconciled subtotals/totals remain explicit instead of guessed.
- An unlabeled financial row now terminates section-membership inference. This prevents the page-7 `Dönem Karı Dağılımı` section from incorrectly absorbing later `Hisse başına kazanç` and comprehensive-income rows.
- Semantic fallback evidence now records its trigger, the failed semantic result, the baseline fallback result, and the resulting loss of semantic evidence. The normal real run still completes without fallback.
- Run manifests now embed resolved model/provider revision, runtime device, all configured quality-gate results, and the validation summary in addition to checksums and stage metadata.
- The verified post-change run `20261014T184111351485Z` completed with warnings, used the pinned MiniLM FastEmbed revision on CPU, recorded 15 quality gates, used no fallback, preserved both correct relation selections and matched its final-output checksum.
- Fifty-three automated tests pass after adding dipnot row/column referential integrity, multiline title recovery, reconciled unlabeled totals, and evidence-based semantic header cleanup.
- The bounded embedding benchmark compared `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, `minishlab/potion-multilingual-128M`, and `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` on the same 38 candidates, two reviewed relations, CPU threads, contexts, non-semantic weights, Top-5 setting, threshold, and evaluator.
- All three models selected the same correct relation sets and reported exploratory selected-set accuracy, Top-1 accuracy, Recall@5, and MRR of `1.0`; the two-example set therefore provides no evidence of a general quality winner.
- Resolved model revisions are MiniLM `faf4aa4225822f3bc6376869cb1164e8e3feedd0`, Potion `3766c5fca8a199c3d6801461f289f4459719ba31`, and MPNet `e5d116277351513fd260955ece953ecddde7046e`.
- Measured cache sizes are approximately 252,141,023 bytes for MiniLM, 547,008,811 bytes for Potion, and 1,127,147,809 bytes for MPNet. Declared licenses are Apache-2.0, MIT, and Apache-2.0 respectively.
- Warm median full 38-candidate inference times in the latest reproduced benchmark were `0.231708` seconds for MiniLM, `0.005614` seconds for Potion, and `0.812925` seconds for MPNet. These are single-machine diagnostic timings, not general throughput claims.
- Potion's raw semantic scores ranked percentage/assumption rows above the correct gain rows on the second example; exact numeric evidence still prevented their selection. MPNet produced a larger semantic margin for the correct gain rows but did not improve any reviewed selection metric and was roughly 4.47 times the MiniLM cache size and 3.72 times its warm runtime.
- MiniLM remains the selected MVP model because no alternative improved the reviewed outputs, it has the smallest measured cache footprint, and its runtime is proportionate to the 38-candidate task. Potion's speed benefit does not offset its larger artifact and weaker raw semantic ordering on the observed error case; MPNet's margin benefit is not material enough on two examples to justify its approximately 4.47× cache and 3.51× warm-runtime cost.
- Initial model-loading observations are not a fair clean cold-start comparison: MiniLM was cached before the benchmark, while the two alternatives were downloaded during their first initialization. This limitation must be stated rather than presenting those times as comparable cold-start latency.
- Every final summary table now exposes an explicit `columns` list containing the implicit row-label column, extracted note-reference column, and dynamically detected period data columns with source provenance where available.
- Final table, row, cell, and relation records expose `review_required` and `quality_flags`. Confidence thresholds come from configured quality gates; extraction warnings, invalid values, missing labels, unresolved aggregations, incomplete relations, ambiguity, and fallback remain explicit reasons rather than a single opaque flag.
- The verified final run completed with warnings, no stop-gate failure, and no fallback. It produced 7 reviewed tables, 21 reviewed rows, 16 reviewed cells, and 1 reviewed relation; the relation is flagged because multiple numerically defensible alternatives remain, not because its final confidence is below threshold.
- `outputs/delivery_index.json` maps ten assignment requirements to stable files and JSON locations, and records size plus SHA-256 for every indexed runtime/evaluation artefact. Five comparison/evaluation artifacts are copied under `outputs/evaluation/` by `scripts/prepare_delivery_artifacts.py` only after required source artifacts exist.
- A destructive clean rebuild was verified on 2026-10-15: `.venv/`, `work/`, `outputs/`, Python caches, and editable-install metadata were removed; a new Python 3.13 environment installed only `requirements.txt`; `pip check` passed; the then-current 49 tests passed; the seven-stage real pipeline, two relation evaluations, method comparison, four-PSM comparison, and three-model embedding benchmark were regenerated from scratch.
- The installed `ykt-case` console entry point initially exposed a macOS hidden-`.pth` editable-install failure that `PYTHONPATH=src` had masked. Switching the final requirements entry from `-e .` to a normal local wheel (`.`) fixed the issue; help, config smoke test, direct import, `pip check`, and the current 64 tests pass without `PYTHONPATH`.
- Delivery separation is intentional: raw/intermediate/history artefacts remain under ignored `work/`; stable reviewer-facing results are copied or written under `outputs/`. A third duplicate `delivery/` tree is avoided because it would add stale-copy risk without adding provenance.

## Documentation policy

- Final Turkish README authoring began after the clean rebuild and delivery audit; its agreed heading structure is present and content will be filled collaboratively from verified local records.
- README Section 8 now records the four-PSM comparison, baseline-versus-semantic evaluation, three-model embedding benchmark, exact selected model revision, and selection rationale without turning the two reviewed relations into a general performance claim.
- README Section 9 now presents five real-document error or low-confidence examples with expected/actual behavior, cause, mitigation, remaining limitation, and direct delivery evidence.
- README Section 10 documents the run manifest, event log, deterministic behavior, source/config/final-output checksums, and delivery index. Redundant project-tree and separate technical-decisions sections were removed; future improvements is now Section 11.
- README Section 11 limits future work to an evidence-gated PaddleOCR fallback comparison, a broader multi-report evaluation set, and a conditional reranker experiment; none is presented as required for the current MVP.
- README Section 4 now includes a concrete summary-to-note relation evidence diagram and a compact table of five representative quality gates with configured thresholds, final observations, and actions; full gate evidence remains linked to config, result, and manifest.
- README Section 1 now includes a 15-row source-code map covering the core runtime and evaluation scripts. Every Python file carries a short Turkish purpose comment; executable scripts keep the shebang first and place that comment immediately below it.
- Reproducible installation and execution commands live in `RUNBOOK.local.md` until final delivery.
- Observed failures, root causes, fixes, and regression evidence live in `ERRORS.local.md`.
- Only verified and still-current information will be promoted from these files into the final README.
- The source report is included at `data/source/report.pdf`; its verified SHA-256 is `25e4afe4c27bd2b3bb17a943a323e265520e68981c349f300d9248b3f3bfd7e0`.
- Every emitted disclosure-note row and column now carries a stable `row_id` or `column_id`; relation IDs resolve directly to emitted rows rather than relying on consumer-side reconstruction.
- Summary-table titles now join the adjacent date/audit line with the line containing `KONSOLİDE`, producing the complete visual title on all three configured pages.
- The page-54 header artifact `Ooo` remains in `raw_text` with source provenance, is removed only from evidence-based `normalized_text`, and no longer enters semantic model context.
- Percentage cells now use explicit `percentage` and `percentage_range` statuses shared by extraction and validation. Context may come from the cell, row label, or column header; values outside `[0, 100]` and OCR text without defensible percentage evidence remain invalid rather than being guessed.
- Numeric relation coverage consumes each note cell at most once and prefers a cell whose column header matches the summary period. A repeated value in one note cell therefore cannot falsely cover two summary periods.
- Multi-note references are parsed into separate relations for each configured note number. Turkish dotless `ı` is normalized in matching and note-location text, and short continuation headings are evaluated after removing the `(devamı)` marker.
- Unlabeled disclosure-note rows begin as unresolved and become totals only after exact period-wise reconciliation with preceding rows. Their `classification_basis` and contributing row IDs remain explicit.
- Disclosure-table numeric-region detection is derived from observed column anchors; the former fixed `46%` page-width boundary is no longer the sole inclusion rule.
- Empty selected sets no longer receive perfect method-agreement evidence, and standalone validation failures terminate the CLI with a non-zero exit code.
- The latest verified run `20261015T094254771236Z` started from clean Git revision `99e59254b2c42bb64b78ebbc8eeba5f57af8a4ad`, completed all seven stages in approximately `128.50` seconds with no fallback, 15 passed validations, 0 failures, 3 incomplete OCR-dependent checks, and 1 not-applicable check. Final output SHA-256 is `7f572ae099336bc98d7c286a55b197af691406500ffbd319c84eacbfe6e544c5`.
