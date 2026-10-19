from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, ProjectMember, Task, User


def project_member(db: Session, project_id: int, user: User) -> ProjectMember:
    membership = db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
    ))
    if membership is None:
        raise HTTPException(404, "项目不存在")
    return membership


def project_owner(db: Session, project_id: int, user: User) -> Project:
    project_member(db, project_id, user)
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(403, "仅项目负责人可执行此操作")
    return project


def project_task(db: Session, project_id: int, task_id: int, user: User) -> Task:
    project_member(db, project_id, user)
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(404, "任务不存在")
    return task


def valid_assignee(db: Session, project_id: int, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    membership = db.scalar(select(ProjectMember).join(User, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == assignee_id,
        User.is_active.is_(True),
    ))
    if membership is None:
        raise HTTPException(422, "任务执行人必须是有效的项目成员")
