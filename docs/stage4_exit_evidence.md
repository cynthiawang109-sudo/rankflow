# Stage 4 exit evidence

The reference deployment ran in AWS `ca-central-1`. The continuation reused
the original image digest, stable bundle, stack name, and tags. The stable
strategy is `rule-v1`. The signed Stage 2 rejection of `lgbm-v1` stands.
[Deployment record](stage4_deployment.md) · [Release decision](stage2_release_decision.md)

## 4.3 Reference reliability

All application requests went through the HTTPS ALB. ECS and ELB control
plane queries identified the targets and their health states. The traffic
fixture used synthetic requests and the historical W2-dev prefixes.

| Drill | Expected | Observed |
| --- | --- | --- |
| Re-deployment | Two healthy tasks serve the original stable generation through the ALB. | ECS had two running tasks and zero pending. Both instances reported revision 0 through the ALB and a public recommendation persisted on `rule-v1`. |
| First named shadow publish | Both active tasks converge on revision 1. | The audit recorded `partially_converged`. The capacity rule committed automatic rollback `capacity-1` at revision 2, which converged. The 90-second client window did not capture either instance on revision 1. |
| Named shadow retry | After both instances preload the fixture, the fleet converges on the named publication. | Both tasks reported revision 3 and the requested config. The latest first sighting was 2.269 seconds after the retry request began. |
| Named rollback | The named stable config is restored and both instances acknowledge it. | The audit recorded `stage4-named-rollback` at revision 4 as `converged`. The original 90-second client window sampled one task on revision 4. Follow-up readiness sampled both tasks at the stable config. The full client convergence interval could not be measured from the original request. |
| Initial task stop | A stop request made during traffic preserves successful recommendations while ECS replaces the task. | All 200 requests returned HTTP 200 with persisted `rule-v1` results and zero fallbacks. ECS recorded target deregistration and draining 35.801 seconds after the stop request, after the burst ended. A later sample showed two healthy targets and a new instance ID. |
| Task drain confirmation | Traffic overlaps actual target draining and deregistration, followed by replacement. | The follow-up stopped one task in the restored fleet and kept traffic active until ELB removed the target. ELB first reported `draining` at 12:56:25.275 UTC and the target was absent at 12:56:40.237 UTC. All 112 requests returned HTTP 200 with persisted `rule-v1` results and zero fallbacks. The replacement fleet had two healthy targets. |
| RDS snapshot restore | Restore the stable pointer, configuration and epoch, account for post-backup losses, and persist a stable answer through the ALB. | One manual snapshot, `rankflow-stage4-drill`, was restored as `rankflow-stage4-restored`. Both replacement tasks reported revision 4. The configuration, traffic history, epoch and checkpoint event counts matched. The ALB returned the original stable generation with a persisted impression. One post-snapshot decision and its pending outbox event were unrecoverable. |

Readiness observations use the client boundary and include TLS and ALB
target selection. The follow-up rollback observation used consecutive
readiness connections before querying the fleet. Its timing starts at the
follow-up probe.

The RDS checkpoint contained 202 decisions and 202 delivered outbox events,
with zero events pending. After the snapshot, one more decision and its outbox
event committed to the source. The restored store returned to the checkpoint
counts. The new recommendation persisted as impression
`2931331c-ce0b-4504-87f2-4c1292d08542`. This RDS snapshot held an already
drained outbox. The separate local recovery drills cover redelivery from
surviving storage. [Stage 3 fault evidence](stage3_fault_evidence.md)

The drill RPO was **164.400 seconds** from the recorded manual snapshot time
to restore initiation. RTO was **608.108 seconds** from restore initiation
through the ECS endpoint switch, both ALB readiness observations, and a
persisted stable recommendation. These manual-snapshot measurements were
within R29's 24-hour and 4-hour targets.
[Recorded cloud probes and snapshot checks](stage4_reliability_evidence.json)
