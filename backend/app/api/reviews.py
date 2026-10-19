"""Owner initiated, read-only PR evidence snapshots for task acceptance."""

from datetime import timezone
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.review import generate_review_advice
from ..analysis.secret_rules import secret_warnings, text_warnings
from ..db import get_db
from ..github import inspect_code, pull_request_snapshot
from ..models import Project, Task, TaskEvent, TaskReviewAdvice, TaskReviewSnapshot, User
from ..permissions import project_owner, project_task
from ..schemas import ReviewAdvice, ReviewConsentIn, TaskReviewAdviceOut, TaskReviewSnapshotOut
from ..security import current_user


router = APIRouter(prefix="/projects/{project_id}/tasks/{task_id}/reviews", tags=["PR 验收证据"])


def task_signature(task: Task) -> str:
    data = {
        "title": task.title, "description": task.description,
        "acceptance_criteria": task.acceptance_criteria,
        "development_checklist": task.development_checklist or [],
        "evidence_note": task.evidence_note, "evidence_url": task.evidence_url,
        "code_url": task.code_url, "test_note": task.test_note, "test_url": task.test_url,
    }
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def snapshot_out(record: TaskReviewSnapshot, task: Task) -> TaskReviewSnapshotOut:
    snapshot = record.snapshot_json
    return TaskReviewSnapshotOut(
        id=record.id, task_id=record.task_id, snapshot=snapshot,
        is_current=(snapshot["task_signature"] == task_signature(task)
                    and snapshot["pr"]["head_sha"] == (task.code_metadata or {}).get("sha")),
        created_at=(record.created_at.replace(tzinfo=timezone.utc)
                    if record.created_at.tzinfo is None else record.created_at),
    )


@router.get("", response_model=list[TaskReviewSnapshotOut])
def list_reviews(project_id: int, task_id: int, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    task = project_task(db, project_id, task_id, user)
    records = db.scalars(select(TaskReviewSnapshot).where(TaskReviewSnapshot.task_id == task.id)
                         .order_by(TaskReviewSnapshot.id.desc()).limit(10)).all()
    return [snapshot_out(record, task) for record in records]


@router.post("", response_model=TaskReviewSnapshotOut, status_code=201)
def create_review_snapshot(project_id: int, task_id: int, user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    if task.status != "review":
        raise HTTPException(409, "仅待验收任务可以读取 PR 改动")
    if not project.github_repo_url or not task.code_url:
        raise HTTPException(409, "请先绑定公开 GitHub 仓库并提交 PR 链接")
    original = task_signature(task)
    pr = pull_request_snapshot(task.code_url, project.github_repo_url)
    db.refresh(project)
    db.refresh(task)
    if project.owner_id != user.id or task.status != "review" or task_signature(task) != original:
        raise HTTPException(409, "任务在读取期间已变化，请重新获取")
    task.code_metadata = {
        "kind": "pull", "title": pr["title"], "author": pr["author"],
        "state": pr["state"], "sha": pr["head_sha"], "number": pr["number"],
        "checked_at": pr["fetched_at"],
    }
    record = TaskReviewSnapshot(task_id=task.id, created_by_id=user.id,
                                snapshot_json={"task_signature": original, "pr": pr})
    db.add(record)
    db.add(TaskEvent(task_id=task.id, actor_id=user.id, action="pr_inspected",
                     note=f"已读取 PR #{pr['number']} · {pr['head_sha'][:12]}"))
    db.commit()
    db.refresh(record)
    return snapshot_out(record, task)


def advice_out(record: TaskReviewAdvice) -> TaskReviewAdviceOut:
    return TaskReviewAdviceOut(
        id=record.id, snapshot_id=record.snapshot_id,
        advice=ReviewAdvice.model_validate(record.advice_json),
        created_at=(record.created_at.replace(tzinfo=timezone.utc)
                    if record.created_at.tzinfo is None else record.created_at),
    )


@router.get("/{snapshot_id}/advice", response_model=list[TaskReviewAdviceOut])
def list_advice(project_id: int, task_id: int, snapshot_id: int,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_task(db, project_id, task_id, user)
    snapshot = db.get(TaskReviewSnapshot, snapshot_id)
    if snapshot is None or snapshot.task_id != task_id:
        raise HTTPException(404, "PR 快照不存在")
    records = db.scalars(select(TaskReviewAdvice).where(TaskReviewAdvice.snapshot_id == snapshot_id)
                         .order_by(TaskReviewAdvice.id.desc()).limit(10)).all()
    return [advice_out(record) for record in records]


@router.post("/{snapshot_id}/advice", response_model=TaskReviewAdviceOut, status_code=201)
async def create_advice(project_id: int, task_id: int, snapshot_id: int, data: ReviewConsentIn,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = project_owner(db, project_id, user)
    task = project_task(db, project_id, task_id, user)
    snapshot = db.get(TaskReviewSnapshot, snapshot_id)
    if snapshot is None or snapshot.task_id != task.id:
        raise HTTPException(404, "PR 快照不存在")
    if not (data.acknowledged_risk and data.confirmed_send and data.confirmation_text == "发送至 DeepSeek"):
        raise HTTPException(422, "请完成两次外部数据发送确认")
    if task.status != "review" or not snapshot_out(snapshot, task).is_current:
        raise HTTPException(409, "请先读取当前待验收任务的 PR 改动")
    if not project.github_repo_url or not task.code_url:
        raise HTTPException(409, "请先绑定仓库并提交 PR 链接")
    original = task_signature(task)
    pr = snapshot.snapshot_json["pr"]
    context = {
        "task": {
            "title": task.title,
            "description": task.description[:3000],
            "acceptance_criteria": task.acceptance_criteria[:2000],
            "development_checklist": (task.development_checklist or [])[:12],
            "test_note": (task.test_note or "")[:1000],
        },
        "pr": {
            "title": pr["title"], "head_sha": pr["head_sha"],
            "files": [{"path": item["path"], "status": item["status"],
                       "patch": item["patch"]} for item in pr["files"]],
        },
    }
    warnings = secret_warnings(context)
    if warnings:
        raise HTTPException(422, "敏感信息预警：" + "、".join(warnings) + "。未向 DeepSeek 发送内容，请先检查 PR 或任务文字。")
    live = inspect_code(task.code_url, project.github_repo_url)
    if live["sha"] != pr["head_sha"]:
        raise HTTPException(409, "PR 已更新，请先重新读取改动快照")
    advice = await generate_review_advice(context)
    if advice.security_warning or text_warnings(json.dumps(advice.model_dump(), ensure_ascii=False)):
        raise HTTPException(422, "敏感信息预警：AI 报告疑似泄露，已停止分析且未保存 AI 回复。已发送的请求无法由本系统撤回，请检查并轮换相关凭据。")
    db.refresh(project)
    db.refresh(task)
    if project.owner_id != user.id or task.status != "review" or task_signature(task) != original:
        raise HTTPException(409, "任务在分析期间已变化，AI 建议未保存")
    record = TaskReviewAdvice(snapshot_id=snapshot.id, created_by_id=user.id,
                              advice_json=advice.model_dump())
    db.add(record)
    db.add(TaskEvent(task_id=task.id, actor_id=user.id, action="review_advised",
                     note=f"AI 建议基于 PR #{pr['number']} · {pr['head_sha'][:12]}"))
    db.commit()
    db.refresh(record)
    return advice_out(record)
