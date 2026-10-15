# Error and Resolution Log

This file permanently records engineering failures observed on the real document and during testing. Each entry includes the symptom, root cause, resolution, and evidence that prevents the same failure from returning.

## E001 — `pdftoppm` was not available on PATH

- **Stage:** PDF page rendering
- **Symptom:** `RuntimeError: pdftoppm is required but was not found on PATH`
- **Root cause:** Poppler was not installed or was not accessible through the terminal PATH.
- **Resolution:** Install it on macOS with `brew install poppler`, then verify it with `which pdftoppm`.
- **Regression evidence:** The dependency and verification command are retained in `RUNBOOK.local.md`. This is an external runtime dependency failure, not an OCR/model failure.

## E002 — PSM 6 read note reference `11` as `1]`

- **Stage:** Summary-page OCR configuration
- **Symptom:** The critical note reference on PDF page 5 was read as `1]` instead of `11`.
- **Root cause:** PSM 6 assumes a single uniform text block and grouped characters incorrectly in the multi-column financial-table layout.
- **Resolution:** PSM 3, 4, 6, and 11 were compared on the same images and expectations; PSM 3 produced the best critical-field result on this document.
- **Regression evidence:** `scripts/psm_comparison.py` and `evaluation/psm_expectations.json` make the comparison reproducible.

## E003 — The configured OCR engine was not actually enforced

- **Stage:** OCR infrastructure
- **Symptom:** Changing `ocr.engine` could leave runtime behavior unchanged, and an empty token result could appear successful.
- **Root cause:** Engine selection and configuration validation were not fully connected to the runtime pipeline.
- **Resolution:** Engine selection is now driven by configuration; unsupported engines are rejected and empty OCR output raises an explicit error.
- **Regression evidence:** Configuration and empty-result tests were added, and the actual engine name is recorded in run output.

## E004 — Stale rendered files changed the selected page set

- **Stage:** Summary OCR
- **Symptom:** Images from earlier runs under `work/rendered/summary/` could be included in a new run.
- **Root cause:** The entire directory was read instead of filtering strictly to pages selected by the current configuration.
- **Resolution:** The pipeline now accepts only rendered images whose page numbers are present in the active configuration.
- **Regression evidence:** A test confirms that an extra stale file is ignored.

## E005 — The note-column boundary was too narrow in a synthetic table

- **Stage:** Summary-table structuring
- **Symptom:** A note-reference token was not assigned to the correct column in a narrow-layout test.
- **Root cause:** A fixed threshold based on the token's left edge misinterpreted a bounding box that crossed the column boundary.
- **Resolution:** Column membership is calculated from the token center coordinate.
- **Regression evidence:** The note-token column-assignment test is retained.

## E006 — Decimal-comma financial values were treated as invalid

- **Stage:** Summary-table structuring
- **Symptom:** The `Hisse başına kazanç` row containing `0,058` and `1,191` disappeared and its values were attached to the wrong row.
- **Root cause:** The numeric parser treated commas only as thousands separators.
- **Resolution:** The parser now recognizes decimal-comma notation, and row assignment was revalidated.
- **Regression evidence:** Decimal-comma examples are fixed in unit tests.

## E007 — Greedy row-label matching attached labels to the wrong rows

- **Stage:** Summary-table structuring
- **Symptom:** Some labels were attached backward to the wrong value row, and section headers were unintentionally merged with child rows.
- **Root cause:** Row-by-row greedy matching did not preserve the global ordering of nearby rows.
- **Resolution:** Direct matches are selected globally, with indentation-aware continuation-line merging.
- **Regression evidence:** Critical real-page rows and synthetic layouts are covered by tests.

## E008 — Two repeated total rows had no reliable OCR label

- **Stage:** Summary-table structuring
- **Expected result:** The two distribution-total rows on PDF page 7 should retain their period values and a defensible structural role.
- **Actual result:** Period values and coordinates were retained, but both labels remained `null` and produced `missing_row_label` flags.
- **Symptom:** The two total rows have values but no reliable text label.
- **Root cause:** The source image/OCR output did not provide sufficient label evidence, and repeated values make deterministic naming unsafe.
- **Resolution:** The system does not invent labels. It retains the rows with warnings and reports `completed_with_warnings`; their total role is inferred only through exact two-period reconciliation.
- **Improvement:** Measure PaddleOCR/PP-StructureV3 or a named second OCR fallback on the same fixed page. Enable it only if label recovery improves materially without an unacceptable false-positive increase.
- **Regression evidence:** Tests confirm that values survive when the label is missing and that the review flag is emitted.
- **Status:** Known limitation; revisit only with measured OCR/layout evidence.

## E009 — A simple note regex treated dates as heading candidates

- **Stage:** Document-wide note location
- **Symptom:** The initial rule based on numbers at the start of a line produced many false candidates from dates and table values.
- **Root cause:** “Line starts with a number” is insufficient to identify a disclosure-note heading.
- **Resolution:** Candidates are constrained by note number, uppercase-heavy heading form, line position, and textual evidence.
- **Regression evidence:** The real 95-page document is scanned without injecting the target page.

## E010 — A table row on page 89 was mistaken for note heading 11

- **Stage:** Document-wide note location
- **Symptom:** The financial-table row `11. UZUN VADELİ YÜKÜMLÜLÜKLER ...` was returned as an additional target-note page.
- **Root cause:** Exact number matching was treated as sufficient evidence; financial fragments and topic mismatch with the real heading were not penalized enough.
- **Resolution:** Heading candidates containing two or more financial-value fragments are rejected. Candidates with the same number are clustered by normalized title similarity, excluding topic-inconsistent rows.
- **Regression evidence:** `test_same_number_in_unrelated_table_row_is_not_added` was added. Page 89 is absent after rerunning the real document.

## E011 — OCR read the first-page note number `11` as `1`

- **Stage:** Document-wide note location
- **Symptom:** The true note on PDF page 53 appeared to start with `1.`; exact-number-only logic would have lost the first page.
- **Root cause:** Low-resolution full-document OCR dropped one digit of the two-digit note number.
- **Resolution:** The exact `11 ... (devamı)` heading on page 54 is used as an anchor. The preceding page is recovered only when normalized title similarity and page continuity are strong.
- **Regression evidence:** A test covers the missing-digit first page. The real result is pages 53–54 with confidence `0.956727`.

## E012 — A date header in the rate table was interpreted as a data row

- **Stage:** Note-table structuring
- **Symptom:** The two `31` tokens from `31 Aralık 2012 / 31 Aralık 2011` on page 54 became a separate data row.
- **Root cause:** Two numeric tokens on the same right-side line were sufficient to form a data-row candidate.
- **Resolution:** A repeated day-number row followed by aligned year headers is classified as a period header and excluded from data rows.
- **Regression evidence:** A synthetic test confirms that two `31` tokens with different years beneath them are not emitted as data.

## E013 — A multiline opening label was mixed into column headers

- **Stage:** Note-table structuring
- **Symptom:** The first line of `1 Ocak 2011 ... (Yeniden Düzenlenmiş)` disappeared, while `(Yeniden` entered the first column header.
- **Root cause:** The header search window was too close to the first data row and did not treat left-side lines containing numbers as label continuations.
- **Resolution:** Adjacent lines fully inside the label region are removed from the header pool and appended to the row label. Headers use trailing vertically connected right-side lines.
- **Regression evidence:** A synthetic multiline label containing a year is reconstructed fully; the real headers are again `Arazi ve Arsalar / Binalar / Toplam`.

## E014 — OCR-damaged cells remain in disclosure-note tables

- **Stage:** Note-table structuring
- **Expected result:** Parenthesized values, percentages, thousands separators, and dashes should be assigned and parsed under the document locale.
- **Actual result:** Five cells remain invalid raw values, one cell is missing, and one dash is retained as an extra token; the minimum table parse rate is `0.5`.
- **Symptom:** PSM 3 produced `(205.034.968`, `196262.178`, `“49`, `410,5`, and `42-44`, and could not assign one 2011 dash reliably.
- **Root cause:** Table rules, percent signs, parentheses, and thousands separators were confused with characters or noise by Tesseract.
- **Resolution:** Raw OCR and coordinates are preserved. Invalid values are not normalized, missing cells remain blank, and `invalid_note_value`, `missing_data_cell`, or `extra_numeric_token` warnings are emitted.
- **Improvement:** Evaluate a cell-cropped OCR pass or measured alternative OCR engine. Corrections must come from image evidence, never known financial answers.
- **Regression evidence:** The stage reports `completed_with_warnings` and per-table parse/assignment rates. PSM 11 improved some cells observationally but is not a silent fallback.
- **Phase 4 result:** Output contains 4 tables and 19 rows, eight row/cell warnings, and one `column_header_ocr_noise_removed` warning.
- **Status:** Known limitation; matching uses raw, normalized, and warning evidence together.
- **Phase 6 impact:** Three reconciliations in the 2011 movement table are `incomplete`; five other applicable total checks reconcile exactly.
- **Relation impact:** The balance-sheet item selects the unlabeled page-54 total that covers both periods. Alternatives with the same balances make it `ambiguous: true`, `review_required: true`, and `ambiguous_numeric_alternatives`, with final confidence `0.856148`. No `Toplam` label is injected.

## E015 — An inflected Turkish transaction term was treated like a total row

- **Stage:** Baseline relation matching
- **Symptom:** `farkları` did not exactly match the transaction/detail signal `fark`, leaving structural compatibility at `0.5`.
- **Root cause:** Structural-term matching used exact token intersection without Turkish inflection.
- **Resolution:** Prefix matching is applied to a small, explainable set of transaction terms. `farkları` now carries the `fark` signal without changing other evidence.
- **Regression evidence:** The regenerated baseline selects the correct row sets; Top-1, Recall@5, and MRR are `1.0` on two examples and explicitly exploratory.

## E016 — Semantic similarity promoted a row with no numeric evidence

- **Stage:** Multilingual embedding relation matching
- **Expected result:** A candidate that does not explain period values must not be selected solely because of topic similarity.
- **Actual result:** `Bağcılar Arsa` rose to third place in the semantic Top-5 but was not selected.
- **Symptom:** The correct 2012 and 2011 gain rows remained first and second, while a numerically unsupported row moved upward.
- **Root cause:** Cosine similarity captures topical proximity but cannot prove that a period value is explained.
- **Resolution:** Semantic score is not selection evidence by itself. Exact period-value coverage remains a separate 50% feature, and selection requires a previously unexplained period value.
- **Improvement:** Compare embeddings/rerankers on a broader labeled report set while retaining numeric coverage as mandatory evidence.
- **Regression evidence:** Example-level Top-5 changes are retained; both methods select the correct sets and unsupported candidates cannot enter them.
- **Status:** Expected model limitation.

## E017 — Section membership continued too far after an unlabeled row

- **Stage:** Summary-table parent/child extraction
- **Expected result:** `Dönem Karı Dağılımı` should contain only its distribution rows; later earnings-per-share and comprehensive-income rows should not be children.
- **Actual result:** The first implementation placed four later rows under that section.
- **Root cause:** Membership continued until the next explicit section header, with no reliable section-end boundary.
- **Resolution:** An unlabeled financial row closes the active section and indentation stack; later rows receive no invented parent.
- **Improvement:** Measure horizontal rules, vertical gaps, and typography on other reports before adding new boundary evidence.
- **Regression evidence:** A synthetic test verifies the boundary. Real page 7 no longer places `Hisse başına kazanç` under the wrong section.

## E018 — The alternative Potion model preferred percentage rows semantically

- **Stage:** Embedding model comparison
- **Expected result:** Raw semantic similarity should separate correct gain rows from unrelated assumption/percentage rows.
- **Actual result:** Under Potion, correct rows scored `0.440519`, while `İskonto oranı`, `Doluluk oranı`, and `Kira artış oranı` scored about `0.545–0.559`. Hybrid ranking still selected correctly.
- **Root cause:** Valuation terminology and topic proximity do not prove that a row represents the same financial movement.
- **Resolution:** Cosine similarity remains a 25% feature; exact period-value coverage is mandatory. Potion was not selected as default.
- **Improvement:** Test a financial reranker only on a broader labeled set and only if Top-1 or correct Top-k improves.
- **Regression evidence:** The benchmark retains all 38 candidates and Top-5 rankings; unrelated percentage rows are not selected.

## E019 — The installed `ykt-case` command could not resolve the editable `.pth`

- **Stage:** Clean installation and CLI smoke test
- **Expected result:** `.venv/bin/ykt-case --help` should run after installing `requirements.txt` without `PYTHONPATH`.
- **Actual result:** It failed with `ModuleNotFoundError`, while `PYTHONPATH=src python -m ykt_case.cli` worked.
- **Root cause:** The editable `.pth` carried a macOS `hidden` flag, so Python site initialization did not add the source path.
- **Resolution:** `requirements.txt` changed from editable `-e .` to normal local wheel installation `.`.
- **Regression evidence:** CLI help, config smoke test, direct import, `pip check`, and all 64 tests pass without `PYTHONPATH`.
- **Status:** Resolved.

## E020 — Relation IDs were not published on note row and column records

- **Stage:** Note-table structuring and referential integrity
- **Expected result:** Every selected row ID must resolve directly to an emitted `row_id`; columns must carry stable `column_id` values.
- **Actual result:** Matching reconstructed IDs from indexes, but note objects did not publish them, so external consumers could not resolve `row["row_id"]`.
- **Root cause:** The later relation-ID contract was not propagated into the initial positional note schema.
- **Resolution:** Note rows, columns, and cells now publish and reference stable IDs. Index reconstruction remains only for backward compatibility.
- **Regression evidence:** Tests cover IDs, cell-column links, and propagation of custom published row IDs. Final relation references all resolve.
- **Status:** Resolved.

## E021 — Unlabeled distribution totals became children of the previous detail row

- **Stage:** Summary-table hierarchy and aggregation
- **Expected result:** Page-7 rows `10.718.956 / 161.914.251` and `(9.127.909) / 358.206.634` should sum their preceding ownership rows.
- **Actual result:** They remained `detail` and became children of `Ana Ortaklık Payları`.
- **Root cause:** The unlabeled boundary was applied after parent assignment, and total classification depended on text.
- **Resolution:** An unlabeled row becomes `total` only after exact reconciliation in every period. It remains parentless and lists contributors in `aggregation_of_row_ids`.
- **Regression evidence:** A unit test covers exact aggregation. Final rows 21 and 29 are parentless, `financial_reconciliation`-backed, and `reconciled`.
- **Status:** Resolved.

## E022 — Multiline financial-table titles were truncated

- **Stage:** Summary-table title extraction
- **Expected result:** The full title should include date/audit scope and table type.
- **Actual result:** Only the line containing `KONSOLİDE` was retained; the preceding audit/date line was lost.
- **Root cause:** Selection stopped at the first `KONSOLİDE` line and did not join adjacent title text.
- **Resolution:** A nearby preceding audit/date line is joined dynamically; no expected title is injected.
- **Regression evidence:** A synthetic test and final output confirm complete titles on pages 5–7.
- **Status:** Resolved.

## E023 — Low-confidence rule noise entered semantic column context

- **Stage:** Note header extraction and semantic input
- **Expected result:** Raw OCR must remain intact, but proven noise should not contaminate model context.
- **Actual result:** A header became `31 Aralık 2012 Gerçeğe Uygun Ooo Değeri`, and `Ooo` entered embedding context.
- **Root cause:** A horizontal rule was read as repeated-character noise with confidence `0.4718655`; one field served raw and semantic use.
- **Resolution:** Raw text remains unchanged. Evidence-backed repeated low-confidence tokens are removed only from `normalized_text`, which semantic context uses. The transformation emits a warning.
- **Regression evidence:** Tests confirm raw preservation and normalized removal. Final output contains both forms and `column_header_ocr_noise_removed`.
- **Status:** Resolved.

## E024 — Percentage-range producer and validator schemas disagreed

- **Stage:** Note-value parsing and format validation
- **Symptom:** The extractor emitted a range status absent from the shared contract, and percentage evidence was searched only in row labels.
- **Root cause:** Enum, context construction, and validation were not updated together when percentage parsing was separated.
- **Resolution:** `percentage` and `percentage_range` are shared statuses. Cell, row-label, and column-header context is used; values must stay within `[0, 100]`. `42-44` and `410,5` are not guessed valid.
- **Regression evidence:** Tests cover valid/invalid ranges, blanks, bounds, and unsigned OCR damage. Final format validation has no violation.
- **Status:** Resolved.

## E025 — One note cell could satisfy two reporting periods

- **Stage:** Baseline and semantic candidate features
- **Symptom:** One note cell could cover two equal-valued summary periods.
- **Root cause:** Matched cells were not consumed, and period-aligned headers were not preferred.
- **Resolution:** Each note cell is used at most once per candidate; period-aligned columns are preferred for duplicates.
- **Regression evidence:** One note cell now yields `0.5` coverage for two equal periods; two correct cells retain full coverage.
- **Status:** Resolved.

## E026 — Turkish dotless `ı` weakened title and row similarity

- **Stage:** Note location and matching normalization
- **Symptom:** Text such as `Yatırım` and OCR variants did not normalize to one form.
- **Root cause:** NFKD does not convert dotless `ı` to ASCII `i`.
- **Resolution:** Explicit `ı → i` conversion follows casefolding in locator and matcher normalization.
- **Regression evidence:** Separate title and row tests verify normalized equality.
- **Status:** Resolved.

## E027 — A short continuation heading could fail the uppercase filter

- **Stage:** Document-wide note location
- **Symptom:** `(devamı)` could dominate a short heading and lower its uppercase ratio artificially.
- **Root cause:** The continuation marker was included in heading-form evidence.
- **Resolution:** Uppercase evidence is measured after removing `(devamı)`.
- **Regression evidence:** A synthetic test keeps a short valid continuation heading.
- **Status:** Resolved.

## E028 — A row with multiple note references could be skipped silently

- **Stage:** Baseline and semantic relation generation
- **Symptom:** A value such as `11, 12` could not become one integer, so no relation was emitted.
- **Root cause:** The matching layer assumed one `int` per reference cell.
- **Resolution:** All positive numbers are parsed, with separate provenance-bearing relations for configured targets.
- **Regression evidence:** A test confirms that one row referencing two configured notes produces two relations.
- **Status:** Resolved.

## E029 — An unlabeled note row could become a total without evidence, and a fixed cutoff could miss columns

- **Stage:** Note-table structuring
- **Symptom:** A last unlabeled row could be treated as a total by position, while numeric columns left of the former 46% page boundary could be lost.
- **Root cause:** Row role and numeric region depended too heavily on fixed position.
- **Resolution:** An unlabeled row starts `unresolved` and becomes `total` only after exact all-column reconciliation. Numeric regions are derived from observed anchors after a wider scan.
- **Regression evidence:** Tests cover evidence-backed totals and columns left of the old cutoff. The real page-54 total has four contributors.
- **Status:** Resolved.

## E030 — Empty matches received full agreement, and failed standalone validation exited successfully

- **Stage:** Confidence aggregation and CLI propagation
- **Symptom:** Two empty selected sets could yield agreement `1.0`; failed `--stage validate` could exit `0`.
- **Root cause:** Set equality was not separated from absence of evidence, and CLI completion was not tied to validation status.
- **Resolution:** Two empty selections contribute `0.0` agreement. Failed standalone validation exits non-zero.
- **Regression evidence:** Tests cover empty-selection confidence and failed-validation CLI behavior.
- **Status:** Resolved.

## E031 — The fundamental balance-sheet equation was not checked directly

- **Stage:** Financial validation
- **Symptom:** `Toplam Varlıklar = Toplam Kaynaklar` was not a separate check despite within-table reconciliations.
- **Root cause:** Initial validation focused on note totals and relation value coverage.
- **Resolution:** A period-wise check finds both source totals, records their difference, and returns `incomplete` rather than guessing when evidence is missing.
- **Regression evidence:** A unit test covers the equation. In the latest run, both sides equal `781.408.277` for 2011 and `852.149.804` for 2012, with difference `0`.
- **Status:** Resolved.

## E032 — A thousands separator OCR error was accepted as a decimal without review

- **Stage:** Summary-value normalization
- **Expected result:** Page-5 `Finansal Yatırımlar` for 2012 should represent financial integer `4.224` (`4224`) and remain auditable.
- **Actual result:** OCR emitted `4,224`; the locale parser validly interpreted it as decimal `4.224`, and the cell was not marked for review.
- **Root cause:** Decimal-comma support is required for legitimate values such as earnings per share, but no secondary accounting check distinguished that case from an OCR-swapped thousands separator.
- **Resolution:** Potential comma-plus-three-digit ambiguity is retained with both candidates. The integer candidate is selected only when it is the unique value that restores the exact parent-child total. Raw OCR, parser value, selected value, method, target row and period are all emitted; the cell remains review-required.
- **Regression evidence:** Unit tests cover unique separator resolution and provenance validation. The real page-5 result retains raw `4,224`, parser value `4.224`, selected value `4224`, and method `parent_child_financial_reconciliation`.
- **Status:** Resolved with attributable evidence.

## E033 — Summary total reconciliation failed on prefix, dash and nested structures

- **Stage:** Summary hierarchy and financial validation
- **Expected result:** Exact statement subtotals and totals should list non-overlapping contributors for both periods.
- **Actual result:** Page 5 and 6 had no resolved totals, while three page-7 totals remained unresolved even though manual arithmetic was exact.
- **Root cause:** Reconciliation searched only a contiguous suffix above a total, skipped dash cells instead of treating them as zero contribution, could not use components printed below a prefix subtotal, and could count an aggregate together with its children.
- **Resolution:** The hierarchy now supports direct-child reconciliation, following same-level components for prefix totals, and a preceding non-overlapping frontier. A dash contributes zero only to arithmetic and remains `numeric_status: dash`. Represented child rows are excluded when their reconciled parent is already in the frontier.
- **Regression evidence:** Tests cover all three failure modes. On the real report all 20 emitted summary subtotals/totals reconcile: page 5 `4/4`, page 6 `7/7`, page 7 `9/9`; validation emits `summary_aggregation_reconciliation: passed`.
- **Status:** Resolved.

## E034 — Exact parent reconciliation exposed two additional low-confidence digit errors

- **Stage:** Summary OCR normalization
- **Expected result:** `Stoklar` 2012 and `Dönem Karı Vergi Yükümlülüğü` 2011 should agree with their visible source values and parent totals.
- **Actual result:** OCR produced `71.543.097` and `716.915`; the source values are `77.543.097` and `776.915`.
- **Root cause:** One digit in each cell was misrecognized at low OCR confidence (`0.827459` and `0.815274`).
- **Resolution:** A one-digit alternative may be selected only when the source cell is below the documented confidence ceiling, one and only one cell can explain the residual, and the replacement restores the exact parent sum. Raw OCR and parser values are never overwritten.
- **Regression evidence:** A unit test covers the single-candidate rule. The final validation lists both corrections under `summary_normalization_provenance`; both cells are review-required.
- **Status:** Resolved with attributable evidence.
