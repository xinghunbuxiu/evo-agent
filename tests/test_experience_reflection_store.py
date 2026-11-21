"""Tests for tenant-bound append-only Experience Reflection persistence."""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import Experience, ExperienceStore
from core.experience_reflection import ExperienceReflectionStore


class ExperienceReflectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.tenant_store = ExperienceStore(self.workspace, "tenant-a")
        self.source = Experience(
            id="source-exp-1",
            domain="android",
            task_type="analysis",
            input_summary="device diagnostics",
            output_summary="IMS registration checked",
            quality_score=0.8,
            metadata={"mission_run_id": "run-1", "evidence_ids": ["evidence-1"]},
        )
        self.tenant_store.save(self.source)
        self.store = ExperienceReflectionStore(self.workspace, "tenant-a")

    def tearDown(self):
        self.temp_dir.cleanup()

    def append(self, *, key="request-1", findings=None, refs=None):
        return self.store.append(
            self.source.id,
            author="tenant-member-1",
            findings=findings or {"observed_outcome": "IMS registration was unavailable"},
            source_evidence_refs=refs if refs is not None else ["evidence-1"],
            idempotency_key=key,
        )

    def test_append_creates_tenant_scoped_experience_and_preserves_source(self):
        before = self.tenant_store.load_by_domain("android")[0].to_dict()
        reflection = self.append()
        after = self.tenant_store.load_by_domain("android")[0].to_dict()
        self.assertEqual(before, after)
        self.assertEqual(reflection.domain, "reflection")
        self.assertEqual(reflection.task_type, "experience_reflection")
        self.assertEqual(reflection.metadata["experience_reflection"]["tenant_id"], "tenant-a")
        projection = self.workspace / ".tenants/tenant-a/experiences/reflection" / f"{reflection.id}.json"
        self.assertTrue(projection.is_file())
        outbox = self.workspace / ".tenants/tenant-a/experience_outbox/pending"
        self.assertEqual(len(list(outbox.glob("*.json"))), 2)

    def test_identical_idempotency_retry_returns_original_revision(self):
        first = self.append()
        retry = self.append()
        self.assertEqual(first.id, retry.id)
        self.assertEqual(retry.metadata["experience_reflection"]["revision"], 1)
        self.assertEqual(len(self.store.list_for_source(self.source.id)), 1)

    def test_idempotency_key_reuse_with_different_content_fails_closed(self):
        self.append()
        with self.assertRaisesRegex(ValueError, "different Reflection content"):
            self.append(findings={"observed_outcome": "A different interpretation"})

    def test_new_revision_links_to_previous_and_never_reuses_its_id(self):
        first = self.append()
        second = self.append(key="request-2", findings={"observed_outcome": "Follow-up observation"})
        first_payload = first.metadata["experience_reflection"]
        second_payload = second.metadata["experience_reflection"]
        self.assertEqual(second_payload["revision"], 2)
        self.assertEqual(second_payload["parent_reflection_id"], first.id)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual([item.id for item in self.store.list_for_source(self.source.id)], [first.id, second.id])
        self.assertEqual(first_payload["state"], "pending")

    def test_rejects_evidence_reference_not_attached_to_source(self):
        with self.assertRaisesRegex(ValueError, "not attached"):
            self.append(refs=["unrelated-evidence"])

    def test_source_digest_change_blocks_new_reflection_revision(self):
        self.append()
        changed_source = Experience(
            id=self.source.id,
            domain=self.source.domain,
            task_type=self.source.task_type,
            input_summary=self.source.input_summary,
            output_summary="Source observation was modified",
            quality_score=self.source.quality_score,
            metadata=self.source.metadata,
            created_at=self.source.created_at,
        )
        self.tenant_store.save(changed_source)
        with self.assertRaisesRegex(ValueError, "source Experience digest changed"):
            self.append(key="request-after-source-change")

    def test_tenant_cannot_submit_reflection_for_another_tenants_source(self):
        other_tenant = ExperienceReflectionStore(self.workspace, "tenant-b")
        with self.assertRaisesRegex(ValueError, "does not exist or is ambiguous"):
            other_tenant.append(
                self.source.id,
                author="tenant-b-member",
                findings={"observed_outcome": "cross tenant"},
                idempotency_key="tenant-b-request",
            )

    def test_concurrent_appends_allocate_unique_ordered_revisions(self):
        def submit(index):
            return self.append(
                key=f"concurrent-{index}",
                findings={"observed_outcome": f"observation-{index}"},
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(submit, range(6)))
        records = self.store.list_for_source(self.source.id)
        self.assertEqual(len({item.id for item in results}), 6)
        self.assertEqual(
            [item.metadata["experience_reflection"]["revision"] for item in records],
            [1, 2, 3, 4, 5, 6],
        )
        for index, item in enumerate(records):
            payload = item.metadata["experience_reflection"]
            expected_parent = records[index - 1].id if index else None
            self.assertEqual(payload["parent_reflection_id"], expected_parent)

    def test_decision_is_a_separate_append_only_record(self):
        reflection = self.append()
        original = reflection.to_dict()
        decision = self.store.decide(
            reflection.id,
            reviewer="tenant-admin-2",
            decision="accepted",
            idempotency_key="review-request-1",
        )
        self.assertEqual(decision.domain, "reflection_decision")
        self.assertEqual(decision.task_type, "experience_reflection_decision")
        self.assertEqual(reflection.to_dict(), original)
        listed = self.store.list_reviewed_for_source(self.source.id)
        self.assertEqual(listed[0]["effective_state"], "accepted")
        self.assertEqual(listed[0]["reflection"]["id"], reflection.id)
        self.assertEqual(listed[0]["reflection"]["metadata"]["experience_reflection"]["state"], "pending")

    def test_reflection_author_cannot_review_own_submission(self):
        reflection = self.append()
        with self.assertRaisesRegex(ValueError, "cannot review their own"):
            self.store.decide(
                reflection.id,
                reviewer="tenant-member-1",
                decision="accepted",
                idempotency_key="review-self",
            )

    def test_source_digest_change_blocks_review_decision(self):
        reflection = self.append()
        changed_source = Experience(
            id=self.source.id,
            domain=self.source.domain,
            task_type=self.source.task_type,
            input_summary=self.source.input_summary,
            output_summary="Source changed after Reflection",
            quality_score=self.source.quality_score,
            metadata=self.source.metadata,
            created_at=self.source.created_at,
        )
        self.tenant_store.save(changed_source)
        with self.assertRaisesRegex(ValueError, "source Experience digest changed"):
            self.store.decide(
                reflection.id,
                reviewer="tenant-admin-2",
                decision="accepted",
                idempotency_key="review-after-source-change",
            )

    def test_listing_all_sources_returns_tenant_review_queue(self):
        first = self.append()
        other_source = Experience(
            id="source-exp-2",
            domain="ios",
            task_type="analysis",
            input_summary="other source",
            output_summary="other result",
            quality_score=0.7,
            metadata={"evidence_ids": ["evidence-2"]},
        )
        self.tenant_store.save(other_source)
        second = self.store.append(
            other_source.id,
            author="tenant-member-2",
            findings={"observed_outcome": "Other source observation"},
            source_evidence_refs=["evidence-2"],
            idempotency_key="request-other-source",
        )
        self.assertEqual(
            {item["reflection"]["id"] for item in self.store.list_reviewed_for_source()},
            {first.id, second.id},
        )

    def test_listing_one_source_ignores_decisions_for_other_sources(self):
        first = self.append()
        other_source = Experience(
            id="source-exp-2",
            domain="ios",
            task_type="analysis",
            input_summary="other source",
            output_summary="other result",
            quality_score=0.7,
            metadata={"evidence_ids": ["evidence-2"]},
        )
        self.tenant_store.save(other_source)
        second = self.store.append(
            other_source.id,
            author="tenant-member-2",
            findings={"observed_outcome": "Other source observation"},
            source_evidence_refs=["evidence-2"],
            idempotency_key="request-other-source",
        )
        self.store.decide(
            second.id,
            reviewer="tenant-admin-2",
            decision="accepted",
            idempotency_key="review-other-source",
        )
        listed = self.store.list_reviewed_for_source(self.source.id)
        self.assertEqual([item["reflection"]["id"] for item in listed], [first.id])

    def test_decision_requires_reason_for_rejection(self):
        reflection = self.append()
        with self.assertRaisesRegex(ValueError, "requires a reason"):
            self.store.decide(
                reflection.id,
                reviewer="tenant-admin-2",
                decision="rejected",
                idempotency_key="review-reject-no-reason",
            )

    def test_decision_retry_is_idempotent_and_conflicting_second_decision_is_rejected(self):
        reflection = self.append()
        first = self.store.decide(
            reflection.id,
            reviewer="tenant-admin-2",
            decision="rejected",
            reason="Evidence does not support the conclusion",
            idempotency_key="review-request-2",
        )
        retry = self.store.decide(
            reflection.id,
            reviewer="tenant-admin-2",
            decision="rejected",
            reason="Evidence does not support the conclusion",
            idempotency_key="review-request-2",
        )
        self.assertEqual(first.id, retry.id)
        with self.assertRaisesRegex(ValueError, "already received"):
            self.store.decide(
                reflection.id,
                reviewer="tenant-admin-3",
                decision="accepted",
                idempotency_key="review-request-3",
            )

    def test_retry_recovers_projection_after_outbox_was_written(self):
        first = self.append()
        projection = self.workspace / ".tenants/tenant-a/experiences/reflection" / f"{first.id}.json"
        projection.unlink()
        recovered = self.append()
        self.assertEqual(recovered.id, first.id)
        self.assertTrue(projection.is_file())
        data = json.loads(projection.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], first.id)


if __name__ == "__main__":
    unittest.main()
