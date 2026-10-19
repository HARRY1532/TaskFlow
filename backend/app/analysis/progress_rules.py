"""Deterministic project progress checks used before AI writes a report."""

from datetime import date

from ..models import Task, User
from ..schemas import ProgressFinding, ProgressSnapshot, ProgressWorkload


def build_progress_snapshot(tasks: list[Task], dependencies: list[tuple[int, int]],
                            members: list[User], as_of: date) -> ProgressSnapshot:
    by_id = {task.id: task for task in tasks}
    status_counts = {status: 0 for status in ("todo", "in_progress", "review", "done")}
    for task in tasks:
        status_counts[task.status] = status_counts.get(task.status, 0) + 1
    completed = status_counts["done"]
    workload = []
    for member in members:
        assigned = [task for task in tasks if task.assignee_id == member.id and task.status != "done"]
        workload.append(ProgressWorkload(
            member_id=member.id, member_name=member.name,
            open_task_count=len(assigned), estimated_hours=sum(task.estimated_hours or 0 for task in assigned),
        ))
    workload.sort(key=lambda item: (-item.estimated_hours, -item.open_task_count, item.member_id))
    findings: list[ProgressFinding] = []

    overdue = [task for task in tasks if task.status != "done" and task.due_date and task.due_date < as_of]
    if overdue:
        findings.append(ProgressFinding(
            code="overdue", severity="high", title=f"{len(overdue)} 项任务已逾期",
            detail="截止日期已过，仍未完成：" + "、".join(task.title for task in overdue[:8]),
            task_ids=[task.id for task in overdue],
        ))

    due_soon = [task for task in tasks if task.status != "done" and task.due_date
                and 0 <= (task.due_date - as_of).days <= 3]
    if due_soon:
        findings.append(ProgressFinding(
            code="due_soon", severity="medium", title=f"{len(due_soon)} 项任务即将到期",
            detail="未来 3 天内到期且尚未完成：" + "、".join(task.title for task in due_soon[:8]),
            task_ids=[task.id for task in due_soon],
        ))

    blocked: dict[int, list[int]] = {}
    for task_id, prerequisite_id in dependencies:
        task, prerequisite = by_id.get(task_id), by_id.get(prerequisite_id)
        if task and prerequisite and task.status != "done" and prerequisite.status != "done":
            blocked.setdefault(task_id, []).append(prerequisite_id)
    if blocked:
        examples = [f"{by_id[task_id].title}（等待 {', '.join(by_id[dep].title for dep in deps)}）"
                    for task_id, deps in list(blocked.items())[:6]]
        findings.append(ProgressFinding(
            code="blocked", severity="medium", title=f"{len(blocked)} 项任务受前置任务阻塞",
            detail="；".join(examples), task_ids=list(blocked),
        ))

    unassigned = [task for task in tasks if task.status == "todo" and task.assignee_id is None]
    if unassigned:
        findings.append(ProgressFinding(
            code="unassigned", severity="medium", title=f"{len(unassigned)} 项任务尚无执行人",
            detail="待分配：" + "、".join(task.title for task in unassigned[:8]),
            task_ids=[task.id for task in unassigned],
        ))

    missing_evidence = [task for task in tasks if task.status in ("review", "done")
                        and not (task.evidence_note or task.evidence_url)]
    if missing_evidence:
        findings.append(ProgressFinding(
            code="missing_evidence", severity="medium", title=f"{len(missing_evidence)} 项任务缺少成果记录",
            detail="已提交或已完成，但未保存成果说明或链接：" + "、".join(task.title for task in missing_evidence[:8]),
            task_ids=[task.id for task in missing_evidence],
        ))

    active_workloads = [item for item in workload if item.open_task_count]
    if len(members) > 1 and active_workloads and sum(item.open_task_count for item in active_workloads) >= 2:
        total_hours = sum(item.estimated_hours for item in active_workloads)
        total_count = sum(item.open_task_count for item in active_workloads)
        top = active_workloads[0]
        share = top.estimated_hours / total_hours if total_hours else top.open_task_count / total_count
        if share >= 0.6:
            findings.append(ProgressFinding(
                code="workload_concentration", severity="medium", title="工作量集中在少数成员",
                detail=f"{top.member_name} 承担约 {share:.0%} 的未完成任务"
                       + ("预计工时" if total_hours else "数量") + "，建议核对分工。",
                task_ids=[task.id for task in tasks if task.assignee_id == top.member_id and task.status != "done"],
                member_id=top.member_id,
            ))

    return ProgressSnapshot(
        as_of=as_of, total_tasks=len(tasks), completed_tasks=completed,
        completion_rate=round(completed / len(tasks) * 100, 1) if tasks else 0,
        status_counts=status_counts, workload=workload, findings=findings,
    )
