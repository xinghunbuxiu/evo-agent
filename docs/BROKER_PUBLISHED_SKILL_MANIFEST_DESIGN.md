# Broker Published Skill Manifest Design

Status: design decision for the next implementation slice
Date: 2026-11-18
Scope: immutable Skill metadata, Validator binding, Broker Catalog discovery, and Mission planning

## 1. Problem

The Broker Catalog now discovers tenant-scoped, independently validated immutable Skill artifacts. Its current result is intentionally small: Skill ID, version, code SHA-256, trust level, Validator ID, and policy ID.

That is sufficient to enumerate and pin an artifact, but not to decide whether it can satisfy a Mission node. The existing `Skill` model already carries `name`, `domain`, `description`, `capability_type`, and `parameters`; however, the current Artifact Store persists only executable code and trust/evidence fields. The metadata is lost before Catalog discovery.

Do not solve this by scanning tenant workspace Skill files or trusting mutable Registry metadata. Broker-published immutable metadata must be part of the same validation and publication contract as the executable artifact.

## 2. Design invariants

1. **One immutable identity:** executable code and its Manifest are published together under one tenant / Skill ID / version.
2. **Validator binds both:** a positive Validator attestation must bind the exact code digest and Manifest digest. A valid signature for code alone must not authorize altered capability claims.
3. **Broker remains authoritative:** the Broker validates tenant/workspace authorization, persists candidates, publishes create-once artifacts, signs Catalog responses, and re-verifies exact bindings before replay.
4. **Catalog is discovery, not permission:** a Catalog hit is only a candidate. It never authorizes execution or bypasses Mission node authorization, Broker replay checks, or Validator policy.
5. **Exact pinning:** Mission execution binds an exact Skill ID, version, code digest, Manifest digest, and new Mission context. No mutable `latest` alias.
6. **Fail closed:** missing, malformed, unsupported, or digest-mismatched Manifest data is not silently inferred from filenames, descriptions, or local Registry state.
7. **No accidental public sharing:** Catalog results remain tenant-scoped. Cross-tenant reuse requires a separate explicit publication/sharing policy; it is not implied by a `cloud` trust label.
8. **No business-success conflation:** successful code execution, Validator acceptance, and business delivery acceptance remain distinct evidence dimensions.

## 3. Manifest schema

Introduce a versioned canonical JSON document:

`mission.skill-manifest.v1`

Required fields:

- `schema_version`: exact schema identifier.
- `skill_id`, `skill_version`: immutable artifact identity.
- `name`: display name.
- `domain`: existing Skill domain.
- `capability_type`: normalized capability taxonomy value.
- `description`: concise task-oriented capability description.
- `task_types`: non-empty bounded list of supported task categories.
- `input_schema`: JSON Schema describing the `run(context)` input contract.
- `output_schema`: JSON Schema describing the structured output contract.
- `runtime_contract`: explicit executable entrypoint/runtime contract; first supported value remains the existing Python `run(context)` contract.
- `compatibility`: bounded declarations for framework/runtime compatibility.

Optional fields may include tags and declared preconditions, but must be schema-validated, bounded, canonicalized, and included in the digest. Do not place secrets, credentials, tenant-private source data, or arbitrary executable hooks in the Manifest.

The Manifest is descriptive and declarative. It must not contain executable code, dynamic import names, shell commands, or instructions that bypass Broker policy.

## 4. Digest and attestation binding

Canonicalize the Manifest using the same deterministic JSON encoding rules used by the Broker and Validator, then compute:

`manifest_sha256 = SHA256(canonical_manifest_bytes)`

Extend the candidate and validation contract so the following are all bound:

- tenant and workspace identity;
- Mission run / node / task context;
- Skill ID and version;
- executable code SHA-256;
- Manifest SHA-256;
- trust level;
- Broker replay request identity and signed replay evidence;
- Validator policy identity and checks digest.

A Validator positive verdict without the expected Manifest digest is not sufficient for publication.

The published artifact stores the canonical Manifest, code, both digests, and the signed Validator attestation. The Broker's promotion receipt includes both digests and the exact Manifest schema version. Readback verifies every field before returning success.

## 5. Versioned binding migration

Do not silently add optional fields to the existing `mission.skill-replay-binding.v1` contract. Introduce an explicit v2 binding schema containing `manifest_sha256` and require the complete field set.

Migration sequence:

1. Add canonical Manifest normalization and digest helpers with unit tests.
2. Extend candidate staging to carry the Manifest and pin its digest in the stage receipt.
3. Extend the Validator request, policy identity, response, and signed attestation to bind the Manifest digest.
4. Extend Artifact Store publication, readback, and exact binding load for the v2 artifact.
5. Extend Broker promotion receipt and signed Catalog metadata.
6. Extend Mission runtime to persist the exact v2 binding before any side effect.
7. Keep legacy v1 artifacts readable only through the existing legacy path; never synthesize a v1 Manifest or silently upgrade old artifacts. New automatic Catalog reuse must require v2.

## 6. Catalog result

The Catalog may return only verified metadata needed for matching and pinning:

- Skill ID / version;
- code SHA-256 / Manifest SHA-256;
- name / domain / capability type / description;
- task types;
- input / output schema summaries or full bounded schemas;
- runtime contract / compatibility;
- trust level and Validator / policy identity.

Do not return source code, original Mission context, raw validation checks, private Broker staging paths, or secrets.

Catalog pagination must be deterministic. Matching must rank candidates deterministically and explain why each candidate matched. Unsupported runtime contracts and compatibility mismatches are excluded, not downgraded into unsafe fallbacks.

## 7. Mission Planner integration

Planner matching is a recommendation step, not execution authorization:

1. Derive required capability, task type, input/output shape, runtime, and compatibility from the Mission node.
2. Query only the authenticated tenant's Broker Catalog.
3. Filter by runtime and compatibility first.
4. Score capability/task type and schema compatibility using explicit, inspectable rules.
5. Record candidate IDs, scores, and rejection reasons in planning trace.
6. Select a candidate only when it meets a configured minimum threshold; otherwise use the ordinary Worker path.
7. After the Mission run/node/task IDs are fixed, persist an exact v2 binding with both digests.
8. At execution, Broker reloads and verifies the exact artifact and new Mission context. A catalog response is never passed directly to an executor.

Planner must not infer compatibility from a Skill name alone or allow free-form descriptions to override schema/runtime constraints.

## 8. Learning and feedback

Persist separate outcomes:

- `execution_succeeded`: isolated execution result;
- `validator_passed`: independent policy verdict;
- `business_accepted`: downstream delivery/business acceptance;
- `replay_outcome`: completed, rejected, blocked, indeterminate, or failed.

Experience records should capture which Manifest and exact version were used, what matching rationale was recorded, and why an outcome succeeded or failed. A successful execution must not be recorded as business acceptance.

## 9. Security and regression requirements

Required tests before automatic Planner reuse is enabled:

- Manifest normalization rejects unknown/missing fields, invalid JSON Schema, unbounded arrays/strings, duplicate task types, and unsupported runtime contracts.
- Code and Manifest digest tampering are independently rejected.
- Validator signature cannot be replayed against another Manifest digest, version, tenant, workspace, or Mission context.
- Candidate metadata cannot be changed between stage, validation, and promotion.
- Artifact publication remains create-once and readback verified.
- Catalog excludes Drafts and legacy artifacts without a verified Manifest.
- Catalog never leaks another tenant's metadata.
- Broker response signature covers every returned Manifest field and digest.
- Mission Planner filters incompatible runtime and schemas before scoring.
- Deterministic matching gives stable ranking and trace explanations.
- Missing Catalog/Broker/Validator config falls back to ordinary Worker execution without unsafe local-file discovery.
- A pinned binding is not silently replaced if a higher-ranked Skill appears later.

## 10. Delivery slices

A. Manifest schema and canonicalization (no Planner behavior change).
B. Candidate stage + Validator digest binding.
C. Immutable Artifact Store v2 + Broker promotion/Catalog response.
D. Mission runtime exact binding and replay.
E. Planner discovery, matching trace, and safe fallback.
F. Experience feedback and regression end-to-end.

Each slice must include tests and update this document with implemented status. Automatic Skill reuse is not complete until A–F pass.
