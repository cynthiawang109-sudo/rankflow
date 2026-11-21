# RankFlow operations runbooks

The Operator Console exposes the alert catalogue at `/operator/metrics` and renders its linked runbook at `/operator/runbook`. Use a viewer bearer to read the Console and an operator bearer to apply traffic changes. Keep bearer values out of URLs, command history, and recorded evidence.

## Canary telemetry unknown

Read the active config and telemetry windows from the Console. Check the per-generation, cohort, and source counts against the minimum sample requirement. Confirm the auto-pause revision and verify that the stable generation serves through the load balancer. If the pause failed, use the pause failure procedure.

## Canary fallback

Confirm that the alert identifies the canary generation, cohort, and source. Check fallback counts and representative request IDs against scorer and decision logs. Verify that the pause is acknowledged across the serving fleet and that stable recommendations persist.

## Stale fleet

Read the current revision, expected instances, and named rollback target from `/operator/status`. Submit the named target to `POST /operator/traffic/rollback` with the current `expected_revision` and a unique `operation_id`. Sample readiness through the load balancer and verify that every eligible instance acknowledges the rollback. Record the observed convergence state and the affected request IDs. If rollback convergence fails, inspect the designated rescue config and the release freeze before resuming release activity.

## Pause failed

Page the release operator. Check the control database, current revision, and signed audit for a revision race or a database error. If foreground service is impaired, use the named rollback or stable kill switch and verify the resulting revision from the load balancer.

## Logging degraded

Page the database operator. Compare impressions served and persisted within the affected generation, cohort, and source. Check database health and commit timing. Verify that post-recovery recommendations produce usable impression IDs and document the degraded interval and any unattributable feedback.

## Outbox retry

Page the operator responsible for delivery. Inspect pending records, oldest age, and worker errors. Restore connectivity and verify idempotent redelivery against the durable sink. Record any unrecoverable events separately if storage was lost and restored from backup.

## Incident evidence

Record the initial config and generation, alert and action timestamps, affected denominator, operation ID, final config and acknowledged revisions, and the verification probe. The Stage 3 fault drills use an isolated schema and explicitly labeled fixtures. See [fault evidence](stage3_fault_evidence.md) and [local restore evidence](stage3_restore_evidence.md).

## Restore from backup

Record the source DB, selected backup timestamp, known-good config revision,
epoch IDs, and event and delivery counts. Restore the snapshot to a separate
private RDS instance in the reference VPC. Retain access to the generation
bundles, routing salts and database credentials. Point a new ECS deployment at
the restored endpoint and wait for ALB health and release readiness from each
leased instance. Check the restored pointer and epoch, then issue a stable
recommendation through the ALB and verify a persisted impression. Compare the
restored and pre-failure counts before the verification write. Record RPO, RTO
and the identified loss. See the [RDS drill](stage4_exit_evidence.md) and
[deployment procedure](stage4_deployment.md).
