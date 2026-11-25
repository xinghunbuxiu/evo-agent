from admin.trainer_coaching_runtime import record_task_failed_coaching


def test_failed_task_creates_trainer_intervention_card():
    runtime = {
        "child_members": {
            "items": [
                {"member_id": "talent_development_officer", "primary_role": "talent_development"},
                {"member_id": "worker-a", "name": "Worker A", "primary_role": "editor"},
            ]
        }
    }
    card = record_task_failed_coaching(
        runtime,
        coached_member=runtime["child_members"]["items"][1],
        task={"task_id": "task-1", "title": "首轮任务", "task_type": "publish"},
        failure_reason="独立验收失败",
        learning_task_id="learn-1",
    )

    assert card is not None
    assert card["stage"] == "task_failed_intervention"
    assert card["next_experiment"]
    assert "learn-1" in card["evidence"]
    assert "trainer_review_before_worker_retirement" in card["evidence"]


def test_failed_task_coaching_is_idempotent_for_same_task():
    runtime = {
        "child_members": {
            "items": [
                {"member_id": "talent_development_officer", "primary_role": "talent_development"},
                {"member_id": "worker-a", "name": "Worker A", "primary_role": "editor"},
            ]
        }
    }
    member = runtime["child_members"]["items"][1]
    first = record_task_failed_coaching(
        runtime,
        coached_member=member,
        task={"task_id": "task-1", "title": "首轮任务"},
        failure_reason="失败 A",
    )
    second = record_task_failed_coaching(
        runtime,
        coached_member=member,
        task={"task_id": "task-1", "title": "首轮任务"},
        failure_reason="失败 A",
    )

    assert first is not None
    assert second is None
    cards = runtime["child_members"]["items"][0]["experience_journal"]["cards"]
    assert len(cards) == 1
