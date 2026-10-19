from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.assignment import generate_assignment_suggestion
from ..analysis.matching_rules import candidate_metrics
from ..db import get_db
from ..models import AssignmentDraft, ProjectMember, SkillProfile, Task, TaskEvent, TaskWeight, User, UserSkill
from ..permissions import project_owner, valid_assignee
from ..schemas import AssignmentConfirmIn, AssignmentDraftOut, AssignmentSuggestion
from ..security import current_user


router = APIRouter(prefix="/projects/{project_id}/assignments", tags=["AI 智能分工"])


def draft_out(draft: AssignmentDraft) -> AssignmentDraftOut:
    return AssignmentDraftOut(
        id=draft.id, project_id=draft.project_id, status=draft.status,
        suggestion=AssignmentSuggestion.model_validate_json(draft.suggestion_json),
        created_at=draft.created_at,
    )


@router.get("/drafts", response_model=list[AssignmentDraftOut])
def list_drafts(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    drafts = db.scalars(select(AssignmentDraft).where(AssignmentDraft.project_id == project_id)
                        .order_by(AssignmentDraft.id.desc()).limit(10)).all()
    return [draft_out(draft) for draft in drafts]


@router.post("/suggest", response_model=AssignmentDraftOut, status_code=201)
async def suggest_assignments(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    tasks = db.scalars(select(Task).where(
        Task.project_id == project_id, Task.status == "todo", Task.assignee_id.is_(None)
    ).order_by(Task.id).limit(20)).all()
    if not tasks:
        raise HTTPException(422, "没有待开始且未分配的任务")
    members = db.execute(select(User).join(ProjectMember, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project_id, User.is_active.is_(True)
    ).order_by(User.id)).scalars().all()
    if not members:
        raise HTTPException(422, "项目暂无有效成员")

    member_ids = {member.id for member in members}
    profiles = {profile.user_id: profile for profile in db.scalars(select(SkillProfile).where(
        SkillProfile.user_id.in_(member_ids)
    ))}
    skills: dict[int, list[tuple[str, int]]] = {member_id: [] for member_id in member_ids}
    for skill in db.scalars(select(UserSkill).where(UserSkill.user_id.in_(member_ids))):
        skills[skill.user_id].append((skill.name, skill.level))
    current_hours = {member_id: 0 for member_id in member_ids}
    for task in db.scalars(select(Task).where(
        Task.project_id == project_id, Task.status != "done", Task.assignee_id.in_(member_ids)
    )):
        current_hours[task.assignee_id] += task.estimated_hours or 0
    weights = {weight.task_id: weight.confirmed_score for weight in db.scalars(select(TaskWeight).where(
        TaskWeight.task_id.in_([task.id for task in tasks])
    ))}
    context = {
        "project": {"name": project.name, "goal": project.goal, "tech_stack": project.tech_stack},
        "tasks": [{
            "id": task.id, "title": task.title, "description": task.description,
            "required_skills": task.required_skills, "estimated_hours": task.estimated_hours,
            "priority": task.priority, "weight": weights.get(task.id),
            "candidates": [{
                "id": member.id, "name": member.name,
                "profile_filled": member.id in profiles,
                "skills": [{"name": name, "level": level} for name, level in skills[member.id]],
                "learning_goal": profiles[member.id].learning_goal if member.id in profiles else "",
                "metrics": candidate_metrics(
                    task.required_skills, skills[member.id],
                    profiles[member.id].weekly_hours if member.id in profiles else 0,
                    current_hours[member.id],
                    profiles[member.id].learning_goal if member.id in profiles else "",
                    member.id in profiles,
                ),
            } for member in members],
        } for task in tasks],
    }
    suggestion = await generate_assignment_suggestion(context)
    expected_ids = {task.id for task in tasks}
    actual_ids = [item.task_id for item in suggestion.recommendations]
    if len(actual_ids) != len(expected_ids) or set(actual_ids) != expected_ids:
        raise HTTPException(502, "AI 分工建议未覆盖全部待分配任务，请重新生成")
    if any(item.assignee_id not in member_ids for item in suggestion.recommendations):
        raise HTTPException(502, "AI 推荐了无效成员，请重新生成")
    draft = AssignmentDraft(
        project_id=project_id, created_by_id=user.id,
        suggestion_json=suggestion.model_dump_json(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft_out(draft)


@router.post("/drafts/{draft_id}/confirm", response_model=list[int])
def confirm_assignments(project_id: int, draft_id: int, data: AssignmentConfirmIn,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    draft = db.get(AssignmentDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise HTTPException(404, "分工草稿不存在")
    if draft.status != "pending":
        raise HTTPException(409, "该分工草稿已确认")
    original = AssignmentSuggestion.model_validate_json(draft.suggestion_json)
    allowed_ids = {item.task_id for item in original.recommendations}
    selected_ids = [item.task_id for item in data.assignments]
    if len(selected_ids) != len(set(selected_ids)) or any(task_id not in allowed_ids for task_id in selected_ids):
        raise HTTPException(422, "所选任务不在草稿中或重复")
    tasks = {task.id: task for task in db.scalars(select(Task).where(
        Task.project_id == project_id, Task.id.in_(selected_ids)
    ))}
    if len(tasks) != len(selected_ids) or any(task.status != "todo" or task.assignee_id is not None for task in tasks.values()):
        raise HTTPException(409, "任务已变更，请重新生成分工建议")
    for item in data.assignments:
        valid_assignee(db, project_id, item.assignee_id)
    for item in data.assignments:
        tasks[item.task_id].assignee_id = item.assignee_id
        db.add(TaskEvent(task_id=item.task_id, actor_id=user.id, action="assigned",
                         note=f"由 AI 分工草稿 {draft_id} 经项目负责人确认"))
    draft.status = "confirmed"
    db.commit()
    return selected_ids
