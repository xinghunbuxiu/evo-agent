"""Tests for append-only Experience Reflection contract primitives."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import Experience
from core.experience_reflection import (
    build_pending_reflection,
    canonical_experience_digest,
    validate_reflection_payload,
)


class ExperienceReflectionContractTests(unittest.TestCase):
    def make_source(self):
        return Experience(
            id="mission-exp-1",
            domain="android",
            task_type="analysis",
            input_summary="device diagnostics",
            output_summary="IMS registration checked",
            quality_score=0.8,
            metadata={"mission_run_id": "run-1"},
        )

    def test_builder_creates_separate_pending_reflection_with_source_digest(self):
        source = self.make_source()
        reflection = build_pending_reflection(
            source,
            tenant_id="tenant-a",
            author="reviewer-candidate",
            findings={"observed_outcome": "IMS registration was not available"},
            source_evidence_refs=["broker-evidence-1"],
            idempotency_key="request-1",
        )
        payload = reflection.metadata["experience_reflection"]
        self.assertEqual(reflection.domain, "reflection")
        self.assertEqual(reflection.task_type, "experience_reflection")
        self.assertEqual(reflection.quality_score, 0.0)
        self.assertEqual(payload["state"], "pending")
        self.assertEqual(payload["source_experience_digest"], canonical_experience_digest(source))
        self.assertEqual(payload["source_experience_id"], source.id)
        self.assertNotEqual(reflection.id, source.id)
        validate_reflection_payload(payload, expected_tenant_id="tenant-a", require_pending=True)

    def test_builder_rejects_invalid_revision_parent_relationship(self):
        with self.assertRaisesRegex(ValueError, "require a parent"):
            build_pending_reflection(
                self.make_source(), tenant_id="tenant-a", author="actor",
                findings={}, revision=2, idempotency_key="request-2",
            )

    def test_builder_rejects_empty_evidence_reference(self):
        with self.assertRaisesRegex(ValueError, "source_evidence_refs"):
            build_pending_reflection(
                self.make_source(), tenant_id="tenant-a", author="actor",
                findings={}, source_evidence_refs=[" "], idempotency_key="request-3",
            )

    def test_builder_rejects_empty_findings(self):
        with self.assertRaisesRegex(ValueError, "findings must not be empty"):
            build_pending_reflection(
                self.make_source(), tenant_id="tenant-a", author="actor",
                findings={}, idempotency_key="request-empty-findings",
            )

    def test_validator_rejects_cross_tenant_reflection(self):
        reflection = build_pending_reflection(
            self.make_source(), tenant_id="tenant-a", author="actor",
            findings={"observed_outcome": "Observed"}, idempotency_key="request-4",
        )
        with self.assertRaisesRegex(ValueError, "tenant mismatch"):
            validate_reflection_payload(
                reflection.metadata["experience_reflection"],
                expected_tenant_id="tenant-b",
            )

    def test_validator_rejects_pending_record_with_decision_provenance(self):
        reflection = build_pending_reflection(
            self.make_source(), tenant_id="tenant-a", author="actor",
            findings={"observed_outcome": "Observed"}, idempotency_key="request-5",
        )
        payload = dict(reflection.metadata["experience_reflection"])
        payload["reviewer"] = {"actor": "actor-2"}
        with self.assertRaisesRegex(ValueError, "cannot contain reviewer"):
            validate_reflection_payload(payload, expected_tenant_id="tenant-a")

    def test_validator_requires_rejection_reason_and_reviewer(self):
        reflection = build_pending_reflection(
            self.make_source(), tenant_id="tenant-a", author="actor",
            findings={"observed_outcome": "Observed"}, idempotency_key="request-6",
        )
        payload = dict(reflection.metadata["experience_reflection"])
        payload.update({
            "state": "rejected",
            "reviewer": {"actor": "reviewer-2"},
            "decision_at": "2026-11-13T10:00:00+00:00",
        })
        with self.assertRaisesRegex(ValueError, "decision_reason"):
            validate_reflection_payload(payload, expected_tenant_id="tenant-a")


if __name__ == "__main__":
    unittest.main()
