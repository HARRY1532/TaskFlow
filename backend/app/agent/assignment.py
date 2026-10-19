import json
import os

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..schemas import AssignmentSuggestion


class RawRecommendation(BaseModel):
    task_id: int
    assignee_id: int
    reason: str = Field(min_length=1)
    risk_note: str = ""


class RawAssignmentPlan(BaseModel):
    summary: str
    recommendations: list[RawRecommendation]


async def generate_assignment_suggestion(context: dict) -> AssignmentSuggestion:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "AI 智能分工尚未配置 DEEPSEEK_API_KEY")
    try:
        from agents import Agent, AsyncOpenAI, OpenAIResponsesModel, RunConfig, Runner
    except ImportError:
        raise HTTPException(503, "请先安装后端的 openai-agents 依赖") from None

    agent = Agent(
        name="TaskFlow 智能分工",
        instructions=(
            "你是高校课程项目分工助手。根据项目任务、有效成员的真实技能画像、每周可用时间、"
            "现有工作量和学习目标，为输入中的每个任务推荐恰好一名输入中的成员。"
            "必须返回所有任务且各出现一次；task_id 和 assignee_id 只能取输入中已有的 ID。"
            "兼顾技能适配、工时负载均衡和能力成长，不要把没有填写画像视为零能力。"
            "reason 用中文说明与任务及成员数据有关的具体理由；若缺少画像、技能不匹配或工时紧张，"
            "在 risk_note 中如实指出。不得捏造技能或自动修改任务，不评定成员贡献和成绩。"
        ),
        output_type=RawAssignmentPlan,
        model=OpenAIResponsesModel(
            model="deepseek-flash",
            openai_client=AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com"),
        ),
    )
    try:
        result = await Runner.run(agent, json.dumps(context, ensure_ascii=False),
                                  run_config=RunConfig(tracing_disabled=True))
        return AssignmentSuggestion.model_validate(result.final_output.model_dump())
    except Exception:
        raise HTTPException(502, "AI 分工服务暂时不可用，请稍后重试") from None
