from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, ProjectActivity, ProjectActivityRead, ProjectMember, Task, TaskEvent, User
from ..schemas import AdminCreateUserIn, AdminUserOut, UserOut
from ..security import current_user, password_hash

router = APIRouter(prefix="/admin/users", tags=["系统管理员"])


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "仅系统管理员可执行此操作")
    return user


def admin_user_out(db: Session, user: User, admin_id: int) -> AdminUserOut:
    activity_count = db.scalar(select(func.count(ProjectActivity.id)).where(ProjectActivity.actor_id == user.id)) or 0
    unread_count = db.scalar(select(func.count(ProjectActivity.id)).outerjoin(
        ProjectActivityRead,
        (ProjectActivityRead.activity_id == ProjectActivity.id) &
        (ProjectActivityRead.admin_id == admin_id),
    ).where(ProjectActivity.actor_id == user.id, ProjectActivityRead.id.is_(None))) or 0
    return AdminUserOut(
        **UserOut.model_validate(user).model_dump(),
        project_activity_count=activity_count,
        unread_project_activity_count=unread_count,
    )


@router.get("", response_model=list[AdminUserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [admin_user_out(db, user, admin.id) for user in users]


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    return admin_user_out(db, user, admin.id)


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: AdminCreateUserIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "邮箱已存在；停用账号可以恢复")
    user = User(email=email, name=data.name, password_hash=password_hash.hash(data.password), is_admin=data.is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserOut)
def deactivate_user(user_id: int, successor_user_id: int | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(409, "不能停用当前登录的管理员")
    owned_projects = db.scalars(select(Project).where(Project.owner_id == user.id)).all()
    if owned_projects and successor_user_id is None:
        raise HTTPException(409, "该用户仍是项目负责人，请选择接任项目负责人")
    if owned_projects:
        successor = db.get(User, successor_user_id)
        if successor is None or not successor.is_active or successor.id == user.id:
            raise HTTPException(422, "接任项目负责人必须是其他有效用户")
        for project in owned_projects:
            current_member = db.scalar(select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            ))
            if current_member:
                current_member.role = "member"
            successor_member = db.scalar(select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == successor.id,
            ))
            if successor_member:
                successor_member.role = "owner"
            else:
                db.add(ProjectMember(project_id=project.id, user_id=successor.id, role="owner"))
            project.owner_id = successor.id
    open_tasks = db.scalars(select(Task).where(
        Task.assignee_id == user.id,
        Task.status != "done",
    )).all()
    for task in open_tasks:
        task.assignee_id = None
        db.add(TaskEvent(
            task_id=task.id, actor_id=admin.id,
            action="unassigned", note="原任务执行人账号已停用，请重新分配",
        ))
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/restore", response_model=UserOut)
def restore_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user
