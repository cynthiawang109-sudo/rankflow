# RankFlow threat model

The reference deployment accepts network traffic through the ALB. The
database is reachable from the task security group inside the VPC. The target
security group accepts API traffic from the ALB security group. AWS manages
the task execution credentials that fetch images and inject secrets. The
task role reads the S3 generation prefixes. Bundle paths are addressed by
their manifest hash and each file is checked before activation.

| Surface | Threat | Control |
| --- | --- | --- |
| Operator routes | Unauthorized release or audit manipulation | Role-checked server routes, bearer authentication over ALB TLS, CSRF checks for browser mutations, and signed append-only records. |
| Public ranking | Oversized or high-rate requests | Strict event validation, request-size limits, and application rate limiting. |
| Feedback | False or duplicate attribution | Persisted impression ID, returned-list membership, attribution window and idempotent event identity. |
| Artifact loading | Substitution, tampering, or partial copy | Read-only runtime object permissions, conditional object creation for deployment assets, manifest identity and per-file checksums, and atomic verified cache activation. |
| Session and holdout data | Identity exposure or training contamination | Separate pseudonymisation and routing keys, retention controls, public partition membership checks, and demo-source quarantine. |

The reference uses short-lived test credentials, restricts network entry to
the probe client, and trusts the short-lived ALB certificate explicitly.
The service uses one RDS database for the control and commit paths. The
same application DB identity performs bootstrap DDL and serving queries.
See [security evidence](stage3_security_evidence.md) and [recovery runbooks](runbooks.md).
