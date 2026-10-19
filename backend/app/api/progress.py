from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.diagnosis import generate_progress_diagnosis
from ..analysis.progress_rules import build_progress_snapshot
from ..db import get_db
from ..models import ProgressReport, ProjectMember, Task, TaskDependency, User
from ..permissions import project_owner
from ..schemas import ProgressDiagnosis, ProgressReportOut, ProgressSnapshot
from ..security import current_user


router = APIRouter(prefix="/projects/{project_id}/progress", tags=["项目进度诊断"])
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


def current_snapshot(project_id: int, db: Session) -> tuple[ProgressSnapshot, list[Task]]:
    tasks = db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.id)).all()
    dependencies = db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_id)
                              .join(Task, TaskDependency.task_id == Task.id)
                              .where(Task.project_id == project_id)).all()
    members = db.scalars(select(User).join(ProjectMember, ProjectMember.user_id == User.id)
                         .where(ProjectMember.project_id == project_id).order_by(User.id)).all()
    snapshot = build_progress_snapshot(tasks, dependencies, members,
                                       datetime.now(BEIJING_TIMEZONE).date())
    return snapshot, tasks


def report_out(report: ProgressReport) -> ProgressReportOut:
    return ProgressReportOut(
        id=report.id, project_id=report.project_id,
        snapshot=ProgressSnapshot.model_validate_json(report.snapshot_json),
        diagnosis=ProgressDiagnosis.model_validate_json(report.diagnosis_json),
        created_at=report.created_at,
    )


@router.get("/snapshot", response_model=ProgressSnapshot)
def get_snapshot(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    return current_snapshot(project_id, db)[0]


@router.get("/reports", response_model=list[ProgressReportOut])
def list_reports(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_owner(db, project_id, user)
    reports = db.scalars(select(ProgressReport).where(ProgressReport.project_id == project_id)
                         .order_by(ProgressReport.id.desc()).limit(10)).all()
    return [report_out(report) for report in reports]


@router.post("/reports", response_model=ProgressReportOut, status_code=201)
async def create_report(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    snapshot, tasks = current_snapshot(project_id, db)
    if not tasks:
        raise HTTPException(422, "请先创建任务，再生成进度报告")
    context = {
        "project": {"name": project.name, "goal": project.goal, "end_date": project.end_date},
        "snapshot": snapshot.model_dump(mode="json"),
        "tasks": [{"id": task.id, "title": task.title, "status": task.status,
                   "due_date": task.due_date, "assignee_name": task.assignee_name} for task in tasks],
    }
    diagnosis = await generate_progress_diagnosis(context)
    task_ids = {task.id for task in tasks}
    if any(task_id not in task_ids for action in diagnosis.actions for task_id in action.related_task_ids):
        raise HTTPException(502, "AI 进度建议引用了无效任务，请重新生成")
    report = ProgressReport(
        project_id=project_id, created_by_id=user.id,
        snapshot_json=snapshot.model_dump_json(), diagnosis_json=diagnosis.model_dump_json(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report_out(report)
