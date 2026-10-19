from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.weight_rules import suggest_weight
from ..db import get_db
from ..models import Task, TaskEvent, TaskWeight, User
from ..permissions import project_member, project_owner, project_task
from ..schemas import TaskWeightOut, WeightConfirmIn, WeightFactors, WeightSuggestionOut
from ..security import current_user

router = APIRouter(prefix="/projects/{project_id}", tags=["任务权重"])


@router.get("/weights", response_model=list[TaskWeightOut])
def list_weights(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_member(db, project_id, user)
    rows = db.scalars(select(TaskWeight).join(Task, TaskWeight.task_id == Task.id).where(
        Task.project_id == project_id
    ).order_by(TaskWeight.task_id)).all()
    return [TaskWeightOut.model_validate(row) for row in rows]


@router.post("/tasks/{task_id}/weight/suggestion", response_model=WeightSuggestionOut)
def weight_suggestion(project_id: int, task_id: int, data: WeightFactors,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    project_task(db, project_id, task_id, user)
    return suggest_weight(data)


@router.put("/tasks/{task_id}/weight", response_model=TaskWeightOut)
def confirm_weight(project_id: int, task_id: int, data: WeightConfirmIn,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    factors = WeightFactors.model_validate(data.model_dump())
    suggestion = suggest_weight(factors)
    if data.confirmed_score != suggestion.suggested_score and not data.adjustment_reason:
        raise HTTPException(422, "调整建议分值时请填写原因")
    weight = db.get(TaskWeight, task_id)
    if weight is None:
        weight = TaskWeight(task_id=task_id)
        db.add(weight)
    for key, value in factors.model_dump().items():
        setattr(weight, key, value)
    weight.suggested_score = suggestion.suggested_score
    weight.confirmed_score = data.confirmed_score
    weight.rationale = suggestion.rationale
    weight.adjustment_reason = data.adjustment_reason if data.confirmed_score != suggestion.suggested_score else ""
    weight.confirmed_by_id = user.id
    task.estimated_hours = data.estimated_hours
    db.add(TaskEvent(task_id=task_id, actor_id=user.id, action="weight_confirmed",
                     note=f"权重 {weight.confirmed_score}/100；建议 {weight.suggested_score}/100。{weight.adjustment_reason}"))
    db.commit()
    db.refresh(weight)
    return TaskWeightOut.model_validate(weight)
