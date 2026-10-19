from ..schemas import WeightFactors, WeightSuggestionOut


def suggest_weight(factors: WeightFactors) -> WeightSuggestionOut:
    """Return an absolute 1–100 planning score, not a share of member contribution."""
    complexity_points = factors.complexity * 6
    hours_points = round(min(factors.estimated_hours, 40) * 30 / 40)
    importance_points = factors.importance * 5
    risk_points = factors.risk * 3
    score = complexity_points + hours_points + importance_points + risk_points
    rationale = (
        f"技术复杂度 {factors.complexity}/5 × 6 = {complexity_points}；"
        f"预计工时 {factors.estimated_hours} 小时（按最多 40 小时计）= {hours_points}；"
        f"项目重要性 {factors.importance}/5 × 5 = {importance_points}；"
        f"实现风险 {factors.risk}/5 × 3 = {risk_points}。"
        f"合计 {score}/100。此分值用于任务规划，不代表成员贡献或成绩。"
    )
    return WeightSuggestionOut(**factors.model_dump(), suggested_score=score, rationale=rationale)
