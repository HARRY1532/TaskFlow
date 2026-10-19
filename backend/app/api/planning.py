from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.planning import generate_plan
from ..db import get_db
from ..models import PlanningDraft, Project, Task, TaskDependency, TaskEvent, User
from ..permissions import project_owner
from ..schemas import PlanningConfirmIn, PlanningDraftOut, PlanningSuggestion
from ..security import current_user

router = APIRouter(prefix="/projects/{project_id}/planning", tags=["AI 任务规划"])


def validate_plan(plan: PlanningSuggestion, existing_titles: set[str]) -> None:
    if not 1 <= len(plan.tasks) <= 20:
        raise HTTPException(502, "AI 返回的任务数量不符合要求")
    titles = [task.title.casefold() for task in plan.tasks]
    if len(titles) != len(set(titles)) or any(title in existing_titles for title in titles):
        raise HTTPException(502, "AI 返回了重复任务，请重新生成")
    visited: set[int] = set()
    visiting: set[int] = set()

    def visit(index: int) -> None:
        if index in visiting:
            raise HTTPException(502, "AI 返回了循环依赖，请重新生成")
        if index in visited:
            return
        visiting.add(index)
        prerequisites = plan.tasks[index].depends_on
        if len(prerequisites) != len(set(prerequisites)):
            raise HTTPException(502, "AI 返回了重复依赖，请重新生成")
        for prerequisite in prerequisites:
            if prerequisite < 0 or prerequisite >= len(plan.tasks):
                raise HTTPException(502, "AI 返回了无效依赖，请重新生成")
            visit(prerequisite)
        visiting.remove(index)
        visited.add(index)

    for index in range(len(plan.tasks)):
        visit(index)


def draft_out(draft: PlanningDraft) -> PlanningDraftOut:
    return PlanningDraftOut(
        id=draft.id, project_id=draft.project_id, status=draft.status,
        suggestion=PlanningSuggestion.model_validate_json(draft.suggestion_json), created_at=draft.created_at,
    )


@router.get("/drafts", response_model=list[PlanningDraftOut])
def list_drafts(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    rows = db.scalars(select(PlanningDraft).where(PlanningDraft.project_id == project_id)
                      .order_by(PlanningDraft.id.desc()).limit(10)).all()
    return [draft_out(row) for row in rows]


@router.post("/suggest", response_model=PlanningDraftOut, status_code=201)
async def suggest_tasks(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    if not project.requirements.strip() and not project.goal.strip():
        raise HTTPException(422, "请先填写项目目标或详细需求")
    existing_tasks = db.scalars(select(Task).where(Task.project_id == project_id)).all()
    plan = await generate_plan(project, existing_tasks)
    validate_plan(plan, {task.title.strip().casefold() for task in existing_tasks})
    draft = PlanningDraft(
        project_id=project_id, created_by_id=user.id,
        requirements_snapshot=project.requirements,
        suggestion_json=plan.model_dump_json(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft_out(draft)


@router.post("/drafts/{draft_id}/confirm", response_model=list[int])
def confirm_plan(project_id: int, draft_id: int, data: PlanningConfirmIn,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    draft = db.get(PlanningDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise HTTPException(404, "规划草稿不存在")
    if draft.status != "pending":
        raise HTTPException(409, "该规划草稿已确认")
    original = PlanningSuggestion.model_validate_json(draft.suggestion_json)
    selected = {item.source_index: item for item in data.tasks}
    if len(selected) != len(data.tasks) or any(index >= len(original.tasks) for index in selected):
        raise HTTPException(422, "所选任务索引无效或重复")
    existing_titles = {title.casefold() for title in db.scalars(
        select(Task.title).where(Task.project_id == project_id)
    )}
    new_titles = [item.title.casefold() for item in data.tasks]
    if len(new_titles) != len(set(new_titles)) or any(title in existing_titles for title in new_titles):
        raise HTTPException(409, "任务标题与现有或所选任务重复")
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visiting:
            raise HTTPException(422, "所选任务依赖不能形成循环")
        if index in visited:
            return
        visiting.add(index)
        links = selected[index].depends_on
        if len(links) != len(set(links)) or index in links or any(link not in selected for link in links):
            raise HTTPException(422, "依赖只能指向本次选中的其他任务，且不能重复")
        for link in links:
            visit(link)
        visiting.remove(index)
        visited.add(index)

    for index in selected:
        visit(index)
    created: dict[int, Task] = {}
    for item in data.tasks:
        task = Task(
            project_id=project_id, title=item.title,
            description=item.description, acceptance_criteria=item.acceptance_criteria,
            estimated_hours=item.estimated_hours, required_skills=item.required_skills,
        )
        db.add(task)
        db.flush()
        created[item.source_index] = task
        db.add(TaskEvent(task_id=task.id, actor_id=user.id, action="created",
                         note=f"由 AI 规划草稿 {draft_id} 经项目负责人确认创建"))
    for item in data.tasks:
        db.add_all(TaskDependency(task_id=created[item.source_index].id,
                                  depends_on_id=created[index].id) for index in item.depends_on)
    draft.status = "confirmed"
    db.commit()
    return [created[item.source_index].id for item in data.tasks]
