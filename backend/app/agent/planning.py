import json
import os

from fastapi import HTTPException
from pydantic import BaseModel

from ..models import Project, Task
from ..schemas import PlanningSuggestion


class RawPlannedTask(BaseModel):
    title: str
    description: str
    acceptance_criteria: str
    estimated_hours: int
    required_skills: list[str]
    depends_on: list[int]
    rationale: str


class RawPlan(BaseModel):
    summary: str
    tasks: list[RawPlannedTask]


async def generate_plan(project: Project, existing_tasks: list[Task]) -> PlanningSuggestion:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "AI 任务规划尚未配置 DEEPSEEK_API_KEY")
    try:
        from agents import Agent, AsyncOpenAI, OpenAIResponsesModel, RunConfig, Runner
    except ImportError:
        raise HTTPException(503, "请先安装后端的 openai-agents 依赖") from None

    agent = Agent(
        name="TaskFlow 课程项目规划",
        instructions=(
            "你是高校软件工程项目的任务规划助手。根据给定项目目标、详细需求、技术栈和已有任务，"
            "提出 3 到 12 项具体且可验收的新任务，不重复已有任务。"
            "输出中文；每项都要有明确标题、描述、验收条件、预计工时、所需技能和简短依据。"
            "depends_on 使用本次输出任务的从 0 开始的索引，仅指向真正需要先完成的任务；不能自依赖或形成环。"
            "你只生成建议，不执行写入，也不评定成员贡献或成绩。"
        ),
        output_type=RawPlan,
        model=OpenAIResponsesModel(
            model="deepseek-flash",
            openai_client=AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com"),
        ),
    )
    context = json.dumps({
        "project_name": project.name,
        "goal": project.goal,
        "requirements": project.requirements,
        "tech_stack": project.tech_stack,
        "existing_tasks": [{"title": task.title, "description": task.description} for task in existing_tasks],
    }, ensure_ascii=False)
    try:
        run_config = RunConfig(tracing_disabled=True)
        result = await Runner.run(agent, context, run_config=run_config)
        plan = PlanningSuggestion.model_validate(result.final_output.model_dump())
        if not 1 <= len(plan.tasks) <= 20:
            retry_context = (
                f"{context}\n上一次输出了 {len(plan.tasks)} 项任务，数量不符合要求。"
                "请重新规划，必须返回 3 到 12 项不重复、可验收的新任务。"
                "如果已有任务覆盖部分需求，请规划剩余工作，不能返回空列表。"
            )
            result = await Runner.run(agent, retry_context, run_config=run_config)
            plan = PlanningSuggestion.model_validate(result.final_output.model_dump())
    except Exception:
        raise HTTPException(502, "AI 规划服务暂时不可用，请稍后重试") from None
    if not 1 <= len(plan.tasks) <= 20:
        raise HTTPException(502, f"AI 返回了 {len(plan.tasks)} 项任务，要求为 1～20 项；请补充项目需求后重试")
    return plan
