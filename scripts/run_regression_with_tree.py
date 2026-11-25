#!/usr/bin/env python3
"""Run the complete unittest suite and emit a readable suite/status tree."""
from __future__ import annotations

import sys
import time
import traceback
import unittest
from collections import defaultdict
from typing import Iterable


def iter_cases(suite: unittest.TestSuite) -> Iterable[unittest.case.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_cases(item)
        else:
            yield item


def test_label(test: unittest.case.TestCase) -> str:
    return f"{test.__class__.__module__}.{test.__class__.__name__}.{test._testMethodName}"


class TreeResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_at = {}
        self.outcomes = {}
        self.module_class_counts = defaultdict(lambda: {"pass": 0, "fail": 0, "skip": 0})

    def startTest(self, test):
        super().startTest(test)
        self.started_at[test] = time.monotonic()
        self.stream.writeln(f"[RUN ] {test_label(test)}")
        self.stream.flush()

    def _mark(self, test, outcome):
        elapsed = time.monotonic() - self.started_at.get(test, time.monotonic())
        self.outcomes[test] = outcome
        key = (test.__class__.__module__, test.__class__.__name__)
        bucket = self.module_class_counts[key]
        bucket["pass" if outcome == "PASS" else "skip" if outcome == "SKIP" else "fail"] += 1
        self.stream.writeln(f"[{outcome:<4}] {test_label(test)} ({elapsed:.3f}s)")
        self.stream.flush()

    def addSuccess(self, test):
        super().addSuccess(test)
        self._mark(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._mark(test, "FAIL")

    def addError(self, test, err):
        super().addError(test, err)
        self._mark(test, "ERROR")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._mark(test, "SKIP")


class TreeRunner(unittest.TextTestRunner):
    resultclass = TreeResult


def print_tree(cases):
    grouped = defaultdict(list)
    for case in cases:
        grouped[(case.__class__.__module__, case.__class__.__name__)].append(case)
    print("TEST FLOW TREE")
    print("└── regression suite")
    modules = defaultdict(list)
    for (module, cls), tests in grouped.items():
        modules[module].append((cls, tests))
    for module in sorted(modules):
        print(f"    ├── {module}")
        for cls, tests in sorted(modules[module], key=lambda item: item[0]):
            print(f"    │   ├── {cls} ({len(tests)} tests)")
            for index, case in enumerate(tests):
                branch = "└──" if index == len(tests) - 1 else "├──"
                print(f"    │   │   {branch} {case._testMethodName}")
    print(f"DISCOVERED TESTS: {len(cases)}")
    print("EXECUTION STATUS TREE follows; each test prints RUN then PASS/FAIL/ERROR/SKIP.")
    print("-" * 88)


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests")
    cases = list(iter_cases(suite))
    print_tree(cases)
    runner = TreeRunner(stream=sys.stdout, verbosity=0, failfast=False, buffer=False)
    result = runner.run(suite)
    print("-" * 88)
    print("RESULT TREE")
    print("└── regression suite")
    for (module, cls), counts in sorted(result.module_class_counts.items()):
        total = sum(counts.values())
        print(
            f"    ├── {module}.{cls}: total={total}, "
            f"pass={counts['pass']}, fail={counts['fail']}, skip={counts['skip']}"
        )
    print(
        f"FINAL: tests={result.testsRun}, passed={result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)}, "
        f"failures={len(result.failures)}, errors={len(result.errors)}, skipped={len(result.skipped)}"
    )
    if result.failures or result.errors:
        print("FAILURE DETAILS (full tracebacks)")
        for test, err in [*result.failures, *result.errors]:
            print(f"\n### {test_label(test)}")
            print(err)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
