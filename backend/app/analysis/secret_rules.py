"""Conservative checks before sending task and PR text to an external model."""

import re


TOKEN = re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
ENV_VALUE = re.compile(r"(?im)^\+?\s*[A-Z][A-Z0-9_]*(?:_KEY|_SECRET|_TOKEN|_PASSWORD)\s*=\s*\S{8,}")
QUOTED_SECRET = re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"\n]{12,}['\"]")
URL_CREDENTIALS = re.compile(r"(?i)https?://[^/\s:]+:[^@/\s]+@")


def secret_warnings(context: dict) -> list[str]:
    warnings = []
    task = context["task"]
    texts = [task.get("title") or "", task.get("description") or "",
             task.get("acceptance_criteria") or "", task.get("test_note") or ""]
    for item in task.get("development_checklist") or []:
        texts.extend([item.get("title") or "", item.get("detail") or ""])
    pr = context["pr"]
    texts.append(pr.get("title") or "")
    for file in pr["files"]:
        path = file["path"]
        name = path.rsplit("/", 1)[-1].lower()
        if name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key")) or name in ("id_rsa", "id_ed25519"):
            warnings.append(f"敏感文件路径：{path}")
        texts.extend([path, file.get("patch") or ""])
    warnings.extend(text_warnings("\n".join(texts)))
    return warnings


def text_warnings(text: str) -> list[str]:
    warnings = []
    for label, pattern in (
        ("疑似 API 令牌", TOKEN), ("私钥内容", PRIVATE_KEY),
        ("环境变量密钥", ENV_VALUE), ("硬编码凭据", QUOTED_SECRET),
        ("URL 内嵌凭据", URL_CREDENTIALS),
    ):
        if pattern.search(text):
            warnings.append(label)
    return warnings
