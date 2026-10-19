from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..github import inspect_code
from ..models import Project, Task, TaskDependency, TaskEvent, TaskWeight, User
from ..permissions import project_member, project_owner, project_task, valid_assignee
from ..schemas import ChecklistItem, ChecklistUpdateIn, DecisionIn, EvidenceIn, TaskEventOut, TaskIn, TaskOut, TaskUpdate
from ..security import current_user
from ..agent.development import generate_development_checklist

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["任务"])


def log_event(db: Session, task: Task, user: User, action: str, note: str = ""):
    db.add(TaskEvent(task_id=task.id, actor_id=user.id, action=action, note=note))


@router.get("", response_model=list[TaskOut])
def list_tasks(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    return db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc())).all()


@router.post("", response_model=TaskOut, status_code=201)
def create_task(project_id: int, data: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    valid_assignee(db, project_id, data.assignee_id)
    task = Task(project_id=project_id, **data.model_dump())
    db.add(task)
    db.flush()
    log_event(db, task, user, "created")
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(project_id: int, task_id: int, data: TaskUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    changes = data.model_dump(exclude_unset=True)
    for required in ("title", "description", "priority", "acceptance_criteria", "required_skills"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} 不能为空")
    if "assignee_id" in changes:
        valid_assignee(db, project_id, changes["assignee_id"])
    if "estimated_hours" in changes and changes["estimated_hours"] != task.estimated_hours:
        weight = db.get(TaskWeight, task.id)
        if weight is not None:
            db.delete(weight)
            log_event(db, task, user, "weight_invalidated", "预计工时已修改，请重新评估权重")
    for key, value in changes.items():
        setattr(task, key, value)
    if changes:
        log_event(db, task, user, "updated", ", ".join(changes))
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(project_id: int, task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    db.delete(task)
    db.commit()


@router.post("/{task_id}/start", response_model=TaskOut)
def start_task(project_id: int, task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    if task.assignee_id != user.id:
        raise HTTPException(403, "仅任务执行人可开始任务")
    if task.status != "todo":
        raise HTTPException(409, "当前状态不能开始")
    blocked = db.scalar(select(Task.id).join(
        TaskDependency, TaskDependency.depends_on_id == Task.id
    ).where(TaskDependency.task_id == task.id, Task.status != "done"))
    if blocked is not None:
        raise HTTPException(409, "前置任务尚未完成，当前任务不能开始")
    task.status = "in_progress"
    log_event(db, task, user, "started")
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/submit", response_model=TaskOut)
def submit_task(project_id: int, task_id: int, data: EvidenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    if task.assignee_id != user.id:
        raise HTTPException(403, "仅任务执行人可提交成果")
    if task.status != "in_progress":
        raise HTTPException(409, "请先开始任务")
    project = db.get(Project, project_id)
    code_metadata = inspect_code(str(data.code_url), project.github_repo_url) if data.code_url and project.github_repo_url else None
    task.evidence_note = data.note.strip() if data.note else None
    task.evidence_url = str(data.url) if data.url else None
    task.code_url = str(data.code_url) if data.code_url else None
    task.code_metadata = code_metadata
    task.test_url = str(data.test_url) if data.test_url else None
    task.test_note = data.test_note.strip() if data.test_note else None
    task.status = "review"
    log_event(db, task, user, "submitted", task.evidence_note or task.evidence_url or task.code_url or task.test_url or task.test_note or "")
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/code-evidence/refresh", response_model=TaskOut)
def refresh_code_evidence(project_id: int, task_id: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    project = db.get(Project, project_id)
    if user.id not in (project.owner_id, task.assignee_id):
        raise HTTPException(403, "仅项目负责人或任务执行人可核验代码成果")
    if not task.code_url or not project.github_repo_url:
        raise HTTPException(409, "请先绑定项目仓库并提交代码链接")
    task.code_metadata = inspect_code(task.code_url, project.github_repo_url)
    log_event(db, task, user, "code_verified", "已重新核验 GitHub 代码链接")
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/development-checklist/generate", response_model=list[ChecklistItem])
async def generate_checklist(project_id: int, task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    project = db.get(Project, project_id)
    if user.id not in (project.owner_id, task.assignee_id):
        raise HTTPException(403, "仅项目负责人或任务执行人可生成开发清单")
    if task.status in ("review", "done"):
        raise HTTPException(409, "待验收或已完成任务不能重新生成清单")
    original = (task.title, task.description, task.acceptance_criteria, task.updated_at)
    items = await generate_development_checklist({
        "project_goal": project.goal[:2000], "tech_stack": project.tech_stack,
        "task_title": task.title, "task_description": task.description[:3000],
        "acceptance_criteria": task.acceptance_criteria[:2000],
    })
    db.refresh(task)
    if ((task.title, task.description, task.acceptance_criteria, task.updated_at) != original
            or task.status in ("review", "done")
            or user.id not in (project.owner_id, task.assignee_id)):
        raise HTTPException(409, "任务在生成期间已变化，请重新生成")
    task.development_checklist = [item.model_dump() for item in items]
    log_event(db, task, user, "checklist_generated", f"生成 {len(items)} 项开发清单")
    db.commit()
    return items


@router.put("/{task_id}/development-checklist", response_model=list[ChecklistItem])
def update_checklist(project_id: int, task_id: int, data: ChecklistUpdateIn,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    if task.assignee_id != user.id:
        raise HTTPException(403, "仅任务执行人可更新开发清单")
    if task.status != "in_progress":
        raise HTTPException(409, "仅进行中的任务可更新开发清单")
    current = task.development_checklist or []
    if not current or len(current) != len(data.items) or any(
        (item.title, item.detail, item.kind) != (old["title"], old["detail"], old["kind"])
        for item, old in zip(data.items, current)
    ):
        raise HTTPException(409, "清单内容已变化，请刷新页面")
    task.development_checklist = [item.model_dump() for item in data.items]
    log_event(db, task, user, "checklist_updated", f"已完成 {sum(item.checked for item in data.items)}/{len(data.items)} 项")
    db.commit()
    return data.items


@router.post("/{task_id}/accept", response_model=TaskOut)
def accept_task(project_id: int, task_id: int, data: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    if task.status != "review":
        raise HTTPException(409, "任务尚未提交验收")
    task.status = "done"
    log_event(db, task, user, "accepted", data.note)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/reject", response_model=TaskOut)
def reject_task(project_id: int, task_id: int, data: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    if task.status != "review":
        raise HTTPException(409, "任务尚未提交验收")
    if not data.note.strip():
        raise HTTPException(422, "驳回时请说明原因")
    task.status = "in_progress"
    log_event(db, task, user, "rejected", data.note.strip())
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}/events", response_model=list[TaskEventOut])
def task_events(project_id: int, task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_task(db, project_id, task_id, user)
    return db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)).all()
