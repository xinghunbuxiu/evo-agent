# Knowledge Containers and Gitee Repository Sharding

## Purpose

Evo's knowledge store is a logical knowledge system backed primarily by multiple Gitee Git repositories. A Gitee repository is a storage shard/node, not the entire knowledge base.

The design separates knowledge by business scenario first, then creates numbered repositories inside each domain as capacity and growth require. The platform presents all shards as one searchable knowledge system.

This is repository-level distribution, not merely copying the same repository to several providers.

## Core principles

1. **Scenario isolation:** Mission traces, Worker profiles, Skills, experiences/mistakes, strategies, and project knowledge have separate repository domains.
2. **Numbered shards:** Each domain has repositories such as `A-01`, `A-02`, `A-03`. The sequence is open-ended; code must not hard-code a maximum shard count.
3. **Gitee-first node service:** Gitee is the initial/default Git hosting service. A provider adapter keeps API details out of domain logic, but multi-provider replication is not a prerequisite for this design.
4. **One logical catalog:** The platform resolves every artifact to its domain, repository shard, branch, path, version, and digest. Users do not need to know which repository stores an item.
5. **Append-only evidence:** Archived task evidence and learning artifacts are immutable by default. Corrections create a new version linked to the previous artifact; they do not silently rewrite history.
6. **Recoverability:** Local pending writes, catalog snapshots, repository manifests, and SHA-256 checks make it possible to rebuild indexes and verify stored content.
7. **Tenant isolation:** Routing and catalog records must retain tenant ownership and access policy. Shared knowledge is promoted only through the existing review/promotion rules.

## Initial domain namespace

These are logical domain codes, not a requirement to create every repository immediately.

| Domain | Meaning | Typical artifacts |
| --- | --- | --- |
| A | Mission archive | task inputs/outputs, decision records, execution traces, verification evidence |
| B | Worker archive | worker profile snapshots, role history, growth and retirement records |
| C | Skill archive | skill definitions, versions, dependencies, provenance |
| D | Experience archive | lessons learned, mistake book, causes, corrections, replay outcomes |
| E | Strategy archive | strategy versions, selection evidence, effectiveness feedback |
| F | Project archive | project-specific knowledge, design decisions, reusable project context |

Examples: `A-01` and `A-02` are two Mission archive shards. `D-01` is the first experience/mistake-book shard. A repository can hold a date-partitioned directory tree, but a domain must not mix unrelated business purposes merely to fill unused space.

## Repository registry and catalog

A small control-plane registry records repository metadata and routing policy. It must not contain the full knowledge corpus.

Suggested repository record:

```json
{
  "repository_id": "A-01",
  "domain": "mission",
  "provider": "gitee",
  "namespace": "owner-or-organization",
  "repository_name": "evo-knowledge-a-01",
  "branch": "main",
  "status": "active",
  "created_at": "2026-11-04T00:00:00Z",
  "capacity_policy": {
    "warning_ratio": 0.70,
    "stop_writes_ratio": 0.80,
    "hard_limit_ratio": 0.90
  }
}
```

Suggested artifact catalog record:

```json
{
  "artifact_id": "mission_20261104_00001",
  "tenant_id": "tenant-001",
  "domain": "mission",
  "repository_id": "A-01",
  "path": "2026/11/04/mission_20261104_00001.json",
  "artifact_type": "decision_trace",
  "version": 1,
  "sha256": "<sha256>",
  "created_at": "2026-11-04T00:00:00Z",
  "status": "verified"
}
```

The registry should have a compact local durable copy and a versioned remote copy. Repository manifests are partition-local and can be rebuilt from verified artifacts. Do not make one large manifest containing every artifact the only source of truth.

## Capacity-aware shard allocation

Capacity is measured per repository using the best available provider metadata and, where available, a conservative estimate of Git object/history growth. Also track file count, largest file, recent growth rate, API throttling, and provider limits.

Thresholds are configurable per provider/account; do not hard-code an assumed Gitee quota because limits can vary by account, repository type, and service policy.

Default policy proposal:

- 70%: warning; report projected time to capacity.
- 80%: stop assigning new artifacts to this shard and allocate the next shard.
- 90%: critical; block writes unless an explicit emergency override is authorized.
- Existing artifacts remain readable in sealed shards.
- A shard in `sealed` state is read-only for normal writes but remains searchable and verifiable.

When `A-01` reaches its write threshold, the allocator reserves `A-02`, verifies that it is writable, registers it, and only then routes new artifacts to it. If creation or verification fails, retain the local pending archive and retry; never mark the artifact remotely archived.

Do not rely on deleting old files to reclaim Git capacity: Git history can retain prior blobs. Prefer new shards and immutable archive records. Any compaction must be an explicit migration that verifies source and destination hashes before changing catalog pointers.

## Routing and growth

Routing order:

1. Resolve tenant and artifact purpose to a domain.
2. Select the active shard for that domain.
3. Check shard health, write status, capacity headroom, and provider rate limits.
4. Allocate a new numbered shard when the current shard reaches its write threshold.
5. Write the artifact idempotently, then read it back and verify SHA-256.
6. Commit the artifact catalog record only after remote verification.
7. Preserve a local durable pending record until the catalog update itself is verified.

Shard IDs are allocated under a serialized/leased allocator so concurrent workers cannot both claim the same next ID. Artifact IDs are globally unique and idempotent; retrying a write must not create duplicate logical artifacts.

## Layout inside each repository

Example:

```text
A-01/
├── repository.json
├── manifests/
│   ├── 2026-11.json
│   └── checksums.json
└── artifacts/
    └── 2026/11/04/
        ├── mission_20261104_00001.json
        └── mission_20261104_00002.json
```

Keep files reasonably sized and partition by date/type. Large traces or attachments should be chunked into bounded parts with a manifest that records ordered part paths, byte sizes, and hashes. Enforce provider-specific single-file limits before upload.

## Failure handling and recovery

- Gitee/API unavailable: queue locally; do not lose or discard the local snapshot.
- Repository full or rate-limited: mark the shard degraded/sealed as appropriate and allocate or retry another shard.
- Catalog unavailable: keep the artifact pending; do not report complete archival.
- Hash mismatch: quarantine the remote record and retry from the local verified snapshot.
- Missing repository: reconstruct from registry snapshots and manifests; report artifacts whose bytes cannot be recovered.
- Index loss: rebuild catalog partitions by scanning repository manifests and validating artifact hashes.
- Concurrent allocation: use an allocator lease/compare-and-swap and unique repository IDs.
- Credential failure: surface an actionable permission/configuration error; never log tokens.

## Platform visibility

The Knowledge page should eventually expose:

- domain and repository shard list (`A-01`, `A-02`, ...);
- repository status, used capacity, remaining headroom, file count, largest file, and growth rate;
- active, sealed, degraded, and pending states;
- artifact counts by type and tenant;
- last successful write/readback verification;
- failed sync queue and retry state;
- search across all registered shards;
- artifact provenance, versions, hashes, and restore/verification history.

## Implementation status

The first capacity-aware shard control-plane slice is now implemented:

- `src/core/knowledge_shards.py` stores a local atomic repository registry and append-only artifact-location catalog.
- Domain IDs are allocated as `A-01`, `B-01`, ... using a process lock; `reserve_or_get_provisioning_shard` reuses an in-flight reservation to avoid duplicate shard IDs.
- `src/admin/knowledge_shard_runtime.py` provisions deterministic Gitee repository names through the existing provider abstraction and activates the shard only after the provider returns its repository identity.
- Gitee repository creation handles a concurrent-create conflict by reading the deterministic repository name back.
- Usage metrics can be recorded by bytes and file count; reaching the configured write threshold seals the shard. Existing sealed shards remain addressable in the catalog.
- Artifact catalog entries include tenant, domain, repository, branch, path, version, and SHA-256. Duplicate artifact IDs are idempotent only when their location and digest match.
- `GET /api/tenants/{tenant_id}/knowledge-shards` exposes the tenant shard inventory; the Knowledge page now displays numbered repositories, status, latest measured capacity ratio, and file count.
- `src/admin/experience_shard_runtime.py` now provisions the tenant's numbered `D-*` experience shard, uploads a complete work-node archive batch, reads every file back, and only then appends artifact catalog records with SHA-256 digests.
- Both the initial work-node archive and local-archive retry paths use the same verified shard writer. Failed provisioning, upload, readback, or catalog registration keeps the local snapshot and does not report remote archival success.
- The experience archive runtime has focused tests for allocation, full readback/catalog behavior, idempotent retry, and refusing to catalog tampered remote content.

This is the first integrated production write path, not yet the complete knowledge write path. `ExperienceStore.save()` still writes the local learning store; skill, strategy, mission-trace and worker-profile writers are not yet routed through numbered shards. Fresh provider capacity measurement, cross-shard search and catalog reconstruction also remain follow-up work. Do not describe automatic capacity rotation as globally active until usage measurement and the remaining writer integrations are complete.

Do not bypass tenant policies, skill promotion guards, or existing archive integrity checks.

## Related documents

- [evo-index-schema.md](evo-index-schema.md)
- [MISSION_EXECUTION_LEARNING_VERIFICATION.md](MISSION_EXECUTION_LEARNING_VERIFICATION.md)
