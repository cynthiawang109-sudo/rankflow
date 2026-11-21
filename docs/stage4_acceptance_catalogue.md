# Addendum v3.0.4 acceptance evidence

This table follows the Addendum catalogue. Earlier kickoff documents reuse
some IDs for different scenarios. Stage 4 owns the final suite replay and
the scenario gaps recorded below. The independent reproduction and final
report are separate SPEC exit criteria.

| ID | Evidence |
| --- | --- |
| T01 | Stage 2 preserved-replay and epoch overlap test, plus the frozen Stage 1 manifest. |
| T02 | Stage 4 `test_t02_training_window_overlapping_sealed_w3_is_refused` verifies the training entry point refuses a synthetic overlapping interval before loading the snapshot. |
| T03 | Stage 4 `test_promotion_with_paused_instance_and_new_joiner` exercises a fixture promotion with an existing instance paused, a new joiner and an immutable in-flight pin. The Stage 3 HTTP pin drill verifies a response survives pointer movement. |
| T04 | Stage 2 named rollback and failed rollback convergence tests. |
| T05?T06 | Stage 1 PostgreSQL commit/disconnect and returned-top-K attribution tests. |
| T07 | Stage 4 artifact tests reject a bundle with an incompatible feature transform. Stage 2 [full-generation offline replay](stage2_exit_evidence.md) used the compatible feature transform. Isolated replay with a pair of incompatible feature schemas remains unverified. |
| T08 | Stage 4 `test_mixed_demo_rows_rejected_as_unregistered_otto_input` rejects a mixed input against the pinned lineage. The [Stage 2 demo rehearsal](stage2_exit_evidence.md) evidences the separate demo namespace and rejects demo-trained eligibility before any gate reads. |
| T09 | Stage 0 tied-cutoff fixture and Stage 3 same-millisecond delivery. |
| T10 | Stage 3 role and sealed-boundary matrix. The W3 final report and access record cover the separate report opening. |
| T11 | Stage 3 event-store outage and recovery. |
| T12 | Stage 4 `test_inference_hang_during_shadow_saturation` exercises a hung foreground scorer while background work is saturated, observes shadow shedding and persisted rule fallbacks, then reuses the recovered scorer and restores stable routing. |
| T13 | Stage 1 public boundary, Stage 2 operator-only signed release report, and Stage 3 sealed routes. |
| T14 | Stage 4 `test_promotion_with_paused_instance_and_new_joiner` checks `pointer_committed`, `partially_converged`, and `converged` with per-instance state, routing readiness and a pinned in-flight generation. The [Stage 3 release drill](stage3_exit_evidence.md#32-three-instance-release) samples only eligible instances while an unprepared node remains out of routing. |
| T15 | Stage 1 disconnect after commit and acknowledgement lifecycle tests, plus Stage 4 `test_render_then_crash_preserves_unknown_send_and_confirmation` for a process killed after sending the body and before recording send completion. |
| T16 | Stage 3 local backup/restore with verifiable loss count. See the Stage 4 exit evidence for the RDS drill. |
| T17?T18 | Stage 0 epoch validation and exact pair-count fixture. |
| T19 | Stage 4 `test_partial_and_corrupt_artifact_never_activate` compares a working bundle and a second bundle with identical feature names but a distinct transform checksum. The incompatible manifest is rejected before ranker-only activation. |
| T20 | Stage 2 unknown/fallback guardrail tests and Stage 3 exit evidence. |
| T21 | Stage 4 `test_two_instances_sticky_canary_cas_and_kill` exercises a 10% canary, consistent session assignments across two instances, a held in-flight pin during a config update, and stable-only routing on named rollback. Stage 3 covers the HTTP in-flight pin. |
| T22 | Stage 4 `test_control_outage_spanning_config_transition` expires two leased pins over a simulated control outage, observes serving-ready stable rescue and release-unready status, and verifies convergence after recovery. |
| T23 | Stage 4 `test_render_then_crash_preserves_unknown_send_and_confirmation` confirms a rendered decision after the worker dies with `send_unknown`. It checks the confirmation and send denominators after the window closes and verifies duplicate late acknowledgements leave exactly one late record. |
| Stage 4 independent reproducibility | See [reproduction log](reproduction_log.md). The catalogue has no additional T-number for this exit criterion. |
| Stage 4 final report | See [final evaluation report](final_evaluation_report.md). The catalogue has no additional T-number for this exit criterion. |
