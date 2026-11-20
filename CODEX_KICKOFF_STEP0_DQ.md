# RankFlow — Codex Kickoff: Step 0 Data-Quality Sign-Off Report (only)

**Repository:** `C:\PROJECTS\rankflow` (Stage 0 complete; real OTTO run recorded in `docs/data_validation_report_real.md` + `.json`; raw data in `data/otto`, run artifacts in `artifacts/`)
**Governing documents:** `SPEC.md` (v3.0, FROZEN), `ADDENDUM.md` (v3.0.4).
**Task scope:** Produce ONE deliverable — the Stage 0 data-quality sign-off report. Do NOT start Stage 1 work. Do NOT modify Stage 0 data, manifests, windows, configs, or existing code behaviour; if you need a small read-only analysis script, add it under `tools/` and commit it with the report.

**Language:** All code, comments, docs, and commit messages in English.

## Background numbers (from the verified real run — your report must be consistent with these)

- 200,000 sessions sampled (cap 200,000, seed `rankflow-stage0-sample-v1`); 108,214 assigned to windows; 91,786 excluded for crossing at least one window boundary; 0 outside all windows.
- 409,839 queries; co-visitation table 1,332,494 rows.
- Per-partition labeled-query retrieval (prefix co-visitation only): W1 retrieved 11,947 / unretrieved 94,702; W2-dev 5,591 / 49,185; W2-gate 5,485 / 48,232; W3 11,048 / 110,411.

## Deliverable: `docs/stage0_data_quality_report.md` (+ `.json` evidence)

1. **Kept vs excluded comparison** over the 200,000-session sample:
   - Event-count distribution (mean/median/percentiles) for kept vs boundary-excluded sessions.
   - Session duration distribution (first-to-last event span) for both groups.
   - Long-session share in each group (use the existing short/long split: short = at most 20 events; also report the share above 100 events).
2. **Behavior mix:** click/cart/order event proportions and repeat-item frequency (share of events whose aid already appeared earlier in the same session), kept vs excluded.
3. **Per-window sufficiency table:** for W1, W2-dev, W2-gate, W3 — retained sessions, events, eligible prefixes, labeled next-click queries, no-label queries, all-negative queries (labeled but positive not retrieved by the Stage 0 single source). W3 figures must come only from the existing governed pipeline outputs (the real-run report/JSON and artifacts); do NOT open or inspect W3 labels beyond those aggregates.
4. **Metric pinning:** state the exact definition behind the "~11%" figure (denominator = labeled queries in the partition; candidates = prefix co-visitation source only; state the candidate cap and retrieval snapshot/config it used) and restate it as `candidate_recall@C` per Addendum R28, per partition, so Stage 1 experiments compare like with like.
5. **Disposition:** conclude with one of — *approve Stage 0* / *proceed to Stage 1 with a registered follow-up data-quality investigation* / *block downstream evaluation* — justified strictly by the measured numbers and the frozen rules. Do not invent universal thresholds. If you register a follow-up investigation, state precisely what it would measure and why.
6. Reuse the existing artifacts where possible. If a needed aggregate is not in the existing artifacts, you may recompute it by streaming `data/otto/train.jsonl` with the existing Stage 0 modules (read-only); record in the report which figures were recomputed and how long it took. Do not write new artifacts into `artifacts/` root without recording them; never commit raw data or artifacts.

## Finish

- Run the full unit test suite; all tests must pass.
- Commit the report (+ JSON, + any analysis script) as one small commit.
- Write a concise summary of the report's key numbers and the disposition to `codex_step0dq_result.txt` in the repo root.
