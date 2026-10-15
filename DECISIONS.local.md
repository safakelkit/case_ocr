# Local Decision Log

Use this file for material decisions. Promote submission-relevant decisions and evidence into `README.md` or `docs/` before delivery.

## D-001 — Use agentic coding for development, not as the runtime architecture

- Status: accepted
- Date: 2026-10-13
- Decision: use coding agents to accelerate implementation, testing, review, and documentation. The delivered application remains an explicit, staged, reproducible pipeline rather than an autonomous agent.
- Rationale: the case rewards decomposition, explainability, validation, uncertainty handling, and reproducibility. A deterministic pipeline is easier to audit and defend in an interview.
- Consequence: agent-generated changes require tests and human-understandable rationale; no opaque prompt-only implementation is accepted as done.

## D-002 — Use staged extraction rather than whole-document prompting

- Status: accepted
- Date: 2026-10-13
- Decision: implement separate rendering, OCR, layout/table extraction, normalization, note location, candidate generation, relation matching, confidence, and validation stages.
- Rationale: this is explicitly required by the assignment and supports inspection, fallback, and error attribution.
- Consequence: every stage should expose structured intermediate output and provenance.

## D-003 — Local-first data processing

- Status: accepted
- Date: 2026-10-13
- Decision: process the source document and run model inference locally by default. External APIs require explicit approval of the service and data flow.
- Rationale: local execution improves confidentiality control, auditability, cost predictability, and reproducibility for a banking-oriented case.
- Consequence: dependencies must document offline/cache behavior and CPU or local-device fallback.

## D-004 — Fail visibly and govern fallbacks with quality gates

- Status: accepted
- Date: 2026-10-13
- Decision: define measurable gates for period headers, OCR confidence, numeric parse rate, row-column assignment, note location, and financial validation. Each gate has an explicit continue, flag, fallback, or stop action.
- Rationale: a structurally valid JSON file can still be financially wrong; silent partial success is unacceptable.
- Consequence: run output must include gate measurements, threshold versions, fallback events, and partial/failure status.

## D-005 — Preserve page identities and source provenance

- Status: accepted
- Date: 2026-10-13
- Decision: distinguish one-based PDF page number, zero-based internal index, and printed page number. Retain page and bounding-box provenance for extracted evidence.
- Rationale: scanned reports frequently have different PDF and printed numbering, creating off-by-one and auditability risks.
- Consequence: the output schema and tests must cover all three concepts explicitly.

## D-006 — Support ambiguity and non-one-to-one relations

- Status: accepted
- Date: 2026-10-13
- Decision: relation output supports zero, one, or multiple note rows plus a primary candidate and supporting evidence where appropriate.
- Rationale: several note rows can share the summary value or jointly explain a summary line item.
- Consequence: the matcher may abstain or preserve alternatives instead of manufacturing a unique answer.

## D-007 — Protect evaluation integrity on the small sample

- Status: accepted
- Date: 2026-10-13
- Decision: keep expected labels separate from predictions and separate calibration from evaluation where defensible. Otherwise report results as exploratory.
- Rationale: the provided case has too few known positive relations to support broad performance claims.
- Consequence: README metrics must state sample size, labeling method, and limitations.

## D-008 — Prioritize the minimum viable end-to-end delivery

- Status: accepted
- Date: 2026-10-13
- Decision: complete and verify one end-to-end pipeline before optional OCR comparisons, manual-review tooling, or broader generalization.
- Rationale: the deadline rewards a reproducible, explainable solution more than optional infrastructure.
- Consequence: OCR-engine benchmarking and a second OCR implementation are P2 unless the primary extraction cannot meet quality gates.

## D-009 — Prevent answer leakage from inspected examples

- Status: accepted
- Date: 2026-10-13
- Decision: known note pages, headings, and expected relations are used only in test assertions and evaluation labels, never as runtime features or fallback answers.
- Rationale: changing `target_note` from 11 to another number must invoke the same generic note-location and matching logic.
- Consequence: configuration provides the requested note number but never its page, title, or expected linked rows.

## D-010 — Use Tesseract PSM 3 for the MVP OCR stage

- Status: accepted
- Date: 2026-10-14
- Decision: use local Tesseract with `tur+eng` and PSM 3 for the current MVP. Consider a second OCR engine only if later quality gates show a material extraction failure.
- Rationale: on the fixed pages 5-7, PSM 3 recovered 10/10 reviewed tokens, 2/2 complete target rows, 2/2 clean numeric rows, and had the highest compared mean confidence (`0.945077`). PSM 6 misread the page-5 note reference, while PSM 11 fragmented numeric rows.
- Consequence: `configs/default.json` uses PSM 3. The comparison remains reproducible and is documented as exploratory rather than a general benchmark.

## D-011 — Reconstruct summary tables from detected header geometry

- Status: accepted
- Date: 2026-10-14
- Decision: derive note and period column positions from their OCR header tokens, then associate financial cells and row labels by vertical geometry. Do not store document-specific pixel coordinates or target values in runtime logic.
- Rationale: the three configured pages use different column positions, while their semantic headers provide stable per-page anchors. A synthetic note-30 test verifies that the extractor is not tied to note 11.
- Consequence: missing period or note-reference headers fail explicitly. Unlabeled numeric rows remain in output with warnings instead of being silently discarded or assigned a guessed label.

## D-012 — Locate notes with a low-resolution full-document OCR pass

- Status: accepted
- Date: 2026-10-14
- Decision: scan every PDF page at 110 DPI with Tesseract PSM 6, detect numbered uppercase headings, and locate configured notes using number, normalized title, continuation, and page-sequence evidence.
- Rationale: the source has no useful text layer, while rendering all 95 pages at the 300 DPI extraction resolution would add unnecessary cost. The lighter scan recovered the target and exposed both a corrupted heading number and a table-row false positive.
- Consequence: runtime stores candidate headings and evidence, excludes number-like table rows with multiple financial fragments, and may recover a corrupted first-page number only from a verified same-title continuation on the next page.

## D-013 — Extract note tables from repeated column geometry

- Status: accepted
- Date: 2026-10-14
- Decision: re-render pages returned by the note locator at 300 DPI with Tesseract PSM 3, identify tables from repeated right-side numeric column clusters and vertical separation, then recover headers and row labels from adjacent geometry. Preserve invalid OCR values and missing cells as warnings rather than correcting them from known answers.
- Rationale: note 11 contains four tables with two- and three-column layouts, multi-line headers, wrapped row labels, percentages, dashes, totals, and prose between tables. Repeated column geometry separates these structures without hard-coded page coordinates, titles, or values.
- Consequence: the extractor supports arbitrary configured note numbers and non-contiguous located pages, but OCR-damaged cells remain explicit partial evidence for later quality gates or a named OCR fallback.

## D-014 — Establish an explainable relation-matching baseline before semantic inference

- Status: accepted
- Date: 2026-10-14
- Decision: generate candidates from every extracted row belonging to the configured note and rank them with separately reported numeric coverage, lexical similarity, structural compatibility, and extraction-evidence quality. Retain top-k candidates, allow a selected set of zero, one, or multiple rows, and keep ambiguity explicit.
- Rationale: exact financial values are strong auditable evidence, while text and row structure distinguish detail rows from totals. A transparent baseline is necessary to show whether a semantic model adds measurable value rather than merely adding complexity.
- Consequence: the runtime never consumes human expectations. `evaluation/relation_expectations.json` is used only by the independent evaluator, and its two-example metrics must be described as exploratory. Approach B must use the same candidates, output shape, and evaluator for a fair comparison.

## D-015 — Use a compact multilingual embedding model as Approach B

- Status: accepted
- Date: 2026-10-14
- Decision: use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` via FastEmbed's quantized ONNX CPU runtime. Replace the baseline lexical weight with cosine-based semantic similarity while retaining exact numeric coverage, structural compatibility, and extraction quality as independent evidence.
- Rationale: the model supports multilingual sentence similarity, has an Apache-2.0 license, emits compact 384-dimensional vectors, and its approximately `0.22 GB` quantized artifact is materially smaller than the multi-gigabyte BGE-M3 alternatives. This is proportionate to 38 short candidate pairs and a local-first banking case.
- Consequence: the first run may download the public model into `work/models/fastembed`; subsequent runs can set downloads off and use the cache. Runtime output records provider version, model source, resolved revision, license, dimensions, input policy, and whether fallback occurred. If loading or inference fails, the system emits an attributable baseline fallback rather than silently claiming semantic execution.

## D-016 — Separate validation status from evidence-aggregated confidence

- Status: accepted
- Date: 2026-10-14
- Decision: run structural, format, financial, and cross-relation validations as an explicit stage. Each configurable gate records its observed metric, comparator, threshold, action, outcome, and rationale. Aggregate final relation confidence from matcher confidence, normalized-value coverage, extraction quality, baseline-semantic agreement, and explicit penalties; do not present it as a calibrated probability.
- Rationale: a high model score cannot prove that periods, table geometry, numeric representations, or financial totals are valid. Conversely, OCR damage may make a check incomplete without proving a financial inconsistency. These states must remain distinguishable.
- Consequence: stop-gate failures produce a failed validation status, warning gates produce `completed_with_warnings`, and incomplete reconciliations never receive guessed values. Current thresholds are transparent engineering thresholds and remain exploratory until a larger document-level labeled set permits calibration.

## D-017 — Deliver one deterministic command with separate result, manifest, and event log

- Status: accepted
- Date: 2026-10-14
- Decision: make `--stage all` execute the seven mandatory runtime stages in a fixed order and emit three distinct artifacts: a versioned final JSON result, a versioned reproducibility manifest, and an append-only JSONL event log. Human-reviewed evaluation files are not read by this path.
- Rationale: the final business result should remain readable without being overloaded by environment diagnostics, while a separate manifest must make the exact run auditable and a JSONL log must expose progress and failure boundaries. Keeping evaluation labels outside runtime prevents answer leakage.
- Consequence: the result preserves extraction, automatic relations, evidence-aggregated confidence, validation and warnings; the manifest records checksums, revisions, dependency/system versions, seed, timestamps, durations, stage outputs and fallback events. A failed validation status remains failed and the CLI exits non-zero for it; warning-only results remain explicit `completed_with_warnings` outcomes.

## D-018 — Emit only evidence-backed hierarchy and aggregation relations

- Status: accepted
- Date: 2026-10-14
- Decision: derive parent/child links conservatively from explicit section headers and material indentation differences. Emit subtotal/total aggregation membership only when a contiguous set of preceding rows reconciles exactly for every reporting period; an unlabeled line may be promoted to a parentless total only by the same exact reconciliation. Otherwise keep its structure explicit and unresolved.
- Rationale: the case requires main/sub/total relationships, but scanned-table indentation alone can overstate financial semantics. Exact numeric reconciliation is stronger evidence for aggregation, while an unlabeled line must terminate uncertain section inference so the relation does not leak into a later block.
- Consequence: every summary row exposes stable hierarchy fields and evidence basis. Downstream consumers can distinguish an explicit section, indentation inference, exact reconciled aggregation, and unresolved total instead of treating all structural links as equally certain.

## D-019 — Keep model and gate evidence directly visible in the run manifest

- Status: accepted
- Date: 2026-10-14
- Decision: copy the resolved semantic model metadata, source revision, device, every quality-gate result, and validation summary into the run manifest. When fallback occurs, record the trigger, failed original semantic result, baseline fallback result, and resulting evidence-quality loss.
- Rationale: an output checksum proves which file was produced but does not make the model or gate behavior directly auditable. Reproducibility and silent-fallback prevention require these facts in the manifest itself.
- Consequence: a reviewer can inspect one manifest to determine the exact local model/runtime, quality-gate outcomes, and whether any semantic evidence was lost to fallback.

---

## D-020 — Retain multilingual MiniLM after the bounded embedding benchmark

- Status: accepted
- Date: 2026-10-14
- Decision: retain `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for the MVP after comparing it with `minishlab/potion-multilingual-128M` and `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` under the same 38 candidates, contexts, non-semantic weights, thresholds, CPU setting, and evaluator.
- Rationale: all three models produced identical correct selected sets and tied on the two-example exploratory metrics. MiniLM had the smallest measured cache footprint (~252 MB). Potion was faster in the clean reproduced warm run but used ~547 MB and ranked unrelated percentage rows above the correct rows by raw semantic similarity. MPNet showed a better semantic margin on one example but used ~1.13 GB, was ~3.72 times slower than MiniLM in warm full-candidate inference, and did not improve a selected-set metric.
- Consequence: the README may present the comparison as diagnostic model selection evidence, not a general benchmark. Numeric coverage remains mandatory selection evidence. Clean cold-start times are not compared because MiniLM was already cached while the alternatives were first downloaded; this limitation remains explicit.

---

## D-021 — Show only measurable terminal progress

- Status: accepted
- Date: 2026-10-15
- Decision: use pinned `tqdm==4.70.1` for the seven deterministic pipeline stages and for page-counted OCR loops. Use plain status messages for model loading, where a defensible total is unavailable, and expose `--no-progress` for quiet or redirected runs.
- Rationale: the full-document OCR can take several minutes and previously appeared frozen, while a fabricated model-loading percentage would be misleading. The JSONL event log remains the durable machine-readable record; terminal progress is only an operator-facing view.
- Consequence: interactive runs show stage, page count, throughput, elapsed time, and ETA where measurable. Progress output does not alter JSON artifacts, confidence, fallback behavior, or runtime evaluation integrity.

---

## D-022 — Publish stable delivery evidence and uniform review markers

- Status: accepted
- Date: 2026-10-15
- Decision: retain timestamped development artefacts under `work/`, while publishing the latest result, manifest, event log, evaluation reports, and a requirement-evidence index under stable `outputs/` paths. Add explicit summary-table columns and uniform `review_required` plus `quality_flags` fields at table, row, cell, and relation levels in the final result.
- Rationale: a submission must not refer to ignored or machine-specific history paths, and a reviewer should be able to find both mandatory evidence and low-confidence records without reverse-engineering several stage-specific warning conventions. The common flags are derived from configured thresholds and existing evidence; they do not overwrite raw extraction or model predictions.
- Consequence: `outputs/result.json` refers to `outputs/run_manifest.json`; the manifest refers to `outputs/run_events.jsonl`; `outputs/delivery_index.json` maps case requirements to concrete files and JSON locations.

---

## D-023 — Publish stable note identifiers and separate raw OCR from semantic normalization

- Status: accepted
- Date: 2026-10-15
- Decision: emit stable `row_id` and `column_id` fields directly on disclosure-note records and treat those emitted IDs as authoritative in matching and validation. Preserve every column header's `raw_text`, while allowing a separate `normalized_text` to exclude only low-confidence repeated-character line artifacts from semantic context.
- Rationale: relation outputs must be directly dereferenceable by external consumers, and OCR provenance must not be overwritten merely to improve model input. A distinct normalized field keeps the transformation attributable and testable.
- Consequence: cells point to emitted column IDs, relations point to emitted row IDs, raw header evidence remains available, semantic contexts use the normalized header, and every removal produces an explicit warning.

---

## D-024 — Require one-use, period-aware numeric evidence and expand multi-note references

- Status: accepted
- Date: 2026-10-15
- Decision: consume each disclosure-note cell at most once while calculating a candidate's reporting-period coverage, prefer period-aligned column headers for duplicate values, and emit an independent relation for every configured note number found in a multi-reference summary cell.
- Rationale: one physical cell cannot prove two period balances, and a compound note reference must not make an otherwise valid summary row disappear.
- Consequence: numeric coverage remains exact and attributable; zero/one/many row selection is preserved independently for each referenced target note.

---

## D-025 — Promote unlabeled note totals only with reconciliation evidence

- Status: accepted
- Date: 2026-10-15
- Decision: initialize unlabeled disclosure-note rows as unresolved and promote them to totals only when their period values exactly reconcile with preceding rows. Derive the table numeric region from observed column anchors after a broad candidate scan rather than relying on a fixed right-side page ratio.
- Rationale: table position alone is insufficient evidence for financial role, while one fixed page boundary is brittle across layouts.
- Consequence: inferred totals carry `classification_basis: financial_reconciliation` and contributor row IDs; unresolved rows remain explicit, and left-shifted numeric columns can still be extracted.

---

## D-026 — Align numeric status contracts and make failure semantics conservative

- Status: accepted
- Date: 2026-10-15
- Decision: share explicit percentage statuses between extraction and validation, require bounded percentage evidence, assign zero method-agreement evidence when both matchers abstain, add balance-sheet equality validation, and make standalone validation failures return a non-zero process status.
- Rationale: producer/consumer schema drift and optimistic empty-set scoring can create false confidence; automation must also be able to distinguish a failed validation from success.
- Consequence: damaged percentage OCR is preserved as invalid rather than repaired from expectations, confidence better reflects evidence absence, balance integrity is visible per period, and CI/shell callers receive actionable failure status.

---

## D-027 — Enforce the selected embedding revision at model load time

- Status: accepted
- Date: 2026-10-15
- Decision: keep both the semantic model identifier and its exact Hugging Face revision in runtime configuration, require a non-empty revision for custom models, and pass the configured revision through FastEmbed to the snapshot download layer.
- Rationale: recording the revision after inference proves what was cached on one machine but does not prevent a clean environment from downloading a later repository state. Runtime enforcement is required for reproducible inference.
- Consequence: clean and cached runs resolve the selected MiniLM model at `faf4aa4225822f3bc6376869cb1164e8e3feedd0`; the requested and resolved revision remain visible in model metadata and the run manifest.
