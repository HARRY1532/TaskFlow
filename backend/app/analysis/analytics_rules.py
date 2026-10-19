"""Project charts derived from current task rows and their surviving events."""

from datetime import date, datetime, timedelta, timezone

from ..models import Task, TaskEvent, TaskWeight, User
from ..schemas import AnalyticsMember, AnalyticsScheduleItem, AnalyticsTrendPoint, AnalyticsWeight, ProjectAnalytics


BEIJING_TIMEZONE = timezone(timedelta(hours=8))
STATUSES = ("todo", "in_progress", "review", "done")


def beijing_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BEIJING_TIMEZONE).date()


def build_project_analytics(tasks: list[Task], users: list[User], weights: list[TaskWeight],
                            accepted_events: list[TaskEvent], as_of: date) -> ProjectAnalytics:
    status_counts = {status: 0 for status in STATUSES}
    for task in tasks:
        status_counts[task.status] = status_counts.get(task.status, 0) + 1
    completed = status_counts["done"]

    member_rows = {user.id: AnalyticsMember(
        member_id=user.id, member_name=user.name,
        status_counts={status: 0 for status in STATUSES}, estimated_hours=0,
    ) for user in users}
    for task in tasks:
        if task.assignee_id not in member_rows:
            member_rows[task.assignee_id] = AnalyticsMember(
                member_id=task.assignee_id,
                member_name="未分配" if task.assignee_id is None else "已退出成员",
                status_counts={status: 0 for status in STATUSES}, estimated_hours=0,
            )
        row = member_rows[task.assignee_id]
        row.status_counts[task.status] = row.status_counts.get(task.status, 0) + 1
        row.estimated_hours += task.estimated_hours or 0
    known_ids = {user.id for user in users}
    members = [member_rows[user.id] for user in users]
    members.extend(row for member_id, row in member_rows.items() if member_id not in known_ids)

    task_by_id = {task.id: task for task in tasks}
    weight_rows = [AnalyticsWeight(task_id=weight.task_id,
                                   task_title=task_by_id[weight.task_id].title,
                                   confirmed_score=weight.confirmed_score)
                   for weight in weights if weight.task_id in task_by_id]
    weight_rows.sort(key=lambda row: (-row.confirmed_score, row.task_id))
    user_names = {user.id: user.name for user in users}
    schedule = [AnalyticsScheduleItem(
        task_id=task.id, task_title=task.title, due_date=task.due_date,
        status=task.status, assignee_name=user_names.get(task.assignee_id),
    ) for task in tasks if task.due_date is not None]
    schedule.sort(key=lambda item: (item.due_date, item.task_id))

    accepted_dates: dict[int, date] = {}
    for event in accepted_events:
        if event.action == "accepted" and event.task_id in task_by_id and task_by_id[event.task_id].status == "done":
            day = beijing_date(event.created_at)
            accepted_dates[event.task_id] = min(day, accepted_dates.get(event.task_id, day))
    trend = []
    for offset in range(13, -1, -1):
        day = as_of - timedelta(days=offset)
        existing = [task for task in tasks if task.created_at and beijing_date(task.created_at) <= day]
        done = sum(1 for task in existing if task.id in accepted_dates and accepted_dates[task.id] <= day)
        trend.append(AnalyticsTrendPoint(
            date=day, total_tasks=len(existing), completed_tasks=done,
            completion_rate=round(done / len(existing) * 100, 1) if existing else 0,
        ))

    return ProjectAnalytics(
        as_of=as_of, total_tasks=len(tasks), completed_tasks=completed,
        completion_rate=round(completed / len(tasks) * 100, 1) if tasks else 0,
        status_counts=status_counts, members=members, weights=weight_rows, schedule=schedule, trend=trend,
    )
