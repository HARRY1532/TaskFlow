import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.requirement_matching import recommend_tasks
from ..db import get_db
from ..models import Requirement, RequirementTask, Task, User
from ..permissions import project_member, project_owner
from ..schemas import RequirementIn, RequirementLinksIn, RequirementMatchOut, RequirementOut
from ..security import current_user

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["需求"])


def get_requirement(db: Session, project_id: int, requirement_id: int) -> Requirement:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None or requirement.project_id != project_id:
        raise HTTPException(404, "需求不存在")
    return requirement


def as_output(db: Session, requirement: Requirement) -> RequirementOut:
    task_ids = db.scalars(select(RequirementTask.task_id).where(
        RequirementTask.requirement_id == requirement.id
    ).order_by(RequirementTask.id)).all()
    return RequirementOut.model_validate({
        "id": requirement.id,
        "project_id": requirement.project_id,
        "title": requirement.title,
        "description": requirement.description,
        "acceptance_criteria": requirement.acceptance_criteria,
        "priority": requirement.priority,
        "status": requirement.status,
        "task_ids": task_ids,
        "created_at": requirement.created_at,
        "updated_at": requirement.updated_at,
    })


def matching_context(db: Session, requirement: Requirement) -> tuple[dict, str]:
    linked_ids = set(db.scalars(select(RequirementTask.task_id).where(
        RequirementTask.requirement_id == requirement.id
    )).all())
    tasks = db.scalars(select(Task).where(Task.project_id == requirement.project_id).order_by(Task.id)).all()
    context = {
        "requirement": {
            "title": requirement.title,
            "description": requirement.description[:3000],
            "acceptance_criteria": requirement.acceptance_criteria[:2000],
            "priority": requirement.priority,
            "status": requirement.status,
            "updated_at": requirement.updated_at.isoformat(),
        },
        "linked_task_ids": sorted(linked_ids),
        "tasks": [{
            "id": task.id,
            "title": task.title,
            "description": task.description[:1200],
            "acceptance_criteria": task.acceptance_criteria[:800],
            "status": task.status,
            "updated_at": task.updated_at.isoformat(),
        } for task in tasks],
    }
    signature = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return context, signature


@router.get("", response_model=list[RequirementOut])
def list_requirements(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    rows = db.scalars(select(Requirement).where(
        Requirement.project_id == project_id
    ).order_by(Requirement.created_at, Requirement.id)).all()
    return [as_output(db, row) for row in rows]


@router.post("", response_model=RequirementOut, status_code=201)
def create_requirement(project_id: int, data: RequirementIn,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    requirement = Requirement(project_id=project_id, **data.model_dump())
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return as_output(db, requirement)


@router.put("/{requirement_id}", response_model=RequirementOut)
def update_requirement(project_id: int, requirement_id: int, data: RequirementIn,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    requirement = get_requirement(db, project_id, requirement_id)
    for key, value in data.model_dump().items():
        setattr(requirement, key, value)
    db.commit()
    db.refresh(requirement)
    return as_output(db, requirement)


@router.post("/{requirement_id}/recommendations", response_model=RequirementMatchOut)
async def suggest_requirement_tasks(project_id: int, requirement_id: int,
                                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    requirement = get_requirement(db, project_id, requirement_id)
    if requirement.status == "archived":
        raise HTTPException(409, "已归档需求不能生成关联建议")
    context, signature = matching_context(db, requirement)
    if len(context["tasks"]) > 50:
        raise HTTPException(422, "当前项目超过 50 项任务，请先整理任务后再生成关联建议")
    linked_ids = set(context["linked_task_ids"])
    candidates = [task for task in context["tasks"] if task["id"] not in linked_ids]
    if not candidates:
        raise HTTPException(422, "没有尚未关联的任务可供推荐")
    suggestion = await recommend_tasks({
        "requirement": {key: value for key, value in context["requirement"].items() if key != "updated_at"},
        "candidate_tasks": [{key: value for key, value in task.items() if key != "updated_at"}
                            for task in candidates],
    })
    db.expire_all()
    project_owner(db, project_id, user)
    requirement = get_requirement(db, project_id, requirement_id)
    if matching_context(db, requirement)[1] != signature:
        raise HTTPException(409, "需求或任务在生成期间已变化，请重新生成建议")
    candidate_ids = {task["id"] for task in candidates}
    recommended_ids = [item.task_id for item in suggestion.recommendations]
    if len(recommended_ids) != len(set(recommended_ids)) or any(task_id not in candidate_ids for task_id in recommended_ids):
        raise HTTPException(502, "AI 返回了无效或重复的任务，请重新生成建议")
    return RequirementMatchOut(**suggestion.model_dump(), context_signature=signature)


@router.put("/{requirement_id}/tasks", response_model=RequirementOut)
def set_requirement_tasks(project_id: int, requirement_id: int, data: RequirementLinksIn,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    requirement = get_requirement(db, project_id, requirement_id)
    if data.expected_signature and matching_context(db, requirement)[1] != data.expected_signature:
        raise HTTPException(409, "需求或任务已变化，请重新查看并生成建议")
    if len(data.task_ids) != len(set(data.task_ids)):
        raise HTTPException(422, "关联任务不能重复")
    valid_ids = set(db.scalars(select(Task.id).where(
        Task.project_id == project_id, Task.id.in_(data.task_ids)
    )).all()) if data.task_ids else set()
    if valid_ids != set(data.task_ids):
        raise HTTPException(422, "只能关联当前项目中存在的任务")
    existing = db.scalars(select(RequirementTask).where(
        RequirementTask.requirement_id == requirement_id
    )).all()
    for link in existing:
        db.delete(link)
    db.flush()
    for task_id in data.task_ids:
        db.add(RequirementTask(requirement_id=requirement_id, task_id=task_id))
    db.commit()
    return as_output(db, requirement)


@router.delete("/{requirement_id}", status_code=204)
def delete_requirement(project_id: int, requirement_id: int,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    requirement = get_requirement(db, project_id, requirement_id)
    db.delete(requirement)
    db.commit()
