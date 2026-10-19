from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ProjectMember, SkillProfile, User, UserSkill
from ..permissions import project_owner
from ..schemas import MemberSkillProfileOut, SkillIn, SkillProfileIn, SkillProfileOut, UserOut
from ..security import current_user

router = APIRouter(tags=["成员技能画像"])


def profile_out(db: Session, user_id: int) -> SkillProfileOut:
    profile = db.get(SkillProfile, user_id)
    skills = db.scalars(select(UserSkill).where(UserSkill.user_id == user_id).order_by(UserSkill.id)).all()
    return SkillProfileOut(
        user_id=user_id,
        weekly_hours=profile.weekly_hours if profile else 0,
        learning_goal=profile.learning_goal if profile else "",
        skills=[SkillIn(category=skill.category, name=skill.name, level=skill.level) for skill in skills],
        updated_at=profile.updated_at if profile else None,
    )


@router.get("/profile/skills", response_model=SkillProfileOut)
def my_skills(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return profile_out(db, user.id)


@router.put("/profile/skills", response_model=SkillProfileOut)
def save_my_skills(data: SkillProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = db.get(SkillProfile, user.id)
    if profile is None:
        profile = SkillProfile(user_id=user.id)
        db.add(profile)
    profile.weekly_hours = data.weekly_hours
    profile.learning_goal = data.learning_goal
    db.execute(delete(UserSkill).where(UserSkill.user_id == user.id))
    db.add_all(UserSkill(user_id=user.id, **skill.model_dump()) for skill in data.skills)
    db.commit()
    return profile_out(db, user.id)


@router.get("/projects/{project_id}/skills", response_model=list[MemberSkillProfileOut])
def project_skills(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    rows = db.execute(select(ProjectMember, User).join(User, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id
    ).order_by(ProjectMember.id)).all()
    return [MemberSkillProfileOut(
        user=UserOut.model_validate(member_user), role=membership.role,
        profile=profile_out(db, member_user.id),
    ) for membership, member_user in rows]
