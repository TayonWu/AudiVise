from app.models.enums import TaskStatus


class InvalidTaskTransition(ValueError):
    pass


_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {TaskStatus.PROBING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.PROBING: frozenset(
        {TaskStatus.EXTRACTING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.EXTRACTING: frozenset(
        {TaskStatus.TRANSCRIBING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.TRANSCRIBING: frozenset(
        {TaskStatus.INDEXING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.INDEXING: frozenset(
        {TaskStatus.SUMMARIZING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.SUMMARIZING: frozenset(
        {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def ensure_transition(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    if target not in _TRANSITIONS[current]:
        raise InvalidTaskTransition(f"cannot transition task from {current} to {target}")
    return target

