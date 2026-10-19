from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ProjectActivity, ProjectActivityRead, User
from ..schemas import ProjectActivityOut
from .admin import require_admin

router = APIRouter(prefix="/admin/project-activities", tags=["管理员通知"])
user_router = APIRouter(prefix="/admin/users", tags=["用户项目记录"])


def as_output(db: Session, activity: ProjectActivity, admin_id: int) -> ProjectActivityOut:
    actor = db.get(User, activity.actor_id)
    read = db.scalar(select(ProjectActivityRead).where(
        ProjectActivityRead.activity_id == activity.id,
        ProjectActivityRead.admin_id == admin_id,
    ))
    return ProjectActivityOut(
        id=activity.id, project_id=activity.project_id,
        project_name=activity.project_name,
        actor_name=actor.name if actor else "已删除用户",
        action=activity.action, created_at=activity.created_at,
        is_read=read is not None,
    )


@router.get("", response_model=list[ProjectActivityOut])
def list_activities(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ProjectActivity).order_by(ProjectActivity.id.desc())).all()
    return [as_output(db, row, admin.id) for row in rows]


@user_router.get("/{user_id}/project-activities", response_model=list[ProjectActivityOut])
def user_activities(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(404, "用户不存在")
    rows = db.scalars(select(ProjectActivity).where(
        ProjectActivity.actor_id == user_id
    ).order_by(ProjectActivity.id.desc())).all()
    return [as_output(db, row, admin.id) for row in rows]


@router.get("/unread-count")
def unread_count(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(ProjectActivity.id)).outerjoin(
        ProjectActivityRead,
        (ProjectActivityRead.activity_id == ProjectActivity.id) &
        (ProjectActivityRead.admin_id == admin.id),
    ).where(ProjectActivityRead.id.is_(None)))
    return {"count": count or 0}


@router.post("/{activity_id}/read", response_model=ProjectActivityOut)
def mark_read(activity_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    activity = db.get(ProjectActivity, activity_id)
    if activity is None:
        raise HTTPException(404, "通知不存在")
    existing = db.scalar(select(ProjectActivityRead).where(
        ProjectActivityRead.activity_id == activity_id,
        ProjectActivityRead.admin_id == admin.id,
    ))
    if existing is None:
        db.add(ProjectActivityRead(activity_id=activity_id, admin_id=admin.id))
        db.commit()
    return as_output(db, activity, admin.id)
