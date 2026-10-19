from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.analytics_rules import BEIJING_TIMEZONE, build_project_analytics
from ..db import get_db
from ..models import ProjectMember, Task, TaskEvent, TaskWeight, User
from ..permissions import project_member
from ..schemas import ProjectAnalytics
from ..security import current_user


router = APIRouter(prefix="/projects/{project_id}/analytics", tags=["项目数据分析"])


@router.get("", response_model=ProjectAnalytics)
def project_analytics(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    tasks = db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id)).all()
    task_ids = [task.id for task in tasks]
    current_members = db.scalars(select(User).join(ProjectMember, ProjectMember.user_id == User.id)
                                 .where(ProjectMember.project_id == project_id).order_by(User.id)).all()
    known_ids = {member.id for member in current_members}
    departed_ids = {task.assignee_id for task in tasks if task.assignee_id is not None} - known_ids
    departed = db.scalars(select(User).where(User.id.in_(departed_ids)).order_by(User.id)).all() if departed_ids else []
    weights = db.scalars(select(TaskWeight).where(TaskWeight.task_id.in_(task_ids))).all() if task_ids else []
    events = db.scalars(select(TaskEvent).where(TaskEvent.task_id.in_(task_ids),
                                                 TaskEvent.action == "accepted")).all() if task_ids else []
    return build_project_analytics(tasks, [*current_members, *departed], weights, events,
                                   datetime.now(BEIJING_TIMEZONE).date())
