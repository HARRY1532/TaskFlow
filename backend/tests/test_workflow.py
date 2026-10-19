import os
import asyncio
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-with-at-least-32-characters"

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from io import BytesIO
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app import db as db_module
from app.main import app
from app.models import Project, Task, TaskEvent, TaskWeight, User
from app.api import planning as planning_api
from app.api import assignments as assignments_api
from app.api import progress as progress_api
from app.api import tasks as tasks_api
from app.api import reviews as reviews_api
from app import github as github_module
from app.analysis.secret_rules import secret_warnings
from app.schemas import ReviewAdvice, ReviewFinding
from app.agent.planning import RawPlan, generate_plan
from app.agent.assignment import RawAssignmentPlan, generate_assignment_suggestion
from app.agent.diagnosis import RawProgressDiagnosis, generate_progress_diagnosis
from app.analysis.matching_rules import candidate_metrics
from app.analysis.progress_rules import build_progress_snapshot
from app.analysis.analytics_rules import build_project_analytics
from app.schemas import AssignmentSuggestion, PlanningSuggestion, ProgressDiagnosis


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)

    def test_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.state.test_engine = engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def register_and_login(client: TestClient, email: str):
    registration = client.post("/api/auth/register", json={
        "email": email, "name": email.split("@")[0], "password": "password123"
    })
    assert registration.status_code == 201
    token = client.post("/api/auth/login", json={
        "email": email, "password": "password123"
    })
    assert token.status_code == 200
    return registration.json()["id"], {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_development_checklist_and_structured_evidence(client: TestClient, monkeypatch):
    owner_id, owner = register_and_login(client, "dev-owner@example.com")
    member_id, member = register_and_login(client, "dev-member@example.com")
    _, outsider = register_and_login(client, "dev-outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "开发辅助"}).json()["id"]
    invitation = client.post(f"/api/projects/{project_id}/invitations", headers=owner,
                             json={"email": "dev-member@example.com"}).json()
    client.post(f"/api/invitations/{invitation['id']}/accept", headers=member)
    base = f"/api/projects/{project_id}/tasks"
    task_id = client.post(base, headers=owner, json={
        "title": "完成接口", "description": "实现查询接口", "acceptance_criteria": "包含无权限测试",
        "assignee_id": member_id,
    }).json()["id"]
    path = f"{base}/{task_id}"

    async def fake_generate(context):
        assert context["acceptance_criteria"] == "包含无权限测试"
        return [
            tasks_api.ChecklistItem(title="实现查询接口", detail="返回正确数据", kind="implementation"),
            tasks_api.ChecklistItem(title="测试无权限请求", detail="返回拒绝", kind="test"),
        ]

    monkeypatch.setattr(tasks_api, "generate_development_checklist", fake_generate)
    assert client.post(f"{path}/development-checklist/generate", headers=outsider).status_code == 404
    assert client.post(f"{path}/development-checklist/generate", headers=member).status_code == 200
    assert client.put(f"{path}/development-checklist", headers=owner, json={"items": [
        {"title": "伪造", "kind": "test", "checked": True}
    ]}).status_code == 403
    client.post(f"{path}/start", headers=member)
    items = client.get(base, headers=member).json()[0]["development_checklist"]
    items[0]["checked"] = True
    assert client.put(f"{path}/development-checklist", headers=member, json={"items": items}).status_code == 200
    items[0]["title"] = "篡改内容"
    assert client.put(f"{path}/development-checklist", headers=member, json={"items": items}).status_code == 409
    assert client.post(f"{path}/submit", headers=member, json={
        "code_url": "https://github.com/example/repo/pull/1",
        "test_url": "https://github.com/example/repo/actions/runs/1",
        "test_note": "执行了接口测试",
    }).status_code == 200
    saved = client.get(base, headers=owner).json()[0]
    assert saved["code_url"] == "https://github.com/example/repo/pull/1"
    assert saved["test_note"] == "执行了接口测试"
    assert saved["development_checklist"][0]["checked"] is True
    assert client.post(f"{path}/development-checklist/generate", headers=owner).status_code == 409


def test_public_github_repository_and_code_evidence(client: TestClient, monkeypatch):
    _, owner = register_and_login(client, "repo-owner@example.com")
    member_id, member = register_and_login(client, "repo-member@example.com")
    _, outsider = register_and_login(client, "repo-outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "仓库项目"}).json()["id"]
    invitation = client.post(f"/api/projects/{project_id}/invitations", headers=owner,
                             json={"email": "repo-member@example.com"}).json()
    client.post(f"/api/invitations/{invitation['id']}/accept", headers=member)
    calls = []

    def fake_get(path):
        calls.append(path)
        if path == "/repos/example/repo":
            return {"full_name": "example/repo", "private": False}
        if path == "/repos/example/repo/pulls/12":
            return {"title": "完成接口", "user": {"login": "developer"}, "state": "open",
                    "merged_at": None, "head": {"sha": "a" * 40}}
        raise AssertionError(path)

    monkeypatch.setattr(github_module, "github_get", fake_get)
    repo_path = f"/api/projects/{project_id}/repository"
    assert client.put(repo_path, headers=member, json={"url": "https://github.com/example/repo"}).status_code == 403
    assert client.put(repo_path, headers=owner, json={"url": "https://github.com@127.0.0.1/evil/repo"}).status_code == 422
    assert client.put(repo_path, headers=owner, json={"url": "https://github.com/example/repo"}).json()["github_repo_url"] == "https://github.com/example/repo"
    base = f"/api/projects/{project_id}/tasks"
    task_id = client.post(base, headers=owner, json={"title": "开发接口", "assignee_id": member_id}).json()["id"]
    task_path = f"{base}/{task_id}"
    client.post(f"{task_path}/start", headers=member)
    assert client.post(f"{task_path}/submit", headers=member, json={
        "code_url": "https://github.com/other/repo/pull/12"
    }).status_code == 422
    assert client.post(f"{task_path}/submit", headers=member, json={
        "code_url": "https://github.com/example/repo/pull/12"
    }).json()["code_metadata"]["author"] == "developer"
    assert client.get(base, headers=outsider).status_code == 404
    assert client.post(f"{task_path}/code-evidence/refresh", headers=outsider).status_code == 404
    assert client.post(f"{task_path}/code-evidence/refresh", headers=owner).json()["code_metadata"]["state"] == "open"
    assert client.put(repo_path, headers=owner, json={"url": None}).status_code == 409
    assert calls == ["/repos/example/repo", "/repos/example/repo/pulls/12", "/repos/example/repo/pulls/12"]


@pytest.mark.parametrize("url", [
    "http://github.com/example/repo",
    "https://github.com:443/example/repo",
    "https://github.com@127.0.0.1/example/repo",
    "https://github.com/example/../repo",
    "https://github.com/example/repo?redirect=http://127.0.0.1",
])
def test_github_link_rejects_noncanonical_host_or_path(url):
    with pytest.raises(HTTPException) as error:
        github_module.repository_name(url)
    assert error.value.status_code == 422


def test_github_commit_metadata(monkeypatch):
    seen = []

    def fake_get(path):
        seen.append(path)
        return {"sha": "b" * 40, "commit": {"message": "Fix login\nDetails",
                "author": {"name": "Student"}}, "author": None}

    monkeypatch.setattr(github_module, "github_get", fake_get)
    metadata = github_module.inspect_code(
        "https://github.com/example/repo/commit/" + "b" * 40,
        "https://github.com/example/repo",
    )
    assert metadata["kind"] == "commit"
    assert metadata["title"] == "Fix login"
    assert metadata["author"] == "Student"
    assert seen == ["/repos/example/repo/commits/" + "b" * 40]


def test_pr_review_snapshot_permissions_and_staleness(client: TestClient, monkeypatch):
    _, owner = register_and_login(client, "review-owner@example.com")
    member_id, member = register_and_login(client, "review-member@example.com")
    _, outsider = register_and_login(client, "review-outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "验收项目"}).json()["id"]
    invitation = client.post(f"/api/projects/{project_id}/invitations", headers=owner,
                             json={"email": "review-member@example.com"}).json()
    client.post(f"/api/invitations/{invitation['id']}/accept", headers=member)

    def fake_get(path):
        if path == "/repos/example/repo":
            return {"full_name": "example/repo", "private": False}
        if path == "/repos/example/repo/pulls/7":
            return {"title": "实现接口", "user": {"login": "student"}, "state": "open",
                    "head": {"sha": "a" * 40}, "merged_at": None}
        if path == "/repos/example/repo/pulls/7/files?per_page=21&page=1":
            return [{"filename": "app/api.py", "status": "modified", "additions": 3,
                     "deletions": 1, "patch": "@@ -1 +1 @@\n-old\n+new"}]
        raise AssertionError(path)

    monkeypatch.setattr(github_module, "github_get", fake_get)
    client.put(f"/api/projects/{project_id}/repository", headers=owner,
               json={"url": "https://github.com/example/repo"})
    base = f"/api/projects/{project_id}/tasks"
    task_id = client.post(base, headers=owner, json={"title": "实现接口", "assignee_id": member_id,
                                                   "acceptance_criteria": "返回正确数据"}).json()["id"]
    task_path = f"{base}/{task_id}"
    reviews = f"{task_path}/reviews"
    assert client.post(reviews, headers=owner).status_code == 409
    client.post(f"{task_path}/start", headers=member)
    client.post(f"{task_path}/submit", headers=member,
                json={"code_url": "https://github.com/example/repo/pull/7"})
    assert client.post(reviews, headers=member).status_code == 403
    assert client.get(reviews, headers=outsider).status_code == 404
    saved = client.post(reviews, headers=owner)
    assert saved.status_code == 201
    assert saved.json()["is_current"] is True
    assert saved.json()["snapshot"]["pr"]["files"][0]["path"] == "app/api.py"
    assert client.get(reviews, headers=member).json()[0]["is_current"] is True
    advice_path = f"{reviews}/{saved.json()['id']}/advice"
    assert client.post(advice_path, headers=member, json={}).status_code == 422
    assert client.post(advice_path, headers=owner, json={
        "acknowledged_risk": False, "confirmed_send": True,
        "confirmation_text": "发送至 DeepSeek",
    }).status_code == 422

    async def fake_advice(context):
        assert context["pr"]["files"][0]["patch"] == "@@ -1 +1 @@\n-old\n+new"
        return ReviewAdvice(summary="需核对返回值", findings=[ReviewFinding(
            criterion="返回正确数据", assessment="uncertain", explanation="补丁不足以确认",
            evidence_paths=["app/api.py"],
        )], manual_tests=["运行接口测试"])

    monkeypatch.setattr(reviews_api, "generate_review_advice", fake_advice)
    consent = {"acknowledged_risk": True, "confirmed_send": True,
               "confirmation_text": "发送至 DeepSeek"}
    assert client.post(advice_path, headers=member, json=consent).status_code == 403
    assert client.post(advice_path, headers=outsider, json=consent).status_code == 404
    generated = client.post(advice_path, headers=owner, json=consent)
    assert generated.status_code == 201
    assert generated.json()["advice"]["findings"][0]["assessment"] == "uncertain"
    assert len(client.get(advice_path, headers=member).json()) == 1

    async def unsafe_advice(context):
        return ReviewAdvice(security_warning=True, security_message="疑似敏感数据")

    monkeypatch.setattr(reviews_api, "generate_review_advice", unsafe_advice)
    warning = client.post(advice_path, headers=owner, json=consent)
    assert warning.status_code == 422
    assert "敏感信息预警" in warning.json()["detail"]
    assert len(client.get(advice_path, headers=owner).json()) == 1
    client.patch(task_path, headers=owner, json={"acceptance_criteria": "还需权限校验"})
    assert client.get(reviews, headers=owner).json()[0]["is_current"] is False
    assert client.post(advice_path, headers=owner, json=consent).status_code == 409
    client.patch(task_path, headers=owner, json={
        "acceptance_criteria": "DEEPSEEK_API_KEY=abcdefghijklmnop",
    })
    fresh = client.post(reviews, headers=owner).json()

    async def must_not_send(context):
        raise AssertionError("本地预检应在外部调用前阻止请求")

    monkeypatch.setattr(reviews_api, "generate_review_advice", must_not_send)
    blocked = client.post(f"{reviews}/{fresh['id']}/advice", headers=owner, json=consent)
    assert blocked.status_code == 422
    assert "未向 DeepSeek 发送" in blocked.json()["detail"]


def test_pr_snapshot_rejects_large_or_changing_diff(monkeypatch):
    pr = {"head": {"sha": "a" * 40}, "title": "test", "user": {"login": "student"}}
    files_path = "/repos/example/repo/pulls/7/files?per_page=21&page=1"
    monkeypatch.setattr(github_module, "github_get", lambda path: (
        [{"filename": f"file-{n}.py", "patch": "+ok"} for n in range(21)]
        if path == files_path else pr
    ))
    with pytest.raises(HTTPException) as error:
        github_module.pull_request_snapshot("https://github.com/example/repo/pull/7",
                                            "https://github.com/example/repo")
    assert error.value.status_code == 422

    heads = iter([{"head": {"sha": "a" * 40}}, {"head": {"sha": "b" * 40}}])
    monkeypatch.setattr(github_module, "github_get", lambda path: (
        [{"filename": "app.py", "patch": "+ok"}] if path == files_path else next(heads)
    ))
    with pytest.raises(HTTPException) as error:
        github_module.pull_request_snapshot("https://github.com/example/repo/pull/7",
                                            "https://github.com/example/repo")
    assert error.value.status_code == 409


def test_review_secret_preflight_detects_credentials_without_echoing_values():
    context = {"task": {"title": "接口", "description": "", "acceptance_criteria": "",
                         "development_checklist": [], "test_note": ""},
               "pr": {"title": "实现接口", "files": [{"path": "src/config.py",
                       "patch": "+DEEPSEEK_API_KEY=abcdefghijklmnop"}]}}
    warning = secret_warnings(context)
    assert warning == ["环境变量密钥"]
    assert "abcdefghijklmnop" not in str(warning)


def test_project_task_review_and_permissions(client: TestClient):
    owner_id, owner = register_and_login(client, "owner@example.com")
    member_id, member = register_and_login(client, "member@example.com")
    _, outsider = register_and_login(client, "outsider@example.com")

    project_response = client.post("/api/projects", headers=owner, json={
        "name": "课程项目", "goal": "完成协作平台", "tech_stack": "Vue, FastAPI"
    })
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    assert project_response.json()["owner_id"] == owner_id
    assert client.get(f"/api/projects/{project_id}", headers=outsider).status_code == 404
    assert client.post(f"/api/projects/{project_id}/invitations", headers=member, json={"email": "outsider@example.com"}).status_code == 404

    invite = client.post(f"/api/projects/{project_id}/invitations", headers=owner, json={"email": "member@example.com"})
    assert invite.status_code == 201
    assert invite.json()["status"] == "pending"
    assert len(client.get(f"/api/projects/{project_id}/members", headers=owner).json()) == 1
    invitation_id = invite.json()["id"]
    assert client.post(f"/api/invitations/{invitation_id}/accept", headers=outsider).status_code == 404
    assert client.post(f"/api/invitations/{invitation_id}/accept", headers=member).json()["status"] == "accepted"
    assert len(client.get(f"/api/projects/{project_id}/members", headers=owner).json()) == 2
    task_path = f"/api/projects/{project_id}/tasks"
    assert client.post(task_path, headers=member, json={"title": "非法任务"}).status_code == 403
    task_response = client.post(task_path, headers=owner, json={
        "title": "实现登录", "assignee_id": member_id, "acceptance_criteria": "接口测试通过"
    })
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]
    task = f"{task_path}/{task_id}"
    assert client.post(f"{task}/start", headers=outsider).status_code == 404
    assert client.post(f"{task}/start", headers=owner).status_code == 403
    assert client.post(f"{task}/start", headers=member).json()["status"] == "in_progress"
    assert client.post(f"{task}/submit", headers=member, json={"note": ""}).status_code == 422
    assert client.post(f"{task}/submit", headers=member, json={"note": "首版完成"}).json()["status"] == "review"
    assert client.post(f"{task}/accept", headers=member, json={"note": ""}).status_code == 403
    assert client.post(f"{task}/reject", headers=owner, json={"note": "请补充测试"}).json()["status"] == "in_progress"
    assert client.post(f"{task}/submit", headers=member, json={"url": "https://example.com/result"}).json()["status"] == "review"
    assert client.post(f"{task}/accept", headers=owner, json={"note": "通过"}).json()["status"] == "done"
    actions = [event["action"] for event in client.get(f"{task}/events", headers=member).json()]
    assert actions == ["created", "started", "submitted", "rejected", "submitted", "accepted"]


def test_invitation_decline_and_meaningful_titles(client: TestClient):
    _, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    assert client.post("/api/projects", headers=owner, json={"name": "   "}).status_code == 422
    project_id = client.post("/api/projects", headers=owner, json={"name": "  Valid project  "}).json()["id"]
    assert client.post(f"/api/projects/{project_id}/tasks", headers=owner, json={"title": "  "}).status_code == 422
    invitation = client.post(f"/api/projects/{project_id}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    assert client.post(f"/api/invitations/{invitation['id']}/decline", headers=member).json()["status"] == "declined"
    assert client.get(f"/api/projects/{project_id}", headers=member).status_code == 404
    assert client.post(f"/api/invitations/{invitation['id']}/accept", headers=member).status_code == 409


def test_admin_and_profile(client: TestClient):
    admin_id, admin = register_and_login(client, "admin@example.com")
    _, member = register_and_login(client, "member@example.com")
    with Session(client.app.state.test_engine) as db:
        user = db.get(User, admin_id)
        user.is_admin = True
        db.commit()
    assert client.get("/api/admin/users", headers=member).status_code == 403
    created = client.post("/api/admin/users", headers=admin, json={
        "name": "Created", "email": "created@example.com", "password": "password123", "is_admin": False
    })
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert client.delete(f"/api/admin/users/{user_id}", headers=admin).json()["is_active"] is False
    assert client.post("/api/auth/login", json={"email": "created@example.com", "password": "password123"}).status_code == 401
    assert client.post(f"/api/admin/users/{user_id}/restore", headers=admin).json()["is_active"] is True
    assert client.patch("/api/profile", headers=member, json={"name": "   "}).status_code == 422
    assert client.patch("/api/profile", headers=member, json={"name": "  New name  "}).json()["name"] == "New name"
    assert client.post("/api/profile/password", headers=member, json={
        "current_password": "wrong-password", "new_password": "new-password123",
    }).status_code == 400
    assert client.post("/api/profile/password", headers=member, json={
        "current_password": "password123", "new_password": "new-password123",
    }).status_code == 200
    assert client.post("/api/auth/login", json={"email": "member@example.com", "password": "password123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "member@example.com", "password": "new-password123"}).status_code == 200

    image = Image.new("RGB", (100, 100), "red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    upload = client.post("/api/profile/avatar", headers=member, files={"file": ("avatar.png", buffer.getvalue(), "image/png")})
    assert upload.status_code == 200
    avatar = client.get(upload.json()["avatar_url"])
    assert avatar.status_code == 200
    assert avatar.headers["content-type"] == "image/jpeg"
    assert client.post("/api/profile/avatar", headers=member, files={"file": ("x.png", b"not image", "image/png")}).status_code == 422

    project_id = client.post("/api/projects", headers=member, json={"name": "Transfer project"}).json()["id"]
    member_id = client.get("/api/auth/me", headers=member).json()["id"]
    task_id = client.post(f"/api/projects/{project_id}/tasks", headers=member, json={
        "title": "Incomplete", "assignee_id": member_id,
    }).json()["id"]
    assert client.delete(f"/api/admin/users/{client.get('/api/auth/me', headers=member).json()['id']}", headers=admin).status_code == 409
    transfer = client.delete(f"/api/admin/users/{member_id}?successor_user_id={admin_id}", headers=admin)
    assert transfer.status_code == 200
    assert client.get(f"/api/projects/{project_id}", headers=admin).json()["owner_id"] == admin_id
    assert client.get(f"/api/projects/{project_id}/tasks", headers=admin).json()[0]["assignee_id"] is None
    assert client.get(f"/api/projects/{project_id}/tasks/{task_id}/events", headers=admin).json()[-1]["action"] == "unassigned"
    assert client.get("/api/auth/me", headers=member).status_code == 401


def test_project_delete_leave_and_admin_activities(client: TestClient):
    admin_id, admin = register_and_login(client, "admin@example.com")
    owner_id, owner = register_and_login(client, "owner@example.com")
    member_id, member = register_and_login(client, "member@example.com")
    next_owner_id, next_owner = register_and_login(client, "next@example.com")
    with Session(client.app.state.test_engine) as db:
        db.get(User, admin_id).is_admin = True
        db.commit()

    project_id = client.post("/api/projects", headers=owner, json={"name": "Finished project"}).json()["id"]
    project_url = f"/api/projects/{project_id}"
    assert client.get("/api/admin/project-activities", headers=member).status_code == 403
    notices = client.get("/api/admin/project-activities", headers=admin).json()
    assert [(item["action"], item["project_name"]) for item in notices] == [("created", "Finished project")]
    assert notices[0]["created_at"].endswith(("Z", "+00:00"))
    assert client.get(f"/api/admin/users/{owner_id}", headers=member).status_code == 403
    assert client.get(f"/api/admin/users/{owner_id}/project-activities", headers=member).status_code == 403
    assert client.get("/api/admin/users/9999", headers=admin).status_code == 404
    assert client.get("/api/admin/users/9999/project-activities", headers=admin).status_code == 404
    owner_summary = client.get(f"/api/admin/users/{owner_id}", headers=admin).json()
    assert owner_summary["project_activity_count"] == 1
    assert owner_summary["unread_project_activity_count"] == 1
    assert client.get(f"/api/admin/users/{owner_id}/project-activities", headers=admin).json() == notices
    users = client.get("/api/admin/users", headers=admin).json()
    assert next(user for user in users if user["id"] == owner_id)["project_activity_count"] == 1
    assert client.get("/api/admin/project-activities/unread-count", headers=admin).json()["count"] == 1
    assert client.post(f"/api/admin/project-activities/{notices[0]['id']}/read", headers=admin).json()["is_read"] is True
    assert client.get("/api/admin/project-activities/unread-count", headers=admin).json()["count"] == 0
    assert client.get(f"/api/admin/users/{owner_id}", headers=admin).json()["unread_project_activity_count"] == 0

    for email, headers in [("member@example.com", member), ("next@example.com", next_owner)]:
        invitation = client.post(f"{project_url}/invitations", headers=owner, json={"email": email}).json()
        assert client.post(f"/api/invitations/{invitation['id']}/accept", headers=headers).status_code == 200
    task_url = f"{project_url}/tasks"
    unfinished_id = client.post(task_url, headers=owner, json={"title": "Unfinished", "assignee_id": member_id}).json()["id"]
    finished_id = client.post(task_url, headers=owner, json={"title": "Finished", "assignee_id": member_id}).json()["id"]
    assert client.post(f"{task_url}/{finished_id}/start", headers=member).status_code == 200
    assert client.post(f"{task_url}/{finished_id}/submit", headers=member, json={"note": "Done"}).status_code == 200
    assert client.post(f"{task_url}/{finished_id}/accept", headers=owner, json={"note": "OK"}).status_code == 200

    confirmed_project = f"{project_url}?confirmation=Finished%20project"
    confirmed_exit = f"{project_url}/members/me?confirmation=Finished%20project"
    assert client.delete(project_url, headers=owner).status_code == 422
    assert client.delete(f"{project_url}?confirmation=Wrong", headers=owner).status_code == 409
    assert client.delete(confirmed_project, headers=member).status_code == 403
    assert client.delete(confirmed_exit, headers=owner).status_code == 409
    assert client.delete(f"{project_url}/members/me?confirmation=Wrong", headers=member).status_code == 409
    assert client.delete(confirmed_exit, headers=member).status_code == 204
    assert client.get(project_url, headers=member).status_code == 404
    tasks = {task["id"]: task for task in client.get(task_url, headers=owner).json()}
    assert tasks[unfinished_id]["assignee_id"] is None
    assert tasks[finished_id]["assignee_id"] == member_id
    assert tasks[finished_id]["assignee_name"] == "member"
    assert client.get(f"{task_url}/{unfinished_id}/events", headers=owner).json()[-1]["actor_name"] == "member"

    assert client.put(f"{project_url}/owner", headers=owner, json={"new_owner_id": next_owner_id}).status_code == 200
    assert client.delete(confirmed_exit, headers=owner).status_code == 204
    assert client.delete(confirmed_project, headers=owner).status_code == 404
    assert client.delete(confirmed_project, headers=next_owner).status_code == 204
    assert client.get(project_url, headers=next_owner).status_code == 404
    assert client.get(task_url, headers=next_owner).status_code == 404
    notices = client.get("/api/admin/project-activities", headers=admin).json()
    assert [item["action"] for item in notices] == ["deleted", "created"]
    assert notices[0]["project_name"] == "Finished project"
    assert client.get("/api/admin/project-activities/unread-count", headers=admin).json()["count"] == 1
    assert [item["action"] for item in client.get(f"/api/admin/users/{next_owner_id}/project-activities", headers=admin).json()] == ["deleted"]
    assert [item["action"] for item in client.get(f"/api/admin/users/{owner_id}/project-activities", headers=admin).json()] == ["created"]


def test_skill_profiles_and_project_visibility(client: TestClient):
    owner_id, owner = register_and_login(client, "owner@example.com")
    member_id, member = register_and_login(client, "member@example.com")
    _, outsider = register_and_login(client, "outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Skill project"}).json()["id"]
    project_skills_url = f"/api/projects/{project_id}/skills"
    own_profile_url = "/api/profile/skills"

    empty = client.get(own_profile_url, headers=member).json()
    assert empty == {"user_id": member_id, "weekly_hours": 0, "learning_goal": "", "skills": [], "updated_at": None}
    payload = {"weekly_hours": 12, "learning_goal": "  学习接口测试  ", "skills": [
        {"category": "language", "name": "  Python  ", "level": 4},
        {"category": "testing", "name": "Pytest", "level": 2},
    ]}
    assert client.put(own_profile_url, headers=member, json={**payload, "weekly_hours": 81}).status_code == 422
    assert client.put(own_profile_url, headers=member, json={**payload, "skills": [
        {"category": "language", "name": "Python", "level": 4},
        {"category": "language", "name": "python", "level": 2},
    ]}).status_code == 422
    saved = client.put(own_profile_url, headers=member, json=payload)
    assert saved.status_code == 200
    assert saved.json()["learning_goal"] == "学习接口测试"
    assert [skill["name"] for skill in saved.json()["skills"]] == ["Python", "Pytest"]
    assert saved.json()["updated_at"].endswith(("Z", "+00:00"))
    assert client.get(project_skills_url, headers=outsider).status_code == 404
    assert client.get(project_skills_url, headers=member).status_code == 404

    invite = client.post(f"/api/projects/{project_id}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    assert client.post(f"/api/invitations/{invite['id']}/accept", headers=member).status_code == 200
    assert client.get(project_skills_url, headers=member).status_code == 403
    profiles = client.get(project_skills_url, headers=owner).json()
    assert [entry["user"]["id"] for entry in profiles] == [owner_id, member_id]
    assert profiles[0]["profile"]["updated_at"] is None
    assert profiles[1]["profile"]["skills"][0]["name"] == "Python"

    replaced = client.put(own_profile_url, headers=member, json={
        "weekly_hours": 6, "learning_goal": "", "skills": [],
    })
    assert replaced.status_code == 200
    assert replaced.json()["skills"] == []
    assert client.get(project_skills_url, headers=owner).json()[1]["profile"]["weekly_hours"] == 6


def test_task_weight_suggestion_confirmation_and_permissions(client: TestClient):
    owner_id, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    _, outsider = register_and_login(client, "outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Weighted project"}).json()["id"]
    task_id = client.post(f"/api/projects/{project_id}/tasks", headers=owner, json={"title": "Build API"}).json()["id"]
    invite = client.post(f"/api/projects/{project_id}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    assert client.post(f"/api/invitations/{invite['id']}/accept", headers=member).status_code == 200
    factors = {"complexity": 4, "estimated_hours": 20, "importance": 5, "risk": 3}
    suggestion_url = f"/api/projects/{project_id}/tasks/{task_id}/weight/suggestion"
    weight_url = f"/api/projects/{project_id}/tasks/{task_id}/weight"
    weights_url = f"/api/projects/{project_id}/weights"

    assert client.get(weights_url, headers=outsider).status_code == 404
    assert client.post(suggestion_url, headers=member, json=factors).status_code == 403
    assert client.post(suggestion_url, headers=owner, json={**factors, "risk": 6}).status_code == 422
    suggestion = client.post(suggestion_url, headers=owner, json=factors)
    assert suggestion.status_code == 200
    assert suggestion.json()["suggested_score"] == 73
    assert "20 小时" in suggestion.json()["rationale"]
    assert client.get(weights_url, headers=owner).json() == []
    assert client.put(weight_url, headers=member, json={**factors, "confirmed_score": 73}).status_code == 403
    assert client.put(weight_url, headers=owner, json={**factors, "confirmed_score": 80}).status_code == 422
    confirmed = client.put(weight_url, headers=owner, json={
        **factors, "confirmed_score": 80, "adjustment_reason": "外部接口尚不稳定",
    })
    assert confirmed.status_code == 200
    assert confirmed.json()["suggested_score"] == 73
    assert confirmed.json()["confirmed_score"] == 80
    assert confirmed.json()["confirmed_by_id"] == owner_id
    assert confirmed.json()["updated_at"].endswith(("Z", "+00:00"))
    assert client.get(weights_url, headers=member).json()[0]["adjustment_reason"] == "外部接口尚不稳定"
    assert client.get(f"/api/projects/{project_id}/tasks/{task_id}/events", headers=owner).json()[-1]["action"] == "weight_confirmed"

    updated = client.put(weight_url, headers=owner, json={**factors, "confirmed_score": 73})
    assert updated.status_code == 200
    assert updated.json()["adjustment_reason"] == ""
    assert client.get(f"/api/projects/{project_id}/tasks", headers=owner).json()[0]["estimated_hours"] == 20
    assert client.patch(f"/api/projects/{project_id}/tasks/{task_id}", headers=owner,
                        json={"estimated_hours": 16}).status_code == 200
    assert client.get(weights_url, headers=owner).json() == []
    assert client.get(f"/api/projects/{project_id}/tasks/{task_id}/events", headers=owner).json()[-2]["action"] == "weight_invalidated"
    assert client.delete(f"/api/projects/{project_id}/tasks/{task_id}", headers=owner).status_code == 204
    assert client.get(weights_url, headers=owner).json() == []


def test_task_dependencies_reject_cycles_and_cross_project(client: TestClient):
    owner_id, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Dependency project"}).json()["id"]
    other_id = client.post("/api/projects", headers=owner, json={"name": "Other project"}).json()["id"]
    first = client.post(f"/api/projects/{project_id}/tasks", headers=owner,
                        json={"title": "First", "assignee_id": owner_id}).json()["id"]
    second = client.post(f"/api/projects/{project_id}/tasks", headers=owner,
                         json={"title": "Second", "assignee_id": owner_id}).json()["id"]
    third = client.post(f"/api/projects/{other_id}/tasks", headers=owner, json={"title": "Third"}).json()["id"]
    url = f"/api/projects/{project_id}/tasks/{second}/dependencies"
    assert client.put(url, headers=member, json={"depends_on_ids": [first]}).status_code == 404
    assert client.put(url, headers=owner, json={"depends_on_ids": [second]}).status_code == 422
    assert client.put(url, headers=owner, json={"depends_on_ids": [first, first]}).status_code == 422
    assert client.put(url, headers=owner, json={"depends_on_ids": [third]}).status_code == 422
    assert client.put(url, headers=owner, json={"depends_on_ids": [first]}).status_code == 200
    assert client.put(f"/api/projects/{project_id}/tasks/{first}/dependencies", headers=owner,
                      json={"depends_on_ids": [second]}).status_code == 422
    rows = client.get(f"/api/projects/{project_id}/dependencies", headers=owner).json()
    assert {row["task_id"]: row["depends_on_ids"] for row in rows} == {first: [], second: [first]}
    tasks_url = f"/api/projects/{project_id}/tasks"
    assert client.post(f"{tasks_url}/{second}/start", headers=owner).status_code == 409
    assert client.post(f"{tasks_url}/{first}/start", headers=owner).status_code == 200
    assert client.post(f"{tasks_url}/{first}/submit", headers=owner, json={"note": "Done"}).status_code == 200
    assert client.post(f"{tasks_url}/{first}/accept", headers=owner, json={"note": "OK"}).status_code == 200
    assert client.post(f"{tasks_url}/{second}/start", headers=owner).status_code == 200
    assert client.put(url, headers=owner, json={"depends_on_ids": []}).status_code == 409
    assert client.delete(f"/api/projects/{project_id}/tasks/{first}", headers=owner).status_code == 204
    assert client.get(f"/api/projects/{project_id}/dependencies", headers=owner).json() == [
        {"task_id": second, "depends_on_ids": []}
    ]


def test_ai_planning_draft_review_and_confirm(client: TestClient, monkeypatch):
    _, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    project_id = client.post("/api/projects", headers=owner, json={
        "name": "Planner project", "goal": "Build a web app", "requirements": "Login and dashboard",
    }).json()["id"]
    project_url = f"/api/projects/{project_id}"
    invite = client.post(f"{project_url}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=member)
    suggest_url = f"{project_url}/planning/suggest"
    assert client.post(suggest_url, headers=member).status_code == 403
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert client.post(suggest_url, headers=owner).status_code == 503

    async def fake_plan(project, existing_tasks):
        assert project.requirements == "Login and dashboard"
        assert existing_tasks == []
        return PlanningSuggestion.model_validate({"summary": "先做认证，再做看板", "tasks": [
            {"title": "Build login", "description": "Login form", "acceptance_criteria": "Login works",
             "estimated_hours": 8, "required_skills": ["Vue"], "depends_on": [], "rationale": "基础能力"},
            {"title": "Build dashboard", "description": "Task board", "acceptance_criteria": "Tasks visible",
             "estimated_hours": 12, "required_skills": ["Vue"], "depends_on": [0], "rationale": "依赖登录"},
        ]})

    monkeypatch.setattr(planning_api, "generate_plan", fake_plan)
    draft_response = client.post(suggest_url, headers=owner)
    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert draft["suggestion"]["tasks"][1]["depends_on"] == [0]
    assert client.get(f"{project_url}/tasks", headers=owner).json() == []
    assert client.get(f"{project_url}/planning/drafts", headers=member).status_code == 403
    assert client.get(f"{project_url}/planning/drafts", headers=owner).json()[0]["id"] == draft["id"]
    confirm_url = f"{project_url}/planning/drafts/{draft['id']}/confirm"
    selected = [
        {"source_index": 0, "title": "Build login", "description": "Edited login", "acceptance_criteria": "Pass test",
         "estimated_hours": 10, "required_skills": ["Vue", "API"], "depends_on": []},
        {"source_index": 1, "title": "Build dashboard", "description": "Task board", "acceptance_criteria": "Tasks visible",
         "estimated_hours": 12, "required_skills": ["Vue"], "depends_on": [0]},
    ]
    assert client.post(confirm_url, headers=member, json={"tasks": selected}).status_code == 403
    assert client.post(confirm_url, headers=owner, json={"tasks": [selected[1]]}).status_code == 422
    assert client.post(confirm_url, headers=owner, json={"tasks": [
        {**selected[0], "depends_on": [1]}, selected[1],
    ]}).status_code == 422
    assert client.get(f"{project_url}/tasks", headers=owner).json() == []
    confirmed = client.post(confirm_url, headers=owner, json={"tasks": selected})
    assert confirmed.status_code == 200
    first_id, second_id = confirmed.json()
    saved_tasks = {task["id"]: task for task in client.get(f"{project_url}/tasks", headers=owner).json()}
    assert saved_tasks[first_id]["estimated_hours"] == 10
    assert saved_tasks[first_id]["required_skills"] == ["Vue", "API"]
    assert client.get(f"{project_url}/dependencies", headers=owner).json() == [
        {"task_id": first_id, "depends_on_ids": []},
        {"task_id": second_id, "depends_on_ids": [first_id]},
    ]
    assert client.post(confirm_url, headers=owner, json={"tasks": selected}).status_code == 409


def test_existing_sqlite_project_and_task_rows_survive_migration(monkeypatch):
    legacy_engine = create_engine("sqlite://", poolclass=StaticPool)
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO projects (id, name) VALUES (1, 'Legacy project')"))
        connection.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO tasks (id, title) VALUES (1, 'Legacy task')"))
    monkeypatch.setattr(db_module, "engine", legacy_engine)
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite://")
    db_module.migrate_sqlite_project_columns()
    db_module.migrate_sqlite_task_columns()
    db_module.migrate_sqlite_project_columns()
    db_module.migrate_sqlite_task_columns()
    with legacy_engine.connect() as connection:
        assert connection.execute(text("SELECT name, requirements FROM projects WHERE id = 1")).one() == ("Legacy project", "")
        assert connection.execute(text("SELECT title, estimated_hours, required_skills FROM tasks WHERE id = 1")).one() == ("Legacy task", None, "[]")
    legacy_engine.dispose()


def test_agents_sdk_planning_adapter_without_network(monkeypatch):
    from agents import OpenAIResponsesModel, Runner

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    async def fake_run(agent, prompt, *, run_config):
        assert agent.output_type is RawPlan
        assert isinstance(agent.model, OpenAIResponsesModel)
        assert agent.model.model == "deepseek-flash"
        assert str(agent.model._client.base_url) == "https://api.deepseek.com"
        assert run_config.tracing_disabled is True
        assert "Course project" in prompt
        return SimpleNamespace(final_output=RawPlan(
            summary="先完成基础功能",
            tasks=[{
                "title": "Create login", "description": "Implement login", "acceptance_criteria": "Login succeeds",
                "estimated_hours": 8, "required_skills": ["Python"], "depends_on": [], "rationale": "基础模块",
            }],
        ))

    monkeypatch.setattr(Runner, "run", fake_run)
    project = Project(name="Course project", goal="Build platform", requirements="Login", tech_stack="FastAPI", owner_id=1)
    result = asyncio.run(generate_plan(project, []))
    assert result.tasks[0].title == "Create login"


def test_ai_planning_retries_when_model_returns_no_tasks(monkeypatch):
    from agents import Runner

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    calls = []

    async def fake_run(agent, prompt, *, run_config):
        calls.append(prompt)
        if len(calls) == 1:
            return SimpleNamespace(final_output=RawPlan(summary="无任务", tasks=[]))
        return SimpleNamespace(final_output=RawPlan(summary="补充任务", tasks=[{
            "title": "Create login", "description": "Implement login", "acceptance_criteria": "Login succeeds",
            "estimated_hours": 8, "required_skills": ["Python"], "depends_on": [], "rationale": "基础模块",
        }]))

    monkeypatch.setattr(Runner, "run", fake_run)
    project = Project(name="Course project", goal="Build platform", requirements="Login", tech_stack="FastAPI", owner_id=1)
    result = asyncio.run(generate_plan(project, []))
    assert len(calls) == 2
    assert "上一次输出了 0 项任务" in calls[1]
    assert result.tasks[0].title == "Create login"


def test_ai_planning_reports_count_after_failed_retry(monkeypatch):
    from agents import Runner
    from fastapi import HTTPException

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    calls = []

    async def fake_run(agent, prompt, *, run_config):
        calls.append(prompt)
        return SimpleNamespace(final_output=RawPlan(summary="无任务", tasks=[]))

    monkeypatch.setattr(Runner, "run", fake_run)
    project = Project(name="Course project", goal="Build platform", requirements="Login", tech_stack="FastAPI", owner_id=1)
    with pytest.raises(HTTPException) as error:
        asyncio.run(generate_plan(project, []))
    assert len(calls) == 2
    assert error.value.status_code == 502
    assert "返回了 0 项任务" in error.value.detail


def test_assignment_suggestion_review_and_confirm(client: TestClient, monkeypatch):
    owner_id, owner = register_and_login(client, "owner@example.com")
    member_id, member = register_and_login(client, "member@example.com")
    outsider_id, outsider = register_and_login(client, "outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Team project"}).json()["id"]
    base = f"/api/projects/{project_id}"
    invite = client.post(f"{base}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=member)
    client.put("/api/profile/skills", headers=member, json={
        "weekly_hours": 12, "learning_goal": "学习 FastAPI", "skills": [
            {"category": "backend", "name": "Python", "level": 4},
        ],
    })
    first = client.post(f"{base}/tasks", headers=owner, json={
        "title": "Build API", "required_skills": ["Python"], "estimated_hours": 6,
    }).json()["id"]
    second = client.post(f"{base}/tasks", headers=owner, json={
        "title": "Write tests", "required_skills": ["Python"], "estimated_hours": 4,
    }).json()["id"]
    suggest_url = f"{base}/assignments/suggest"
    assert client.post(suggest_url, headers=member).status_code == 403
    assert client.post(suggest_url, headers=outsider).status_code == 404

    async def fake_suggestion(context):
        assert [task["id"] for task in context["tasks"]] == [first, second]
        candidate = next(item for item in context["tasks"][0]["candidates"] if item["id"] == member_id)
        assert candidate["metrics"]["skill_match_ratio"] == 0.8
        assert candidate["metrics"]["remaining_hours"] == 12
        assert candidate["metrics"]["learning_goal_matches"] == []
        return AssignmentSuggestion.model_validate({
            "summary": "兼顾技能与负载", "recommendations": [
                {"task_id": first, "assignee_id": member_id, "reason": "Python 4 级", "risk_note": ""},
                {"task_id": second, "assignee_id": owner_id, "reason": "平衡工作量", "risk_note": "画像未填写"},
            ],
        })

    monkeypatch.setattr(assignments_api, "generate_assignment_suggestion", fake_suggestion)
    draft_response = client.post(suggest_url, headers=owner)
    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert len(draft["suggestion"]["recommendations"]) == 2
    assert all(task["assignee_id"] is None for task in client.get(f"{base}/tasks", headers=owner).json())
    assert client.get(f"{base}/assignments/drafts", headers=member).status_code == 403
    assert client.get(f"{base}/assignments/drafts", headers=owner).json()[0]["id"] == draft["id"]
    confirm_url = f"{base}/assignments/drafts/{draft['id']}/confirm"
    selected = [{"task_id": first, "assignee_id": owner_id}, {"task_id": second, "assignee_id": member_id}]
    assert client.post(confirm_url, headers=member, json={"assignments": selected}).status_code == 403
    assert client.post(confirm_url, headers=owner, json={"assignments": [
        {"task_id": first, "assignee_id": outsider_id},
    ]}).status_code == 422
    assert client.post(confirm_url, headers=owner, json={"assignments": selected}).json() == [first, second]
    tasks = {task["id"]: task for task in client.get(f"{base}/tasks", headers=owner).json()}
    assert tasks[first]["assignee_id"] == owner_id
    assert tasks[second]["assignee_id"] == member_id
    assert client.get(f"{base}/tasks/{first}/events", headers=owner).json()[-1]["action"] == "assigned"
    assert client.post(confirm_url, headers=owner, json={"assignments": selected}).status_code == 409


def test_assignment_draft_rejects_invalid_or_stale_recommendations(client: TestClient, monkeypatch):
    owner_id, owner = register_and_login(client, "owner@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Team project"}).json()["id"]
    base = f"/api/projects/{project_id}"
    task_id = client.post(f"{base}/tasks", headers=owner, json={"title": "Build API"}).json()["id"]
    suggest_url = f"{base}/assignments/suggest"

    async def invalid_suggestion(context):
        return AssignmentSuggestion.model_validate({"summary": "无效", "recommendations": []})

    monkeypatch.setattr(assignments_api, "generate_assignment_suggestion", invalid_suggestion)
    assert client.post(suggest_url, headers=owner).status_code == 502
    assert client.get(f"{base}/assignments/drafts", headers=owner).json() == []

    async def valid_suggestion(context):
        return AssignmentSuggestion.model_validate({"summary": "建议", "recommendations": [
            {"task_id": task_id, "assignee_id": owner_id, "reason": "项目负责人可承接"},
        ]})

    monkeypatch.setattr(assignments_api, "generate_assignment_suggestion", valid_suggestion)
    draft_id = client.post(suggest_url, headers=owner).json()["id"]
    client.patch(f"{base}/tasks/{task_id}", headers=owner, json={"assignee_id": owner_id})
    confirm_url = f"{base}/assignments/drafts/{draft_id}/confirm"
    assert client.post(confirm_url, headers=owner, json={"assignments": [
        {"task_id": task_id, "assignee_id": owner_id},
    ]}).status_code == 409


def test_matching_metrics_distinguish_missing_profile_from_zero_hours():
    missing = candidate_metrics(["Python"], [], 0, 0, "", False)
    unavailable = candidate_metrics(["Python"], [], 0, 0, "", True)
    assert missing["remaining_hours"] is None
    assert unavailable["remaining_hours"] == 0


def test_assignment_agent_uses_deepseek_without_network(monkeypatch):
    from agents import OpenAIResponsesModel, Runner

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    async def fake_run(agent, prompt, *, run_config):
        assert agent.output_type is RawAssignmentPlan
        assert isinstance(agent.model, OpenAIResponsesModel)
        assert agent.model.model == "deepseek-flash"
        assert str(agent.model._client.base_url) == "https://api.deepseek.com"
        assert run_config.tracing_disabled is True
        assert "Build API" in prompt
        return SimpleNamespace(final_output=RawAssignmentPlan(
            summary="建议", recommendations=[
                {"task_id": 1, "assignee_id": 2, "reason": "有 Python 经验", "risk_note": ""},
            ],
        ))

    monkeypatch.setattr(Runner, "run", fake_run)
    result = asyncio.run(generate_assignment_suggestion({"tasks": [{"id": 1, "title": "Build API"}]}))
    assert result.recommendations[0].assignee_id == 2


def test_progress_rules_detect_overdue_blocked_and_missing_evidence():
    from datetime import date

    tasks = [
        Task(id=1, title="API", status="todo", due_date=date(2026, 10, 14), assignee_id=1, estimated_hours=8),
        Task(id=2, title="UI", status="todo", due_date=date(2026, 10, 18), assignee_id=None),
        Task(id=3, title="Review", status="review", assignee_id=1, estimated_hours=4),
    ]
    members = [User(id=1, name="A"), User(id=2, name="B")]
    snapshot = build_progress_snapshot(tasks, [(2, 1)], members, date(2026, 10, 15))
    findings = {item.code: item for item in snapshot.findings}
    assert snapshot.completion_rate == 0
    assert findings["overdue"].task_ids == [1]
    assert findings["due_soon"].task_ids == [2]
    assert findings["blocked"].task_ids == [2]
    assert findings["unassigned"].task_ids == [2]
    assert findings["missing_evidence"].task_ids == [3]
    assert findings["workload_concentration"].member_id == 1


def test_progress_report_permissions_and_snapshot_history(client: TestClient, monkeypatch):
    owner_id, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Course project"}).json()["id"]
    base = f"/api/projects/{project_id}"
    invite = client.post(f"{base}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=member)
    report_url = f"{base}/progress/reports"
    assert client.post(report_url, headers=owner).status_code == 422
    first = client.post(f"{base}/tasks", headers=owner, json={
        "title": "API", "due_date": "2020-01-01", "assignee_id": owner_id, "estimated_hours": 8,
    }).json()["id"]
    second = client.post(f"{base}/tasks", headers=owner, json={"title": "UI"}).json()["id"]
    client.put(f"{base}/tasks/{second}/dependencies", headers=owner,
               json={"depends_on_ids": [first]})
    assert client.get(f"{base}/progress/snapshot", headers=member).status_code == 403
    assert client.post(report_url, headers=member).status_code == 403
    snapshot = client.get(f"{base}/progress/snapshot", headers=owner)
    assert snapshot.status_code == 200
    assert snapshot.json()["total_tasks"] == 2
    assert {item["code"] for item in snapshot.json()["findings"]} >= {"overdue", "blocked", "unassigned"}

    async def fake_diagnosis(context):
        assert context["snapshot"]["total_tasks"] == 2
        assert {task["id"] for task in context["tasks"]} == {first, second}
        return ProgressDiagnosis.model_validate({
            "summary": "API 逾期且 UI 受阻", "actions": [
                {"title": "先完成 API", "detail": "解除 UI 的前置阻塞", "related_task_ids": [first, second]},
            ],
        })

    monkeypatch.setattr(progress_api, "generate_progress_diagnosis", fake_diagnosis)
    created = client.post(report_url, headers=owner)
    assert created.status_code == 201
    assert created.json()["diagnosis"]["actions"][0]["related_task_ids"] == [first, second]
    assert client.get(report_url, headers=member).status_code == 403
    assert client.get(report_url, headers=owner).json()[0]["id"] == created.json()["id"]
    assert client.get(f"{base}/tasks", headers=owner).json()[0]["assignee_id"] is None

    async def invalid_diagnosis(context):
        return ProgressDiagnosis.model_validate({
            "summary": "错误引用", "actions": [
                {"title": "操作", "detail": "无效任务", "related_task_ids": [9999]},
            ],
        })

    monkeypatch.setattr(progress_api, "generate_progress_diagnosis", invalid_diagnosis)
    assert client.post(report_url, headers=owner).status_code == 502
    assert len(client.get(report_url, headers=owner).json()) == 1


def test_progress_agent_uses_deepseek_without_network(monkeypatch):
    from agents import OpenAIResponsesModel, Runner

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    async def fake_run(agent, prompt, *, run_config):
        assert agent.output_type is RawProgressDiagnosis
        assert isinstance(agent.model, OpenAIResponsesModel)
        assert agent.model.model == "deepseek-flash"
        assert str(agent.model._client.base_url) == "https://api.deepseek.com"
        assert run_config.tracing_disabled is True
        assert "Course project" in prompt
        return SimpleNamespace(final_output=RawProgressDiagnosis(
            summary="进度正常", actions=[],
        ))

    monkeypatch.setattr(Runner, "run", fake_run)
    result = asyncio.run(generate_progress_diagnosis({"project": {"name": "Course project"}}))
    assert result.summary == "进度正常"


def test_analytics_trend_uses_surviving_tasks_and_acceptance_events():
    from datetime import date, datetime, timezone

    first = Task(id=1, title="API", status="done", assignee_id=1, estimated_hours=8,
                 created_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    second = Task(id=2, title="UI", status="todo", assignee_id=None, estimated_hours=5,
                  due_date=date(2026, 10, 8),
                  created_at=datetime(2026, 10, 5, tzinfo=timezone.utc))
    accepted = TaskEvent(task_id=1, action="accepted", created_at=datetime(2026, 10, 3, tzinfo=timezone.utc))
    weight = TaskWeight(task_id=1, confirmed_score=72)
    result = build_project_analytics([first, second], [User(id=1, name="Owner")],
                                     [weight], [accepted], date(2026, 10, 6))
    points = {point.date: point for point in result.trend}
    assert points[date(2026, 10, 2)].total_tasks == 1
    assert points[date(2026, 10, 2)].completed_tasks == 0
    assert points[date(2026, 10, 4)].completed_tasks == 1
    assert points[date(2026, 10, 6)].total_tasks == 2
    assert result.status_counts == {"todo": 1, "in_progress": 0, "review": 0, "done": 1}
    assert result.members[0].estimated_hours == 8
    assert result.members[1].member_name == "未分配"
    assert result.weights[0].confirmed_score == 72
    assert result.schedule[0].task_title == "UI"
    assert result.schedule[0].due_date == date(2026, 10, 8)


def test_project_analytics_permissions_and_deleted_task_scope(client: TestClient):
    owner_id, owner = register_and_login(client, "owner@example.com")
    _, member = register_and_login(client, "member@example.com")
    _, outsider = register_and_login(client, "outsider@example.com")
    project_id = client.post("/api/projects", headers=owner, json={"name": "Charts project"}).json()["id"]
    base = f"/api/projects/{project_id}"
    invite = client.post(f"{base}/invitations", headers=owner, json={"email": "member@example.com"}).json()
    client.post(f"/api/invitations/{invite['id']}/accept", headers=member)
    first = client.post(f"{base}/tasks", headers=owner, json={
        "title": "API", "assignee_id": owner_id, "estimated_hours": 8,
    }).json()["id"]
    second = client.post(f"{base}/tasks", headers=owner, json={
        "title": "UI", "due_date": "2026-11-01",
    }).json()["id"]
    with Session(client.app.state.test_engine) as db:
        db.add(TaskWeight(task_id=first, complexity=3, estimated_hours=8, importance=3, risk=2,
                          suggested_score=60, confirmed_score=65, rationale="课程重点",
                          adjustment_reason="", confirmed_by_id=owner_id))
        db.commit()
    client.post(f"{base}/tasks/{first}/start", headers=owner)
    client.post(f"{base}/tasks/{first}/submit", headers=owner, json={"note": "代码已提交"})
    client.post(f"{base}/tasks/{first}/accept", headers=owner, json={"note": "通过"})
    url = f"{base}/analytics"
    assert client.get(url, headers=outsider).status_code == 404
    response = client.get(url, headers=member)
    assert response.status_code == 200
    data = response.json()
    assert data["total_tasks"] == 2
    assert data["completed_tasks"] == 1
    assert data["completion_rate"] == 50
    assert data["trend"][-1]["completed_tasks"] == 1
    assert data["weights"][0]["confirmed_score"] == 65
    assert data["schedule"][0]["task_id"] == second
    assert next(item for item in data["members"] if item["member_id"] is None)["status_counts"]["todo"] == 1
    assert client.delete(f"{base}/tasks/{first}", headers=owner).status_code == 204
    after = client.get(url, headers=member).json()
    assert after["total_tasks"] == 1
    assert after["trend"][-1]["completed_tasks"] == 0
    assert after["weights"] == []


