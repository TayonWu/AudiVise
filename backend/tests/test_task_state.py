import pytest

from app.models.enums import TaskStatus
from app.services.task_state import InvalidTaskTransition, ensure_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TaskStatus.PENDING, TaskStatus.PROBING),
        (TaskStatus.PROBING, TaskStatus.EXTRACTING),
        (TaskStatus.EXTRACTING, TaskStatus.TRANSCRIBING),
        (TaskStatus.TRANSCRIBING, TaskStatus.INDEXING),
        (TaskStatus.INDEXING, TaskStatus.SUMMARIZING),
        (TaskStatus.SUMMARIZING, TaskStatus.SUCCEEDED),
        (TaskStatus.PROBING, TaskStatus.FAILED),
        (TaskStatus.PENDING, TaskStatus.CANCELLED),
    ],
)
def test_allows_defined_task_transitions(current: TaskStatus, target: TaskStatus) -> None:
    assert ensure_transition(current, target) is target


def test_rejects_skipping_pipeline_stages() -> None:
    with pytest.raises(InvalidTaskTransition):
        ensure_transition(TaskStatus.PENDING, TaskStatus.SUCCEEDED)


def test_terminal_task_cannot_restart() -> None:
    with pytest.raises(InvalidTaskTransition):
        ensure_transition(TaskStatus.SUCCEEDED, TaskStatus.PROBING)
