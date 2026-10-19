from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..github import verify_repository
from ..models import Project, ProjectActivity, ProjectMember, Task, TaskEvent, User
from ..permissions import project_member, project_owner
from ..schemas import MemberOut, OwnerTransferIn, ProjectIn, ProjectOut, RepositoryIn, UserOut
from ..security import current_user

router = APIRouter(prefix="/projects", tags=["项目"])


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).join(ProjectMember).where(
        ProjectMember.user_id == user.id
    ).order_by(Project.created_at.desc())).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = Project(**data.model_dump(), owner_id=user.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.add(ProjectActivity(project_id=project.id, project_name=project.name, actor_id=user.id, action="created"))
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    return db.get(Project, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, data: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    for key, value in data.model_dump().items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}/repository", response_model=ProjectOut)
def set_repository(project_id: int, data: RepositoryIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    canonical = verify_repository(data.url) if data.url else None
    linked_urls = db.scalars(select(Task.code_url).where(
        Task.project_id == project_id, Task.code_url.is_not(None)
    )).all()
    if canonical != project.github_repo_url and linked_urls and project.github_repo_url is not None:
        raise HTTPException(409, "已有任务关联代码链接，不能更换或移除项目仓库")
    project.github_repo_url = canonical
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, confirmation: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    if confirmation != project.name:
        raise HTTPException(409, "项目名称确认不一致")
    db.add(ProjectActivity(project_id=project.id, project_name=project.name, actor_id=user.id, action="deleted"))
    db.delete(project)
    db.commit()


@router.put("/{project_id}/owner", response_model=ProjectOut)
def transfer_owner(project_id: int, data: OwnerTransferIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    if data.new_owner_id == user.id:
        raise HTTPException(422, "请选择其他成员")
    next_owner = db.scalar(select(ProjectMember).join(User, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == data.new_owner_id,
        User.is_active.is_(True),
    ))
    if next_owner is None:
        raise HTTPException(422, "新项目负责人必须是有效的项目成员")
    current_owner = db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user.id,
    ))
    current_owner.role = "member"
    next_owner.role = "owner"
    project.owner_id = data.new_owner_id
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    rows = db.execute(select(ProjectMember, User).join(User, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id
    ).order_by(ProjectMember.id)).all()
    return [MemberOut(user=UserOut.model_validate(member_user), role=membership.role)
            for membership, member_user in rows]


@router.delete("/{project_id}/members/me", status_code=204)
def leave_project(project_id: int, confirmation: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership = project_member(db, project_id, user)
    project = db.get(Project, project_id)
    if project.owner_id == user.id:
        raise HTTPException(409, "项目负责人请先转让项目，再退出")
    if confirmation != project.name:
        raise HTTPException(409, "项目名称确认不一致")
    open_tasks = db.scalars(select(Task).where(
        Task.project_id == project_id,
        Task.assignee_id == user.id,
        Task.status != "done",
    )).all()
    for task in open_tasks:
        task.assignee_id = None
        db.add(TaskEvent(task_id=task.id, actor_id=user.id, action="unassigned", note="原任务执行人退出项目，请重新分配"))
    db.delete(membership)
    db.commit()


