import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.videos import _task_response
from app.core.database import get_db
from app.models import AnalysisTask
from app.models.enums import TaskStatus
from app.schemas.tasks import TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


def should_close_task_stream(status: TaskStatus, *, once: bool) -> bool:
    return once or status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_response(task)


@router.get("/{task_id}/events")
async def task_events(
    task_id: str,
    request: Request,
    once: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    if db.get(AnalysisTask, task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def generate() -> AsyncIterator[dict[str, str]]:
        last_payload = ""
        while True:
            db.expire_all()
            task = db.get(AnalysisTask, task_id)
            if task is None:
                yield {"event": "error", "data": '{"detail":"task not found"}'}
                return
            payload = _task_response(task).model_dump(mode="json")
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if serialized != last_payload:
                yield {"event": "status", "data": serialized}
                last_payload = serialized
            if should_close_task_stream(task.status, once=once):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(1)

    return EventSourceResponse(generate())
