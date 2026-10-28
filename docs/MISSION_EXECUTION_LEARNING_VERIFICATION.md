# Mission execution-to-learning verification flow

This document records what the regression suite proves today and what it does not prove.

## Verified flow (automated tests)

```text
Task input
  -> MissionPlanner creates node + decision_trace
  -> Mission runtime validates coordination contract and dispatch authorization
  -> deterministic test worker executes and checks is_even(2, 3, -4, -3, 0)
  -> runtime action carries execution evidence and original decision_trace
  -> strategy feedback accepts only explicit strategy_usage claims
  -> duplicate feedback for the same task is idempotent
  -> a subsequent MissionPlanner plan can retrieve the persisted strategy
```

## Evidence in tests

| Stage | Regression test | What it establishes |
| --- | --- | --- |
| Planning trace | `tests/test_mission_simple_task_analysis.py` | Input, capability, knowledge, strategy, status, and workforce decisions are recorded in order. Planning-only; no worker executes. |
| Runtime dispatch and execution | `tests/test_mission_simple_task_execution.py` | The runtime authorization contract is enforced; the deterministic test adapter executes edge-case assertions; action retains decision trace and execution evidence. |
| Failure lineage | `tests/test_mission_failure_learning_evidence.py` | Failure-learning records preserve Mission run, source task, node, decision trace, and dispatch authorization. |
| Strategy feedback and reuse | `tests/test_mission_strategy_feedback.py` | Explicit usage is recorded once, recommendations alone do not count as use, unverified worker claims are not promoted to independent verification, and persisted strategy feedback is retrievable by a later plan. |

## Latest observed CI evidence

- Commit: `698d8b461ca4075eb360db2d093785cc4f526c1d`
- Workflow: [Python regression tests](https://github.com/xinghunbuxiu/evo-agent/actions/runs/40712812354)
- Result: passed
- Regression suite output: `Ran 121 tests`, `OK`
- Relevant tests in that run: runtime execution smoke test, failure-learning lineage tests, strategy feedback and subsequent-plan retrieval tests.

## Boundaries and remaining work

1. The execution smoke test uses a deterministic test double, not an LLM or production worker.
2. The current evidence demonstrates connected mechanisms across separate regression tests; it is not yet one single test that carries the exact same task/action record through execution, persisted feedback, and the next plan.
3. Worker-reported verification remains untrusted unless independent verification evidence is produced.
4. Do not treat a saved candidate, an execution log, or a worker claim as a promoted verified skill. Promotion needs its own evidence and policy checks.

## Next verification increment

Add a single integration regression test that seeds a strategy, dispatches a task through Mission runtime, records explicit usage tied to the resulting task evidence, reloads persisted state, and asserts that the next Mission plan retrieves that same strategy. Keep the deterministic worker label explicit so the test cannot be mistaken for production AI capability.
