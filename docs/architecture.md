# Reference architecture

```mermaid
flowchart LR
    Client -->|HTTPS| ALB
    ALB -->|HTTP in VPC| API1[Fargate API task]
    ALB -->|HTTP in VPC| API2[Fargate API task]
    API1 --> RDS[(Private RDS PostgreSQL)]
    API2 --> RDS
    S3[(Versioned S3 bundles)] --> API1
    S3 --> API2
    Secrets[Secrets Manager] --> API1
    Secrets --> API2
    API1 --> Logs[CloudWatch Logs]
    API2 --> Logs
```

ECS runs one API process per task. The ALB target group uses the routability
health endpoint. Each process verifies its checksum-addressed bundle before
startup, maintains a local cache, and polls the shared config pointer. The
pointer and prepared-bundle acknowledgements are PostgreSQL rows. An accepted
mutation receives a revision and signed audit record. Fleet convergence is
tracked separately. Ranking pins the config for the life of the request.

The serving strategy stays `rule-v1`. The labeled rule-only routing fixture
exercises shadow and canary transport. PostgreSQL records impressions,
decisions, and pending outbox events in one transaction. The outbox consumer
delivers after the request boundary. Scoring isolation is exercised with
labeled fault fixtures and the Playground comparison.

Cloud resources are defined in [the CDK app](../infra/stage4.cjs).
Recovery and release procedures are in the [runbooks](runbooks.md).
