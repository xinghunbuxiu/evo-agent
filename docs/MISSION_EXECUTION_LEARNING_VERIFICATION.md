# Mission execution-to-learning verification flow

This document records what the regression suite proves today and what it does not prove.

## Verified single-flow integration test

`tests/test_mission_execution_learning_e2e.py` carries one deterministic test task through the core learning loop:

```text
Seed tenant-scoped strategy
  -> Mission runtime authorizes a plan node
  -> deterministic test worker executes is_even edge-case assertions
  -> execution action retains decision_trace + execution_evidence + strategy_usage
  -> feedback consumes the strategy_usage from that same action/task
  -> duplicate feedback is rejected (idempotency)
  -> a fresh StrategyEngine reloads persisted feedback after simulated restart
  -> the next MissionPlanner plan retrieves the same strategy
```

The worker is a deterministic test-only adapter. This proves evidence continuity across the runtime, feedback, persistence, and planning boundaries; it does **not** prove that a production LLM or external worker independently verified the result.

## Regression evidence

| Stage | Regression test | What it establishes |
| --- | --- | --- |
| Planning trace | `tests/test_mission_simple_task_analysis.py` | Input, capability, knowledge, strategy, status, and workforce decisions are recorded. |
| Runtime dispatch and execution | `tests/test_mission_simple_task_execution.py` | Runtime authorization is enforced; a deterministic worker executes edge-case assertions and the action retains decision trace and execution evidence. |
| Single-flow execution-to-learning | `tests/test_mission_execution_learning_e2e.py` | The same action's strategy usage is fed back, duplicate feedback is idempotent, state survives engine reload, and the next plan retrieves the strategy. |
| Failure lineage | `tests/test_mission_failure_learning_evidence.py` | Failure-learning records preserve Mission run, source task, node, decision trace, and dispatch authorization. |
| Strategy feedback guards | `tests/test_mission_strategy_feedback.py` | Recommendations alone do not count as usage; unverified worker claims are not promoted to independent verification; persisted feedback is retrievable by later plans. |
| Worker reservation | `tests/test_mission_worker_claims.py` | A worker cannot be double-claimed, claims survive a handler error after submission, safe cloning is gated, and terminal task states release claims. |

## Latest observed CI evidence

- Commit: `04341e27da5d1edbd871178e9c55e929342a89db`
- Workflow run: [Python regression tests #305](https://github.com/xinghunbuxiu/evo-agent/actions/runs/40807431541)
- Result: **passed**
- Observed job steps: runner diagnostics, checkout, Python virtual environment, dependency installation, regression suite, and artifact upload all completed successfully.
- This is evidence that the workflow completed successfully; this document does not assert a test count unless the uploaded regression output is inspected.

## Independent-verification gate (2026-10-30)

Strategy outcome statistics now require structured verification evidence bound to the
same task: verifier identity/version, execution event ID, a passed/failed status, and
non-empty check-level results. The evidence must be attached to the Mission action
under `independent_verification`; worker result fields such as
`strategy_usage.verification_passed` remain untrusted claims. The StrategyEngine
rechecks the evidence contract before changing usage counts or success rates, so
callers cannot bypass the runtime gate by constructing an Experience directly.

This remains a **limited verifier integration, not a general production test runner**.
Mission refresh calls an injected `independent_verifier` callback for terminal tasks.
The runtime first removes any pre-existing action-level evidence, then accepts only
verifier identity/version and well-formed check results from that callback. The runtime
itself binds the result to the queue task ID and completion event, derives passed/failed
from the checks, and only then exposes `independent_verification` to strategy feedback.
Callback errors, malformed results, failed queue tasks, and cross-tenant tasks fail closed.

The production server injects the read-only workspace artifact verifier described below.
Only tasks with an explicit, valid structured contract can receive artifact verification;
tasks without one remain unverified and cannot update strategy outcome statistics.

## Read-only workspace artifact verifier (2026-10-31)

Mission nodes may now carry an optional `verification_contract` using schema
`mission.verification.v1`. The deterministic workspace verifier currently supports:

- `file_exists`: a regular file exists inside the workspace.
- `file_contains`: a UTF-8 file contains the declared text.
- `json_value_equals`: a JSON value at a declared key/index path equals the expected value.

A contract can be declared directly on a registered task template as
`verification_contract`, or supplied at Mission planning time through
`context.verification_contracts`, keyed by the exact node ID. A task-template
declaration takes precedence over the context mapping. The planner preserves the
declaration; the Mission brain validates it; the action runtime carries it into the
execution record; and the production server injects the read-only verifier into the
Mission execution runtime.

Example planning context:

```python
context = {
    "verification_contracts": {
        "write_readme": {
            "schema_version": "mission.verification.v1",
            "checks": [
                {
                    "check_id": "readme_exists",
                    "type": "file_exists",
                    "path": "README.md",
                }
            ],
        }
    }
}
```

The verifier resolves paths against the workspace root,
rejects absolute paths, traversal and symlink escapes, and limits inspected files to
2 MiB. It never executes worker-provided shell commands or Python code and does not
trust `task.result` or worker-reported success flags.

This is the first real artifact-inspection capability, not a general-purpose test
runner. Existing natural-language `validation_checks` are not automatically
converted into executable checks. A Mission without an explicit structured contract
remains unverified and cannot contribute strategy outcome feedback. In particular,
file-presence/content checks do not prove program behavior. Runtime-generated evidence
is now HMAC-SHA256 signed with a workspace-local key under `.admin/`, created with
owner-only permissions and a cross-process initialization lock. Strategy feedback and
strategy promotion reject unsigned, tampered, or cross-tenant evidence. This protects
the learning API against fabricated JSON evidence from callers that do not possess the
workspace signing key; it is **not** a security boundary against a malicious process
running as the same OS user or one that can read/replace the key. Production isolation
still requires a separately protected secret or verifier service, plus language-specific
sandboxed test runners.

## Self-hosted runner isolation capability probe (2026-10-31)

Workflow run [#583](https://github.com/xinghunbuxiu/evo-agent/actions/runs/41194270611)
completed successfully on commit
`eb55a00d54a9e20ef2d8d0d0d105fa5e4de99d0d` and ran 185 regression tests
(185 passed, 0 failures, 0 errors, 0 skipped). The same run collected these
host observations as the `evo-runner` account:

- Docker CLI 29.1.3 is installed, but the account cannot access
  `/var/run/docker.sock` (root:docker socket; permission denied). The Docker
  daemon's server-side configuration therefore could not be inspected.
- Podman is not installed.
- `unshare --user --map-root-user --mount --pid` fails with
  `Operation not permitted`; unprivileged user namespaces are unavailable to
  this runner process.
- `systemd-run --user --scope` is unavailable for this account/session.
- The runner process reports `Seccomp: 0` and `NoNewPrivs: 0`.
- GitHub main site/API and codeload probes succeeded in this run, while
  raw.githubusercontent.com and PyPI showed intermittent timeouts/resets.

These observations mean that **no usable per-job isolation mechanism has yet
been demonstrated on this host**. Do not add `evo-runner` to the `docker`
group: access to the Docker daemon is effectively host-administrator
privilege and would undermine the intended boundary.

A future deployment should use a narrow, root-owned sandbox broker (or a
separate disposable VM service), not expose the Docker socket to the
application/worker. The broker must accept only the versioned allowlisted
execution profile, construct fixed container arguments itself, pin the image
by digest, disable networking, mount source read-only, use a separate
writable temporary filesystem, drop capabilities, enforce
`no-new-privileges`, resource/PID/time/output limits, and return a bounded
result envelope. Its signing key must not be readable by the runner account.
Until such a broker is deployed and independently tested, the production
sandbox adapter remains unconfigured and execution must continue to fail
closed.

## Independent Skill Validator service

The standalone Validator is a separate process from both Mission and Broker.
It does not execute candidate code. It accepts only a signed Broker Skill Replay
envelope, verifies that envelope with its pinned Broker public key, then applies
a root-controlled policy matched on the exact tenant, Skill ID, version,
source SHA-256 and requested trust level. Only a complete policy pass produces
an Ed25519 attestation. The Validator private key is readable only by the
Validator service account; the Broker receives only the raw public key.

The policy document is deployment-controlled and does not arrive in the
validation request. Supported output checks are deliberately small and
deterministic: json_key_exists, json_value_equals, and json_value_type.
A policy must contain at least one check. Broker execution success alone is
never enough to issue an attestation.

Example service configuration: deploy/skill-validator.config.example.json.
Example acceptance policy: deploy/skill-validator.policies.example.json.
Example systemd unit: deploy/evo-skill-validator.service.example.

Run from the repository root after installing runtime dependencies:

\`\`\`bash
PYTHONPATH=src python -m core.skill_validator_daemon \\
  --config /etc/evo-skill-validator/config.json
\`\`\`

The Broker/Mission caller sends mission.skill-validation-request.v1 to the
Validator Unix socket. The request contains the exact Mission context, a draft
Skill binding, desired trust level, and the complete Broker-signed Replay
envelope. The Validator checks the Broker signature and execution status
before looking up the policy. The resulting attestation uses the mission.skill-validation-attestation.v2 contract
and signs the exact policy ID plus a SHA-256 digest of its normalized contents and can be passed to the
Broker's existing candidate-promotion operation.

This is the first independent Validator service boundary, not an automatic
promotion workflow. Deployment must provision a policy for each exact
artifact digest, create separate Broker/Validator OS accounts and keys, set
the socket's shared group/UID allowlist (the Validator service group must be shared with the Broker account), and configure the Broker with only
the Validator public key. No production Skill should be promoted until its
acceptance policy reflects real business requirements and the service is
deployed with protected keys. The current implementation validates the
structured Skill output; it does not claim to prove arbitrary real-world
outcomes beyond the checks declared in that policy.

## Broker Artifact Store promotion boundary

The Broker now exposes a separate candidate-promotion operation. The caller
submits an Ed25519 Validator attestation; the Broker resolves the candidate
from its own immutable staging store (promotion requests cannot replace source
code), checks the exact tenant, Skill ID, version, source SHA-256 and requested
trust level, and publishes a create-once trusted artifact. The Broker returns
its own signed publication receipt.

This operation does **not** implement the Validator or decide whether a Skill
is useful. The Validator must run independently, hold a private signing key
that is not readable by the Mission worker or Broker, perform the declared
business acceptance checks, and sign only a passed result. The Broker stores
only the Validator public key. A successful Broker receipt proves that the
signed statement matched the staged bytes and publication succeeded; it does
not independently prove that the Validator's business judgment was correct.
Automatic promotion remains disabled until that external Validator is deployed.


1. The integration worker is deterministic and test-only, not a production LLM/CLI/device process.
2. Worker-reported verification is treated as an untrusted claim unless independently inspected and runtime-signed evidence is produced.
3. Workspace-local HMAC signing protects against data-only evidence forgery, not a malicious process running as the same OS user or able to read the key.
4. A successful test run does not establish distributed locking or multi-host correctness. Worker claims currently live in a file-backed registry with a cross-platform file lock.
5. Startup recovery now reconciles persisted Mission claims with durable queue state. Missing, active, ambiguous, or unqueryable tasks remain reserved for review; terminal tasks can be released idempotently with audit evidence.
6. Logical worker cloning copies an approved profile; it does not itself start an isolated model, CLI, or device process.

## Next verification increment

Prioritize a separately protected signing secret and an isolated test-runner boundary:

- Move the signing key out of the worker-readable workspace, or delegate signing to a trusted verifier service.
- Add Python/JavaScript test runners only behind an explicit, allowlisted execution profile.
- Execute test suites in an OS/container sandbox with bounded time, memory, filesystem and network access.
- Bind test output, exit status, test selection and artifact digests into signed evidence.
- Keep multi-host worker lease guarantees out of scope until backed by a shared transactional store.

The goal is to preserve the invariant: **never double-dispatch a worker, and never free a worker whose task may still be running.**


## Allowlisted execution-profile contract (2026-10-31)

The new src/core/execution_profiles.py module resolves a strict declarative request
into a fixed process specification for a future trusted sandbox adapter:

- python.unittest accepts only a dotted Python module name.
- python.pytest accepts only an existing test file resolved inside the workspace.
- Requests may select a registered profile and target, plus a bounded timeout (1–300 seconds).
- The resolver owns the executable, fixed arguments, working directory, output cap (256 KiB), and network-disabled intent.
- Worker-supplied command, argv, env, or cwd fields are rejected.
- Absolute paths, traversal, Windows drive/UNC paths, NUL bytes, and symlink escapes are rejected for file targets.

This is only a profile contract and command-spec builder. It does not spawn a process
and does not provide OS-level network, CPU, memory, or filesystem isolation. The
network_access=False field is policy metadata, not a firewall. No production Mission
dispatch is connected to these profiles yet. A future adapter must execute the spec
inside an independently enforced sandbox and produce runtime-owned, signed evidence.


## Trusted runner result envelope (2026-10-31)

The new src/core/execution_results.py normalizes a result captured by a trusted
runner adapter into mission.execution-result.v2. It records runner ID/version,
profile and target, timeout/exit status, and SHA-256 digests plus captured byte
counts, Docker-available byte counts, and an explicit per-stream `capture_truncated` flag for
stdout/stderr. The digest covers captured bytes only. `available_bytes` means bytes returned by the runner's log source, not guaranteed total process output. Docker's post-exit log API may expose only retained logs after daemon log rotation; completeness beyond returned data is unknown and must not be inferred from `capture_truncated=false`. Raw output is not copied
into the learning evidence envelope. Non-zero exits and timeouts cannot be marked
as execution success; captured output beyond the profile cap and malformed
runner metadata are rejected. The Docker adapter records bytes available from the log API
before applying the combined output cap, so reviewers can distinguish complete
logs from truncated evidence.

This is still a result-normalization contract, not runner authentication. The
function must only be called by a trusted adapter that actually observed the
process. It does not spawn the process, enforce a sandbox, or sign the envelope.
The Mission runtime must later authenticate the adapter and sign the normalized
record before strategy feedback or task completion can rely on it.


## Fail-closed sandbox adapter boundary (2026-10-31)

The new `src/core/sandbox_runner.py` defines the integration boundary for a
deployment-provided isolated runner:

- `execute_with_sandbox` resolves the allowlisted profile before invoking an adapter.
- If no runner is injected, it raises `SandboxRunnerUnavailable`; there is no
  subprocess, TaskQueue-handler, shell, or in-process execution fallback.
- The adapter receives only the resolved fixed `ExecutionProfileSpec` and must
  return a structured `RunnerProcessOutput` containing observed exit status,
  stdout/stderr bytes, available byte counts, and timeout state.
- The wrapper normalizes that observation with `mission.execution-result.v2`.

This is an interface and fail-closed policy gate, **not an implementation of a
sandbox**. The protocol type, runner ID/version, and result envelope do not
authenticate an adapter or prove that it enforced isolation. A production
deployment must inject only a separately trusted adapter backed by an OS/container
boundary with enforced filesystem, network, CPU, memory, process-count, timeout,
and output limits. Until such an adapter is configured, execution is intentionally
unavailable. This boundary is not yet wired into Mission production dispatch.


## Privileged sandbox broker wire contract (2026-10-31)

`src/core/sandbox_broker_protocol.py` defines the first client-side protocol contract for a separately installed privileged broker:

- Requests use `mission.sandbox-broker-request.v1` and carry only a registered opaque `workspace_id`, allowlisted profile ID, workspace-relative target, bounded timeout, and request UUID. They never carry caller-selected argv, cwd, environment, host paths, mounts, or Docker options.
- Responses use `mission.sandbox-broker-response.v1` and contain the opaque workspace ID plus a `mission.execution-result.v2` envelope signed with Ed25519. The client verifies the configured key ID, public key, request UUID, exact workspace ID, result schema, status consistency, output capture metadata and digests, profile, and exact requested target. The workspace ID is part of the signed payload to prevent a valid result for one registered workspace from being replayed as a result for another.
- The broker's private signing key must remain root/service-account-only; the application receives only a pinned public key.

This is deliberately only a protocol and signature-verification library. It does not provide a Unix socket transport, broker daemon, Docker access, container isolation, or production Mission integration. The broker must independently validate every request, resolve `workspace_id` through a root-owned allowlist, construct fixed container arguments, and sign only observed execution results. Until that separately deployed service exists, the existing sandbox adapter remains unavailable and must fail closed.


## Broker service core and Unix socket transport (2026-10-31)

The broker implementation is now split into three testable layers:

- `src/core/sandbox_broker.py` validates the exact request schema, maps only
  registered opaque workspace IDs, resolves the target again inside that
  workspace, claims request IDs in a persistent SQLite ledger, invokes only an
  injected executor, normalizes the observed process result, and signs it with
  the broker's Ed25519 private key. Replayed request IDs are rejected even
  after service reconstruction/restart.
- `src/core/sandbox_broker_transport.py` implements bounded length-prefixed
  JSON frames over Unix-domain sockets. The server-side connection handler
  checks Linux kernel `SO_PEERCRED` UID before parsing the request; platforms
  without peer credential support fail closed. The client helper verifies the
  returned signature against a pinned public key and checks the exact profile
  and target requested.
- The broker replay database and its containing directory are restricted to
  owner-only permissions. The service returns generic transport errors rather
  than leaking filesystem paths or exception details.

Regression coverage includes request replay after restart, unknown workspace
IDs, invalid targets, peer UID rejection, bounded socket exchange, and signed
response verification.

This still is **not a deployed sandbox**: the repository does not yet provide
the systemd socket unit, root-owned workspace registry provisioning, container
executor, image digest policy, cgroup limits, or production Mission dispatch
integration. The injected executor must not use host subprocess execution as a
fallback. Until a separately reviewed deployment provides those controls, the
broker remains an unconfigured component and Mission execution must fail closed.


## Digest-pinned Docker executor and systemd broker deployment (2026-10-31)

The broker now includes a Docker SDK executor and a systemd socket-activated
daemon entry point:

- `src/core/sandbox_docker_executor.py` accepts only an immutable
  `image@sha256:<64 hex>` reference. It does not pull images or accept a
  worker-selected image, command, mount, environment, or Docker option.
- The executor constructs commands from the two registered profiles itself.
  Pytest caching and automatic third-party plugin discovery are disabled so
  test runs do not attempt to write into the read-only source tree or load
  arbitrary image-installed plugins.
- Each container uses a read-only root filesystem and read-only workspace
  bind mount, no network, UID/GID 65532, no capabilities, no-new-privileges,
  512 MiB memory, one CPU, 128 PIDs, a 64 MiB no-exec temporary filesystem,
  bounded daemon log rotation, and forced cleanup.
- The Docker SDK dependency is isolated in `requirements-broker.txt`; it is
  not added to the normal application requirements.
- `src/core/sandbox_broker_daemon.py` loads a root-owned configuration,
  validates canonical workspace roots, loads a service-only Ed25519 key, and
  requires exactly one systemd-activated Unix stream socket.
- `deploy/systemd/` contains socket and service unit templates. The socket
  grants access only to the configured application group, while the daemon
  separately checks the connecting process UID using kernel peer credentials.

The daemon service account must be a member of the Docker socket's privileged
group to invoke the Docker API. That permission is effectively host-admin
authority; it must be granted only to the dedicated broker account, never to
the general Mission/Worker or GitHub Actions runner account. The systemd
hardening settings reduce the broker process' ambient access but do not make
Docker daemon access non-privileged.

These files are deployment scaffolding, not a claim that a production broker
is installed. The image digest, workspace registry, broker key, app UID/group,
Docker daemon policy, and host directory permissions must be provisioned and
reviewed on the target host. No host permissions or services were changed by
this repository update.


### Broker implementation verification status

The Docker executor and systemd daemon now have unit-level policy coverage.
Those tests use a fake Docker client and validate the exact container creation
configuration; they do not start a real Docker container. The host's previously
observed `evo-runner` account still lacks Docker socket access and must not be
granted it. The dedicated `evo-broker` account and its Docker group membership
are deployment-only and have not been created on the VPS.

The broker is not yet wired into Mission's production task completion path.
A successful broker response can be independently verified by the client
helper, but no Mission action currently consumes that response as task
completion evidence. Keep production execution fail-closed until the broker
is installed, the image digest is built and pinned, a real container test
confirms isolation, and a reviewed Mission adapter binds the signed response
to the exact task and tenant.


### Workspace mount-path ownership boundary

Before the broker accepts a workspace root, it now checks the entire parent
directory chain. Ancestors must be real directories (no symlinks), owned by
root or the dedicated broker UID, and not group/world writable. The only
writable-ancestor exception is a root-owned sticky directory such as
`/tmp`; this permits isolated test fixtures without allowing another account
to replace a workspace path before Docker resolves its bind mount. The
workspace directory itself may remain writable by its owning application
account, because it is mounted read-only inside the container.

The Unix transport also rejects malformed UID allowlists, including booleans
(which Python otherwise treats as integers) and duplicate or negative UIDs.


## Mission-bound broker attestation protocol (2026-11-04)

The sandbox broker wire contract is now versioned as
`mission.sandbox-broker-request.v2` / `mission.sandbox-broker-response.v2`.
Every request must carry an exact `mission_context` containing
`tenant_id`, `mission_run_id`, `node_id`, and `task_id`. The broker validates
that identity envelope before claiming the request ID or executing the profile,
then includes it in the Ed25519-signed response payload. The client requires the
expected identity envelope and rejects a response whose Tenant, Mission, node, or
task differs, even if the response signature is otherwise valid.

This closes the protocol-level cross-task/cross-tenant replay gap: a valid signed
execution result is now cryptographically bound to the task identity supplied by
the trusted caller. It does **not** yet prove that the caller supplied truthful
identity values, nor does it automatically connect arbitrary TaskQueue workers to
the broker. The production dispatch adapter must derive these four values from the
server-owned Mission run and durable queue Task, pass them to `execute_via_broker`,
and persist the verified broker envelope as runtime-owned task evidence. The
Mission verifier must then verify the broker signature and compare all four values
against the durable Mission action and Task before strategy feedback is eligible.

The broker remains undeployed in the VPS environment. These changes do not grant
the normal runner Docker access or enable a local subprocess fallback. A signed
broker result is an execution attestation, not by itself a proof that the requested
behavior is correct; independent artifact/test checks remain necessary.

## Mission → Broker Skill Replay 接线

当前 Mission 已提供一个**显式授权、按租户隔离**的 Skill Replay 入口。它只接受真正的 Python 可执行 Skill 候选，不会把自然语言 Recipe 当成代码执行；Replay 结果只形成签名执行证据与待反思 Experience，不会自动提升 Skill 信任等级。

### 1. 可选运行时配置

普通 Mission 不依赖 Broker。未配置以下环境变量时，普通 Mission 仍可正常启动，Replay API 返回 503。配置不完整或密钥/证据目录权限不安全时，Replay Runtime 会 fail closed 并保持禁用。

| 环境变量 | 含义 |
|---|---|
| `EVO_SKILL_REPLAY_BROKER_SOCKET` | Broker Unix Socket 绝对路径 |
| `EVO_SKILL_REPLAY_WORKSPACE_ID` | Broker 根配置中注册的 opaque Workspace ID |
| `EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY` | Broker Ed25519 公钥文件，32 字节原始格式 |
| `EVO_SKILL_REPLAY_BROKER_KEY_ID` | 必须与 Broker 签名 Key ID 完全一致 |
| `EVO_SKILL_REPLAY_EVIDENCE_ROOT` | 预先创建的证据目录，必须为 canonical、非 symlink、权限 0700 |

示例（路径和 Key ID 必须替换成部署环境的真实值）：

```bash
EVO_SKILL_REPLAY_BROKER_SOCKET=/run/evo-sandbox-broker.sock
EVO_SKILL_REPLAY_WORKSPACE_ID=evo-agent
EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY=/etc/evo-admin/broker-public-key.raw
EVO_SKILL_REPLAY_BROKER_KEY_ID=evo-broker-production
EVO_SKILL_REPLAY_EVIDENCE_ROOT=/var/lib/evo-admin/skill-replay-evidence
```

部署要求：

- Admin 服务账号必须拥有读取公钥和证据目录的权限；证据目录不得允许 group/other 访问。
- Broker Socket 的 peer UID allowlist 必须包含 Admin 服务账号 UID。
- Broker 的 `workspace_roots` 与 `workspace_tenants` 必须显式登记同一个 Workspace ID，并授权相应 tenant。
- Broker 使用独立私钥签名；Admin 只持有公钥。不要把 Broker 私钥放入 Admin 环境变量或项目工作区。
- 公钥必须是 32 字节 Ed25519 raw public key，不是 PEM，也不是 Base64 文本。

### 2. 候选执行契约

候选必须同时满足：

- `trust_level=draft`；
- `parameters.execution_contract.kind=python_run_context`；
- `parameters.execution_contract.replay_eligible=true`；
- 代码中恰好定义一个同步 `run(context)` 入口；
- 候选的 `mission_run_id` 与 `mission_node_id` 必须匹配发起 Replay 的 Mission 与节点。

`non_executable_recipe`、普通说明文字、缺少执行契约或入口签名不匹配的候选会在连接 Broker 前被拒绝。Admin 只做格式/身份检查，不在主进程执行候选代码。

### 3. 显式 Replay API

登录且具备该 Mission 租户 `tenant_admin` 或 `member` 角色的用户，可以针对指定 Mission 节点发起一次 Replay；`viewer` 只读角色不能触发代码执行。未配置 Broker 时，`GET /health` 的 `checks.skill_replay_broker_configured` 为 `false`，但不会降低普通 Mission 的健康状态。

```http
POST /api/missions/{mission_run_id}/skills/{skill_id}/replay
Content-Type: application/json

{"node_id":"<mission-node-id>"}
```

服务端会先在 Mission 运行记录中创建 `skill_replay/running` 操作，再依次执行：

1. 从当前租户的 Draft Skill 目录安全读取候选（拒绝 symlink、越权目录和超限文件）。
2. 固定 Skill ID、版本、SHA-256、信任级别及 Mission/Node/Task 身份。
3. 通过 Broker Socket 暂存不可变候选，并验证 Broker 签名回执。
4. 通过专用 `skill.replay.python.v1` Profile 执行；不接受 Worker 提交的 argv、cwd、容器参数或任意命令。
5. 验证 Broker 执行签名，将原始 attestation 写入租户隔离的 Evidence Store，并投影为待反思 Experience。
6. 将 Evidence ID、Experience ID、签名暂存回执和执行结果写回 Mission 操作记录。

重复提交相同 Skill/Node 且已有 Replay 正在执行时返回 409。未登录、跨租户、Mission/Node 不匹配、Broker 不可用或候选不符合契约时均不会被记为成功证据。

### 4. 证据边界

`execution_succeeded=true` 只表示 Broker 隔离执行成功，不表示业务目标已通过验收。Replay 失败但 Broker 签名有效时，也会作为失败观察保存并进入待反思状态；传输失败或签名验证失败则不会创建成功 Experience。如果 Broker 证据已持久化、但 Experience 投影失败，Mission 操作记录会保留异常携带的 Evidence 引用，避免丢失已落盘证据的追踪入口。

**当前仍未开放自动晋升。** 独立 Validator 必须针对完全相同的 tenant、Skill ID、版本和内容 SHA-256 完成验收，并使用 Artifact Store 信任的 Validator 私钥签名；Broker 在发布时重新验证该签名后，才允许将候选发布为 verified。Recipe 候选仍保留为知识资产，不进入 Python Replay。
