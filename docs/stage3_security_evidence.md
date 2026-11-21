# Stage 3 security and privacy

| Drill | Expected | Observed |
| --- | --- | --- |
| Four-role route matrix | Public endpoints admit all callers. Console endpoints enforce viewer, operator and admin boundaries. | Public, viewer, operator and admin requests matched their route contracts. An operator could publish a shadow config and was denied promotion and incident resolution. |
| Sealed partitions | Requests for W2-gate or W3 examples are rejected and counted, even if the loaded generation lists the names. | All eight requests returned 404 and incremented the denial counter. W2-dev remained available. Unauthorized release registry requests returned 401 or 403 and incremented the protected-read counter. |
| Request controls | Browser mutations require the matching CSRF token. Administrative access uses a bearer header. Oversized or over-limit public requests are rejected. | Missing CSRF tokens returned 403 and a matching token admitted the recommendation. A query-string credential and a Basic header each returned 401. The oversized body returned 413 and the exhausted bucket returned 429. |
| Key separation | Startup rejects reuse of the session HMAC key as a routing salt. | Startup raised the configured key-separation error. The three-instance drill uses one shared session key and a separate shared routing salt. |
| Retention and audit | Expiration removes old pseudonymous decisions and associated delivery data while preserving recent records. Privileged changes carry a verifiable signature. | The 30-day job removed one aged impression, its acknowledgement and one stored delivery payload. The recent impression and its delivery remained. The operator publish HMAC verified. |

The retention job can be run with `python -m rankflow.retention --days 30`
using the event database connection in `RANKFLOW_DATABASE_URL`. Each invocation
processes a bounded batch and leaves pending deliveries eligible for a later pass.

Gitleaks v8.30.0 scanned 66 history commits, the staged implementation, the
documentation directory and three local kickoff logs with redaction enabled.
It reported zero detections. The old Compose values were local demo defaults.
Compose now requires externally supplied values and the API container suppresses
access logs. The scans cover configured Gitleaks patterns within the listed inputs.

`uv lock --check` passed. Production Python dependencies install from `uv.lock`
and the Compose and Dockerfile images use digests. Pip-audit 2.10.0 reported no
known vulnerabilities in the exported locked production requirements.
