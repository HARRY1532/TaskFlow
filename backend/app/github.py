"""Read-only validation of public GitHub repositories and task code links."""

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException


PART = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "TaskFlow-AI"}


def github_path(url: str) -> list[str]:
    try:
        parsed = urlsplit(url.strip())
        invalid_authority = parsed.hostname != "github.com" or parsed.port is not None
    except ValueError:
        raise HTTPException(422, "GitHub 链接无效") from None
    if (parsed.scheme != "https" or invalid_authority
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(422, "请填写标准的 https://github.com 链接")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or not all(PART.fullmatch(item) and item not in (".", "..") for item in parts[:2]):
        raise HTTPException(422, "GitHub 仓库地址无效")
    return parts


def repository_name(url: str) -> str:
    parts = github_path(url)
    if len(parts) != 2 or parts[1].endswith(".git"):
        raise HTTPException(422, "请输入 GitHub 仓库主页地址")
    return f"{parts[0]}/{parts[1]}"


def code_reference(url: str, repository: str) -> tuple[str, str]:
    parts = github_path(url)
    if "/".join(parts[:2]).casefold() != repository.casefold() or len(parts) != 4:
        raise HTTPException(422, "代码链接必须是当前项目仓库的提交或 PR")
    kind, identifier = parts[2:]
    if kind == "pull" and identifier.isdecimal() and int(identifier) > 0:
        return "pull", str(int(identifier))
    if kind == "commit" and SHA.fullmatch(identifier):
        return "commit", identifier.lower()
    raise HTTPException(422, "仅支持 GitHub PR 或提交详情链接")


def github_get(path: str) -> dict | list:
    try:
        with httpx.Client(base_url="https://api.github.com", headers=HEADERS,
                          timeout=8.0, follow_redirects=False) as client:
            response = client.get(path)
        if response.status_code == 404:
            raise HTTPException(422, "GitHub 资源不存在或不是公开资源")
        if response.status_code in (403, 429):
            raise HTTPException(503, "GitHub API 请求受限，请稍后重试")
        if 300 <= response.status_code < 400:
            raise HTTPException(422, "GitHub 资源已迁移，请使用当前地址")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, (dict, list)):
            raise ValueError("unexpected GitHub payload")
        return data
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub 暂时不可用，请稍后重试") from None


def verify_repository(url: str) -> str:
    repository = repository_name(url)
    data = github_get(f"/repos/{repository}")
    if data.get("private") is not False or data.get("full_name", "").casefold() != repository.casefold():
        raise HTTPException(422, "只能绑定公开且地址准确的 GitHub 仓库")
    return f"https://github.com/{data['full_name']}"


def inspect_code(url: str, repository_url: str) -> dict:
    repository = repository_name(repository_url)
    kind, identifier = code_reference(url, repository)
    path = f"/repos/{repository}/pulls/{identifier}" if kind == "pull" else f"/repos/{repository}/commits/{identifier}"
    data = github_get(path)
    checked_at = datetime.now(timezone.utc).isoformat()
    if kind == "pull":
        return {
            "kind": "pull", "title": data.get("title") or f"PR #{identifier}",
            "author": (data.get("user") or {}).get("login") or "未知",
            "state": "merged" if data.get("merged_at") else data.get("state", "unknown"),
            "sha": (data.get("head") or {}).get("sha") or "",
            "number": int(identifier), "checked_at": checked_at,
        }
    return {
        "kind": "commit", "title": ((data.get("commit") or {}).get("message") or "").splitlines()[0][:160],
        "author": (data.get("author") or {}).get("login") or ((data.get("commit") or {}).get("author") or {}).get("name") or "未知",
        "state": "available", "sha": data.get("sha") or identifier,
        "number": None, "checked_at": checked_at,
    }


def pull_request_snapshot(url: str, repository_url: str) -> dict:
    repository = repository_name(repository_url)
    kind, number = code_reference(url, repository)
    if kind != "pull":
        raise HTTPException(422, "AI 辅助验收目前仅支持 GitHub PR")
    path = f"/repos/{repository}/pulls/{number}"
    before = github_get(path)
    files = github_get(f"{path}/files?per_page=21&page=1")
    if not isinstance(before, dict) or not isinstance(files, list):
        raise HTTPException(502, "GitHub 返回的数据格式不正确")
    if not files or len(files) > 20:
        raise HTTPException(422, "仅支持包含 1 至 20 个改动文件的 PR")
    selected = []
    patch_size = 0
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get("filename"), str):
            raise HTTPException(502, "GitHub 文件列表格式不正确")
        name = file["filename"]
        patch = file.get("patch")
        if len(name) > 500 or (patch is not None and not isinstance(patch, str)):
            raise HTTPException(422, "PR 文件路径或补丁不符合分析范围")
        patch_size += len(patch or "")
        if patch_size > 16000:
            raise HTTPException(422, "PR 补丁内容过长，暂不支持 AI 分析")
        selected.append({
            "path": name, "status": str(file.get("status") or "unknown"),
            "additions": file.get("additions") or 0, "deletions": file.get("deletions") or 0,
            "patch": patch,
        })
    after = github_get(path)
    if not isinstance(after, dict):
        raise HTTPException(502, "GitHub 返回的数据格式不正确")
    sha = (before.get("head") or {}).get("sha")
    if not sha or sha != (after.get("head") or {}).get("sha"):
        raise HTTPException(409, "PR 在读取过程中发生变化，请重试")
    return {
        "repository": repository, "number": int(number), "url": url,
        "title": after.get("title") or f"PR #{number}", "head_sha": sha,
        "author": (after.get("user") or {}).get("login") or "未知",
        "state": "merged" if after.get("merged_at") else after.get("state", "unknown"),
        "fetched_at": datetime.now(timezone.utc).isoformat(), "files": selected,
    }
