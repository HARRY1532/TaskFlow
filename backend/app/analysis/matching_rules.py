"""Simple, inspectable inputs for AI task assignment."""


def candidate_metrics(required_skills: list[str], member_skills: list[tuple[str, int]],
                      weekly_hours: int, assigned_hours: int, learning_goal: str,
                      profile_filled: bool) -> dict:
    levels = {name.strip().casefold(): level for name, level in member_skills}
    matched = [name for name in required_skills if name.strip().casefold() in levels]
    skill_score = round(sum(levels[name.strip().casefold()] for name in matched) /
                        (5 * len(required_skills)), 2) if required_skills else None
    available_hours = max(0, weekly_hours - assigned_hours) if profile_filled else None
    goal_matches = [name for name in required_skills if name.strip().casefold() in learning_goal.casefold()]
    return {
        "matched_skills": matched,
        "skill_match_ratio": skill_score,
        "weekly_hours": weekly_hours if profile_filled else None,
        "current_open_task_hours": assigned_hours,
        "remaining_hours": available_hours,
        "learning_goal_matches": goal_matches,
    }
