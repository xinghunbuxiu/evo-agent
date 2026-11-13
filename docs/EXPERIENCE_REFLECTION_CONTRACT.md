# Experience Reflection Contract

Status: contract, tenant-bound append-only persistence, and authenticated submit/list/decision APIs are implemented. Review-queue UI and accepted-Reflection-to-Recipe generation are not implemented.

## 1. Purpose and boundary

An Experience is an observation of work that happened. A Reflection is a later, attributable interpretation of that observation. A Skill is a reusable procedure derived from reviewed knowledge. These are different records and must not share one mutable status field.

The lifecycle is:

```text
Experience observation
  -> Reflection revision (pending)
  -> reviewer decision (accepted | rejected)
  -> Recipe Skill draft
  -> executable candidate synthesis (new candidate/version)
  -> Broker replay
  -> independent Validator
  -> authorized immutable publication
```

A signed Broker execution attestation proves what ran in the isolated execution environment. It does not prove that the result is correct, generally applicable, or safe to reuse. A Reflection acceptance does not publish or verify a Skill.

## 2. Persistence strategy

- Keep the source Experience unchanged as the historical observation.
- Persist each Reflection revision as a separate tenant-scoped record through the existing `ExperienceStore` and its durable outbox. Do not create a parallel knowledge database.
- Use the `reflection` domain and `experience_reflection` task type, with a structured `metadata.experience_reflection` payload. The record's Experience quality score is not an approval signal and must not be used for Skill promotion.
- Reflection records must be excluded from automatic stable-Experience grouping and automatic Skill drafting.
- Each revision gets a new immutable record ID. Never reuse a previous revision's ID to update its contents.
- The persistence adapter currently verifies evidence references against evidence identifiers already embedded in the source Experience metadata. External Mission-lineage lookup remains future work; API actor and reviewer identities are derived from the authenticated session.
- Once a source Experience has a Reflection chain, changing its canonical digest blocks further revisions rather than silently extending a chain over altered source content.
- Keep remote archival content-addressed and read-back verified through the existing outbox flow.

The current Experience store has existing stable-ID/upsert call sites (for example role-reflection cards and replay-validation records). Do not globally change those semantics as part of Reflection work. The append-only guarantee applies to the new Reflection record type.

## 3. Record contract

The `metadata.experience_reflection` object must contain:

| Field | Meaning |
| --- | --- |
| `schema_version` | Contract version, initially `1` |
| `reflection_id` | Unique immutable revision ID |
| `tenant_id` | Tenant that owns the source and reflection |
| `source_experience_id` | Original Experience ID |
| `source_experience_digest` | SHA-256 of the exact canonical persisted source payload |
| `revision` | Positive, monotonically increasing revision number for this source |
| `parent_reflection_id` | Previous revision ID, null for the first revision |
| `state` | Immutable submission state, always `pending`; effective terminal state is derived from a separate decision record |
| `author` | Authenticated actor that submitted the interpretation |
| `reviewer` | Decision provenance is stored in a separate immutable `reflection_decision` Experience, not written back to this record |
| `created_at` | Immutable creation timestamp |
| `decision_at` | Stored on the separate immutable decision record |
| `source_evidence_refs` | References to evidence already associated with the source Experience or its Mission lineage |
| `findings` | Structured interpretation, not a replacement for source facts |
| `decision_reason` | Stored on the separate immutable decision record as `reason` |
| `idempotency_key` | Tenant-scoped key for safe request retries |

The `findings` object should contain:

- `observed_outcome`: concise interpretation of the source observation.
- `success_factors` and `failure_causes`: evidence-backed factors, not unsupported assertions.
- `applicability_conditions`: when the conclusion may apply.
- `constraints`: environment, version, permissions, resource and policy constraints.
- `counterexamples`: known cases where the conclusion does not hold.
- `confidence`: optional calibrated estimate; never an authorization or promotion gate by itself.
- `open_questions`: unresolved points that need another experiment or human review.

Do not copy or rewrite the original Experience payload into the Reflection as if it were a new observation. Reference it by ID and digest.

## 4. State and authorization rules

Allowed transitions:

```text
pending -> accepted
pending -> rejected
accepted -> superseded (only by a later accepted revision; historical decision remains)
rejected -> superseded (only by a later revision; rejection remains historical)
```

A decision is a new append-only decision event or immutable revision, not an in-place edit to the original observation. A pending reflection cannot create a Recipe Skill draft. A rejected reflection cannot seed a draft. An accepted reflection may authorize creation of a low-trust Recipe Skill draft only.

Authorization requirements:

- Resolve tenant membership from the authenticated session; never trust a tenant ID or actor identity supplied only in the request body.
- Only an authorized tenant reviewer may accept or reject a Reflection. The author cannot approve their own submission unless a separately defined tenant policy explicitly allows it.
- Every decision records the authenticated reviewer, tenant, timestamp, decision and reason.
- Verify the source Experience exists in the same tenant and that its digest matches before accepting a Reflection.
- Verify every evidence reference belongs to the source Experience or its recorded Mission lineage. Do not accept caller-supplied claims such as `broker_signature_verified: true` as proof.
- Use a tenant-scoped idempotency key. Repeating the same request returns the original result; reusing the key with different content fails closed.
- Missing, malformed, mismatched or unverifiable lineage must fail closed and leave the source Experience unchanged.

## 5. Skill boundary

An accepted Reflection may produce a Recipe Skill draft containing natural-language steps, applicability conditions, constraints and source provenance. It remains non-executable.

Executable Skill synthesis is a separate operation that creates a new candidate ID and version. It must:

1. Bind the candidate to the accepted Reflection revision and original Experience digest.
2. Produce the explicit executable contract required by Broker (Python module with synchronous module-level `run(context)`).
3. Pass static contract and workspace-allowlist checks.
4. Execute through the Broker and retain signed evidence.
5. Pass independent Validator policy checks with verified Validator provenance.
6. Require the existing authorized publication path before becoming a reusable immutable Artifact.

No Reflection state, confidence score, Recipe draft or worker-reported success can bypass these gates.

## 6. Required regression tests before enabling routes

- Tenant A cannot read, submit, or decide Tenant B's Reflection.
- Source Experience missing or digest changed: submission/decision rejected.
- Evidence reference outside source/Mission lineage: rejected.
- Duplicate idempotency key with identical payload: same Reflection result; different payload: conflict.
- New revision links to the prior revision and never overwrites it.
- Author self-approval is rejected by default.
- Pending and rejected Reflection records never seed Recipe or executable Skill drafts.
- Accepted Reflection creates only a Recipe draft, never a verified/published Skill.
- Broker success without independent Validator does not promote.
- Reflection archive is retried through the existing outbox and marked delivered only after remote read-back verification.

## 7. Implementation sequence

1. [x] Add the append-only Reflection record validator and tenant-bound persistence adapter on top of ExperienceStore.
2. [x] Add tenant-authorized submit/list/decision routes with idempotency and source-digest verification.
3. Add review-queue UI and audit trail.
4. Connect accepted revisions to Recipe Skill draft generation only.
5. Add a separately authorized Recipe-to-executable synthesis workflow and retain the existing Broker/Validator/publishing gates.

Do not implement steps 4–5 before the Reflection storage, authorization and lineage tests pass.
