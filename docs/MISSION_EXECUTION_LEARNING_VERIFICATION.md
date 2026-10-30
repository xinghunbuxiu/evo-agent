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

This is a **guardrail, not yet a production verifier integration**. The deterministic
end-to-end test attaches a test verifier result explicitly. Production Mission
execution still needs a separately invoked verifier that writes this action-level
evidence from actual execution artifacts. Until that integration exists, unverified
worker claims intentionally do not update strategy outcome statistics.

## Boundaries and remaining work

1. The integration worker is deterministic and test-only, not a production LLM/CLI/device process.
2. Worker-reported verification is treated as an untrusted claim unless independent verification evidence is produced.
3. A successful test run does not establish distributed locking or multi-host correctness. Worker claims currently live in a file-backed registry with a cross-platform file lock.
4. Process-crash recovery and stale-claim reclamation are not yet proven. A future recovery mechanism must reconcile claims against durable Mission/task state and must not release a claim while any linked task is still active.
5. Logical worker cloning copies an approved profile; it does not itself start an isolated model, CLI, or device process.

## Next verification increment

Prioritize crash/restart recovery for worker claims:

- Persist enough claim-to-Mission/node/task linkage to reconcile state after restart.
- Recover only when linked tasks are confirmed terminal or definitively absent from durable queue state; ambiguous states must remain claimed and be surfaced for review.
- Make recovery idempotent and record recovery evidence.
- Add regression tests for restart with active tasks, terminal tasks, missing task records, and repeated recovery.
- Keep multi-host/distributed lease guarantees explicitly out of scope until backed by a shared transactional store.

The goal is to preserve the invariant: **never double-dispatch a worker, and never free a worker whose task may still be running.**
