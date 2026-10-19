from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..analysis.dependencies import validate_dependency_graph
from ..db import get_db
from ..models import Task, TaskDependency, User
from ..permissions import project_member, project_owner, project_task
from ..schemas import TaskDependenciesIn, TaskDependenciesOut
from ..security import current_user

router = APIRouter(prefix="/projects/{project_id}", tags=["任务依赖"])


@router.get("/dependencies", response_model=list[TaskDependenciesOut])
def list_dependencies(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    tasks = db.scalars(select(Task.id).where(Task.project_id == project_id).order_by(Task.id)).all()
    dependencies = db.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_id)
        .join(Task, TaskDependency.task_id == Task.id)
        .where(Task.project_id == project_id)
    ).all()
    graph = {task_id: [] for task_id in tasks}
    for task_id, prerequisite in dependencies:
        graph[task_id].append(prerequisite)
    return [TaskDependenciesOut(task_id=task_id, depends_on_ids=graph[task_id]) for task_id in tasks]


@router.put("/tasks/{task_id}/dependencies", response_model=TaskDependenciesOut)
def set_dependencies(project_id: int, task_id: int, data: TaskDependenciesIn,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    if task.status != "todo":
        raise HTTPException(409, "只有待开始任务可以修改依赖")
    validate_dependency_graph(db, project_id, {task_id: data.depends_on_ids})
    db.execute(delete(TaskDependency).where(TaskDependency.task_id == task_id))
    db.add_all(TaskDependency(task_id=task_id, depends_on_id=item) for item in data.depends_on_ids)
    db.commit()
    return TaskDependenciesOut(task_id=task_id, depends_on_ids=data.depends_on_ids)
