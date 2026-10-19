from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, ProjectInvitation, ProjectMember, User
from ..permissions import project_owner
from ..schemas import InvitationOut, MemberIn
from ..security import current_user

router = APIRouter(tags=["项目邀请"])


def invitation_out(db: Session, invitation: ProjectInvitation) -> InvitationOut:
    project = db.get(Project, invitation.project_id)
    invited = db.get(User, invitation.invited_user_id)
    inviter = db.get(User, invitation.invited_by_id)
    return InvitationOut(
        id=invitation.id, project_id=invitation.project_id, project_name=project.name,
        invited_user_id=invited.id, invited_user_name=invited.name,
        invited_by_id=inviter.id, inviter_name=inviter.name,
        status=invitation.status, created_at=invitation.created_at,
        responded_at=invitation.responded_at,
    )


@router.post("/projects/{project_id}/invitations", response_model=InvitationOut, status_code=201)
def create_invitation(project_id: int, data: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    invited = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if invited is None or not invited.is_active:
        raise HTTPException(404, "该邮箱尚未注册或账号已停用")
    if db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == invited.id
    )):
        raise HTTPException(409, "用户已在项目中")
    if db.scalar(select(ProjectInvitation).where(
        ProjectInvitation.project_id == project_id,
        ProjectInvitation.invited_user_id == invited.id,
        ProjectInvitation.status == "pending",
    )):
        raise HTTPException(409, "该用户已有待处理邀请")
    invitation = ProjectInvitation(
        project_id=project_id, invited_user_id=invited.id, invited_by_id=user.id,
        status="pending",
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation_out(db, invitation)


@router.get("/projects/{project_id}/invitations", response_model=list[InvitationOut])
def project_invitations(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    rows = db.scalars(select(ProjectInvitation).where(
        ProjectInvitation.project_id == project_id
    ).order_by(ProjectInvitation.id.desc())).all()
    return [invitation_out(db, row) for row in rows]


@router.get("/invitations", response_model=list[InvitationOut])
def my_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ProjectInvitation).where(
        ProjectInvitation.invited_user_id == user.id
    ).order_by(ProjectInvitation.id.desc())).all()
    return [invitation_out(db, row) for row in rows]


def respond(invitation_id: int, user: User, db: Session, accept: bool) -> InvitationOut:
    invitation = db.get(ProjectInvitation, invitation_id)
    if invitation is None or invitation.invited_user_id != user.id:
        raise HTTPException(404, "邀请不存在")
    if invitation.status != "pending":
        raise HTTPException(409, "邀请已处理")
    project = db.get(Project, invitation.project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    invitation.status = "accepted" if accept else "declined"
    invitation.responded_at = datetime.now(timezone.utc)
    if accept and not db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == invitation.project_id,
        ProjectMember.user_id == user.id,
    )):
        db.add(ProjectMember(project_id=invitation.project_id, user_id=user.id, role="member"))
    db.commit()
    db.refresh(invitation)
    return invitation_out(db, invitation)


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationOut)
def accept_invitation(invitation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return respond(invitation_id, user, db, True)


@router.post("/invitations/{invitation_id}/decline", response_model=InvitationOut)
def decline_invitation(invitation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return respond(invitation_id, user, db, False)


@router.post("/projects/{project_id}/invitations/{invitation_id}/cancel", response_model=InvitationOut)
def cancel_invitation(project_id: int, invitation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    invitation = db.get(ProjectInvitation, invitation_id)
    if invitation is None or invitation.project_id != project_id:
        raise HTTPException(404, "邀请不存在")
    if invitation.status != "pending":
        raise HTTPException(409, "邀请已处理")
    invitation.status = "cancelled"
    invitation.responded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invitation)
    return invitation_out(db, invitation)
