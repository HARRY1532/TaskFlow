from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Task, TaskDependency


def validate_dependency_graph(db: Session, project_id: int, updates: dict[int, list[int]]) -> None:
    """Reject missing, cross-project, duplicate, self and cyclic prerequisite links."""
    task_ids = set(db.scalars(select(Task.id).where(Task.project_id == project_id)).all())
    graph: dict[int, list[int]] = {task_id: [] for task_id in task_ids}
    for task_id, prerequisite_id in db.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_id)
        .join(Task, TaskDependency.task_id == Task.id)
        .where(Task.project_id == project_id)
    ):
        graph[task_id].append(prerequisite_id)
    for task_id, prerequisites in updates.items():
        if task_id not in task_ids or any(item not in task_ids for item in prerequisites):
            raise HTTPException(422, "依赖任务必须属于当前项目")
        if task_id in prerequisites or len(prerequisites) != len(set(prerequisites)):
            raise HTTPException(422, "依赖不能重复或指向任务自身")
        graph[task_id] = prerequisites
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(task_id: int) -> None:
        if task_id in visiting:
            raise HTTPException(422, "任务依赖不能形成循环")
        if task_id in visited:
            return
        visiting.add(task_id)
        for prerequisite in graph[task_id]:
            visit(prerequisite)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)
