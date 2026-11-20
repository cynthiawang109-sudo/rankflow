# Open questions

## Pooled boundary-exclusion retention analysis

The Stage 0 sign-off registers retention rates across the full sampled session
population by length, duration, and repeat-item share. The Stage 1 kickoff
specifies the follow-up on the fixed W2-dev query population. The Stage 1
ablation report records those W2-dev slices and uses the published Stage 0
pooled aggregates for context. Which later milestone should own the wider
pooled retention-band analysis?

## Stage 2 test identifiers and evidence scope

The Stage 2 kickoff calls the weakened-candidate gate check T02. Addendum
R22 and the T02 entry assign that identifier to training overlap with sealed
W3. Its stage-mapping table also differs from the kickoff checklist.
Keep the Addendum identifiers and track the kickoff scenarios by description.

The kickoff refers to Addendum R28 for session-cluster confidence intervals.
R27 specifies the confidence intervals. R28 specifies retrieval depth and
co-visitation budgets.

SPEC section 12 includes a pointwise comparison and the later-OTTO rehearsal
in the Stage 2 exit criteria. The kickoff pins LambdaRank for the promotion
comparison and also requests a demo rehearsal. The demo rehearsal provides
provenance-validation evidence. The existing SPEC exit criteria still apply.
# Stage 3 open reconciliation

The kickoff and Addendum v3.0.4 reuse test IDs for different scenarios.
Treat the kickoff scenario names and the Addendum scenario names as separate
evidence requirements. For example, the kickoff T16 denotes rollback and kill
while Addendum T16 denotes destructive restore and accounting for lost outbox
events. The Addendum stage mapping also calls for scenarios beyond the kickoff
list. Record scenarios by name and cite the source alongside each test ID.

SPEC ?12 places the reference deployment in Stage 3. The owner kickoff puts
the AWS Fargate/CDK deployment in Stage 4 and asks for local multi-instance
evidence in Stage 3. Stage 3 drills use the local deployment.
