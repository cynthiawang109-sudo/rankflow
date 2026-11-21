# RankFlow — Codex Kickoff: Stage 4 (Product Complete)

**Repository:** `C:\PROJECTS\rankflow` (work only inside this repo; commit after every package)
**Governing documents:** `SPEC.md` (v3.0, FROZEN — read §12 Stage 4 exit definition and §9.3 latency targets first) and `ADDENDUM.md` (v3.0.4 implementation baseline). Stage evidence so far: `docs/stage1_exit_evidence.md`, `docs/stage2_exit_evidence.md`, `docs/stage3_exit_evidence.md`.

**Mission (owner's words):** Stage 4 answers the last question — can this system meet explicit performance, reliability, and quality standards in a real cloud deployment, and stand as a complete product another engineer can reproduce? Stage 3 is accepted with ONE open item carried into this stage: the SPEC §9.3 latency targets were missed on the local Windows host (client p95 145/270/144 ms vs the 100 ms target, while retrieval/feature/scoring segments were ~1 ms). That item gets its FINAL determination on the reference deployment here — reported as measured, never tuned into compliance.

**Language:** All code, comments, docs, and commit messages in English.

## Standing rules (carry over from Stages 1–3)

- Final acceptance runs must execute the full test suite with `RANKFLOW_TEST_DATABASE_URL` set against a real PostgreSQL; report passed / failed / skipped counts explicitly. Skipped DB tests count as incomplete.
- Never fabricate metrics, timings, or drill outcomes; every number comes from a recorded run, probe, or cloud bill.
- The Stage 2 W2-gate decision stands: rule-v1 is the stable serving strategy; lgbm-v1 stays rejected. No gate re-runs, no new model candidates in this stage.
- W3 discipline (R15): W3 has stayed sealed through Stages 0–3. It is unsealed exactly ONCE in this stage, for the final report (package 4.4). No tuning, threshold change, or strategy change may follow from seeing W3 results.
- Demo data stays quarantined; nothing in this stage trains on demo or W3 data.

## Package 4.1 — Reference deployment (AWS, CDK)

Deploy the reference architecture per SPEC R19: AWS Fargate in **ca-central-1** via CDK — ALB in front of ≥2 API tasks, managed PostgreSQL (RDS), artifact distribution per R29, roles/permissions per the R19 matrix (public / viewer / operator / admin enforced as in Stage 3).

- Reuse the AWS account and CLI configuration already present on this machine (used for the SyncBridge CDK deployment). If credentials or permissions are missing, STOP, write what is missing into the result file, and end — do not improvise alternate clouds or regions.
- Tag every resource (`project=rankflow`, `stage=stage4`). Record the stack outputs (ALB DNS, task counts, RDS endpoint identifier — no secrets) in `docs/stage4_deployment.md`.
- Verify through the ALB (not direct task access): health/readiness signals, stable generation serving, one named config publication converging across tasks behind the real load balancer — this closes the Stage 2/3 open item "external load-balancer config propagation timing unverified". Measure and record that convergence time.

## Package 4.2 — Latency verdict on the reference deployment

Re-run the Stage 3 benchmark protocol (same modes: stable / peak / synthetic shadow / canary fixture; same request counts and concurrency) against the ALB endpoint.

- Report client p95/p99 and the retrieval / feature / scoring segment timings per mode, plus task CPU/memory headroom, in `docs/stage4_latency_verdict.md`.
- Give the SPEC §9.3 targets their final determination: met or missed, per mode, with the segment evidence. If missed, the verdict says so plainly and analyses which segment is responsible on this deployment. No benchmark-protocol changes designed to flatter the numbers; any necessary protocol adaptation (e.g., client location) is documented with its effect stated.

## Package 4.3 — Reliability re-check on the deployment

Repeat the key Stage 3 drills against the deployed system, briefly: kill one API task mid-traffic (ALB drains, no user-visible errors beyond recorded fallbacks), publish + named rollback behind the ALB, and restore the database from backup once (RDS snapshot) with the restored system serving the stable generation. Record expected vs observed in the exit evidence.

## Package 4.4 — W3 final report (single unsealing)

- Evaluate the SERVING stable strategy (rule-v1) and, for the record only, lgbm-v1 on W3 with the frozen evaluation protocol and label policy `nextclick-v1`. Report HitRate@20 / MRR@20 and `candidate_recall@100` per the R28 definitions, alongside the W1 / W2-dev / W2-gate numbers from earlier stages for the full picture.
- Write `docs/final_evaluation_report.md`. This is a report, not a decision point: no promotion, no tuning, no follow-up experiments based on W3. State that explicitly in the report.

## Package 4.5 — Reproducibility and product completeness pack

- Clean-room reproduction: from the repository docs alone, in a clean environment (fresh container/venv, empty database), reproduce (a) the training pipeline run and its model checksum comparison against the Stage 2 lineage record, (b) the evaluation on W2-dev, and (c) a local deployment serving the stable generation. Record every doc gap or ambiguity encountered and fix the docs, in `docs/reproduction_log.md`.
- Finalise the product documentation set: README (what it is, how to run, how to deploy, how to operate), the product contract (final version of the Stage 0 draft), runbooks linked from the alert catalogue, and an evidence index tying every SPEC §12 Stage 4 exit criterion to its evidence file.
- Assign the remaining acceptance tests from ADDENDUM.md not yet evidenced in Stages 1–3 (verify against the catalogue; expected to include the end-to-end reproducibility and final-report scenarios) and record where each is evidenced.

## Package 4.6 — Teardown and cost record

- After 4.1–4.5 evidence is captured, tear down the CDK stack and verify no billable resources remain (list what was checked). Record the actual AWS cost of the stage from the billing/console data available, in `docs/stage4_deployment.md`. If cost data is not yet available at teardown time, record the resource-hours consumed instead and say so.
- Local wrap-up: full test suite final run (with the standing DB rule), `docs/stage4_exit_evidence.md`, and the result summary in `codex_stage4_result.txt` in the repo root, stating passed / failed / skipped counts explicitly and the latency verdict in one line.

## Hard constraints

Frozen SPEC scope stands; no Kafka/Kubernetes/MLflow/LLM scoring; no new features beyond what the exit criteria require. Cloud spend stays minimal: deploy, verify, tear down in one working session where possible; never leave the stack running unattended between packages.
