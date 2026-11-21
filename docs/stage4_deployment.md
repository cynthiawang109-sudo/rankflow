# Stage 4 AWS reference deployment

The CDK app synthesizes the RankFlow stack for AWS ca-central-1. CloudFormation
creates the base resources before the image, artifacts and HTTPS certificate
are staged. The second deployment configures an HTTPS ALB listener and
an ECS Fargate service with two desired tasks. Both tasks use the private
RDS PostgreSQL instance. See [architecture](architecture.md).

## Original deployment outputs

| Output | Recorded value |
| --- | --- |
| ALB DNS | `RankFl-Alb16-lZtpgmG5nYx3-1565218283.ca-central-1.elb.amazonaws.com` |
| ECS cluster | `RankFlowStage4-ClusterEB0386A7-rDf7qyOpPH6Q` |
| RDS identifier | `rankflowstage4-databaseb269d8bb-hhw8ygodbxht` |
| RDS endpoint | `rankflowstage4-databaseb269d8bb-hhw8ygodbxht.cj2oy2sok398.ca-central-1.rds.amazonaws.com` |
| S3 bundle bucket | `rankflowstage4-bundles3fb864e8-dcb2ouraavns` |
| Image digest | `sha256:7ef3b8886a71102986064d230125c47b47b1afad10a36b63a36771f4308a5382` |
| Stable generation | `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65` |

## Reproduction

Use the documented OTTO stable serving bundle or reproduce it via the README.
Use the configured AWS account, Node.js, AWS CLI, Docker, uv, and OpenSSL.
Run from the repository root. The stage stages a second rule-only generation
whose manifest marks it as the routing fixture.

```powershell
powershell -NoProfile -File infra/stage4_create.ps1
powershell -NoProfile -File infra/stage4_publish.ps1 -OpenSsl <absolute-openssl-path>
```

The base stack took an initial automated RDS backup during provisioning.
The ALB's AWS hostname exceeded the X.509 common-name field limit. The
certificate was created using a short common name and the complete hostname
in the DNS subject alternative name. ALB clients explicitly trust that
short-lived certificate. The ingress rule uses the probe client's IPv4 /32.
The app's bootstrap schema setup runs under PostgreSQL advisory locks.

Resources that support tags are marked `project=rankflow` and `stage=stage4`.
S3 artifact publication uses conditional puts and checksum verification on
each task. The ECS task role has read access to the generation prefixes.
Secrets are generated at deployment and injected from Secrets Manager.

AWS ALB certificate handling follows the [HTTPS listener documentation](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-https-listener.html).

## Original deployment verification

ECS reported desired 2, running 2, pending 0. The service was
`RankFlowStage4-ServiceD69D759B-fPMrAq0zZaeS`. Both API processes completed
startup and were observed serving stable revision 0 through the ALB.
The ALB liveness, readiness, and public ranking probes succeeded. The
role checks exercised public denial on viewer routes, viewer denial
on operator mutations, and operator denial on admin registration.
The admin registered the frozen epoch. Public W2-gate and W3 reads
returned 404 and W2-dev reads succeeded.

The operator published `stage4-named-shadow`, revision 1, config
`cfg-4f5be600b111868bbd94e308d8704c8b2208904882c572ac4f03ec779f71830b`.
The two instance IDs were first observed on the target revision at
0.616281 s and 35.313213 s after the client began the publish request.
The fleet reported converged. The observed convergence upper bound was
35.313213 s. Client scheduling, TLS, target selection, and polling are
included in that observation. Both tasks continued serving `rule-v1`.

The first readiness-only attempt reused HTTP connections and did not
sample both instance IDs within the 90 s observation window. The recorded
run closed each readiness connection to resample ALB routing. Benchmark
requests used the regular shared HTTP client. No direct task API probes
were used.

## Continuation deployment

CloudFormation reported the original stack as `DELETE_COMPLETE` before the
continuation. The continuation recreated `RankFlowStage4` in `ca-central-1`
with the original CDK app and the `project=rankflow` and `stage=stage4` tags.
It pushed the retained original image, whose ECR digest matched the original
record, and staged the same stable generation and synthetic routing fixture.

| Output | Continuation value |
| --- | --- |
| ALB DNS | `RankFl-Alb16-JAWEjQdS9AcH-1068338514.ca-central-1.elb.amazonaws.com` |
| ECS cluster | `RankFlowStage4-ClusterEB0386A7-4VbZyhzigVtG` |
| ECS service | `RankFlowStage4-ServiceD69D759B-DvmsWLup6fLg` |
| RDS identifier | `rankflowstage4-databaseb269d8bb-c8p9fpguzk8d` |
| RDS endpoint | `rankflowstage4-databaseb269d8bb-c8p9fpguzk8d.cj2oy2sok398.ca-central-1.rds.amazonaws.com` |
| S3 bundle bucket | `rankflowstage4-bundles3fb864e8-zdfxhjhb4yry` |
| ECR image digest | `sha256:7ef3b8886a71102986064d230125c47b47b1afad10a36b63a36771f4308a5382` |
| Stable generation | `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65` |

ECS reported desired 2, running 2 and pending 0. The liveness probe passed.
Readiness sampled both serving instances on revision 0 through the HTTPS ALB.
The public recommendation returned HTTP 200, `rule-v1`, the stable generation
above, and persisted impression `6d26eb9f-0a11-4367-9dae-84bb83c8bb9e`.

Run the reliability and snapshot drills against a fresh deployment after
the HTTPS update. The snapshot drill creates a private RDS instance and
updates the ECS service to use it. Remove the drill resources and stack
after collecting the evidence.

```powershell
$env:PYTHONPATH = (Resolve-Path artifacts/stage4/python).Path
uv run --locked python -m scripts.stage4_probes --reliability-only
uv run --locked python -m scripts.stage4_restore
```

The continuation used `--resume-reliability` after the capacity rollback
and again to complete the named rollback's ALB sampling. It used
`--confirm-task-drain` after restore to observe requests across the full
target drain window.

[Expected and observed reliability outcomes](stage4_exit_evidence.md)
