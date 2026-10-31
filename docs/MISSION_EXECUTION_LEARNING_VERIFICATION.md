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

## Boundaries and remaining work

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
