from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator


def meaningful(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("必须填写实际内容")
    return trimmed


def clean_skill_names(values: list[str]) -> list[str]:
    cleaned = [meaningful(value) for value in values]
    if any(len(value) > 60 for value in cleaned) or len({value.casefold() for value in cleaned}) != len(cleaned):
        raise ValueError("所需技能不能重复，且每项不能超过 60 字符")
    return cleaned


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def mark_sqlite_utc(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return meaningful(value)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: int
    email: EmailStr
    name: str
    is_admin: bool
    is_active: bool
    avatar_url: str | None


class AdminUserOut(UserOut):
    project_activity_count: int
    unread_project_activity_count: int


SkillCategory = Literal["language", "frontend", "backend", "database", "testing", "other"]


class SkillIn(BaseModel):
    category: SkillCategory
    name: str = Field(min_length=1, max_length=60)
    level: int = Field(ge=1, le=5)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return meaningful(value)


class SkillProfileIn(BaseModel):
    weekly_hours: int = Field(ge=0, le=80)
    learning_goal: str = Field(max_length=1000)
    skills: list[SkillIn] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_skills(self):
        keys = [(skill.category, skill.name.casefold()) for skill in self.skills]
        if len(keys) != len(set(keys)):
            raise ValueError("同一类别中不能重复填写技能")
        self.learning_goal = self.learning_goal.strip()
        return self


class SkillProfileOut(ORMModel):
    user_id: int
    weekly_hours: int
    learning_goal: str
    skills: list[SkillIn]
    updated_at: datetime | None


class MemberSkillProfileOut(BaseModel):
    user: UserOut
    role: Literal["owner", "member"]
    profile: SkillProfileOut


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return meaningful(value)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AdminCreateUserIn(RegisterIn):
    is_admin: bool = False


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = ""
    requirements: str = Field(default="", max_length=10000)
    tech_stack: str = Field(default="", max_length=255)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return meaningful(value)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class ProjectOut(ORMModel):
    id: int
    name: str
    goal: str
    requirements: str
    tech_stack: str
    github_repo_url: str | None
    start_date: date | None
    end_date: date | None
    owner_id: int
    created_at: datetime


class RepositoryIn(BaseModel):
    url: str | None = Field(default=None, max_length=300)


class OwnerTransferIn(BaseModel):
    new_owner_id: int


class ProjectActivityOut(ORMModel):
    id: int
    project_id: int
    project_name: str
    actor_name: str
    action: Literal["created", "deleted"]
    created_at: datetime
    is_read: bool


class MemberIn(BaseModel):
    email: EmailStr


class MemberOut(BaseModel):
    user: UserOut
    role: Literal["owner", "member"]


class InvitationOut(ORMModel):
    id: int
    project_id: int
    project_name: str
    invited_user_id: int
    invited_user_name: str
    invited_by_id: int
    inviter_name: str
    status: Literal["pending", "accepted", "declined", "cancelled"]
    created_at: datetime
    responded_at: datetime | None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: date | None = None
    acceptance_criteria: str = ""
    estimated_hours: int | None = Field(default=None, ge=1, le=80)
    required_skills: list[str] = Field(default_factory=list, max_length=10)
    assignee_id: int | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return meaningful(value)

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        return clean_skill_names(value)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    priority: Literal["low", "medium", "high"] | None = None
    due_date: date | None = None
    acceptance_criteria: str | None = None
    estimated_hours: int | None = Field(default=None, ge=1, le=80)
    required_skills: list[str] | None = Field(default=None, max_length=10)
    assignee_id: int | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return meaningful(value) if value is not None else None

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str] | None) -> list[str] | None:
        return clean_skill_names(value) if value is not None else None


class TaskOut(ORMModel):
    id: int
    project_id: int
    title: str
    description: str
    priority: str
    due_date: date | None
    acceptance_criteria: str
    estimated_hours: int | None
    required_skills: list[str]
    assignee_id: int | None
    assignee_name: str | None
    status: str
    evidence_note: str | None
    evidence_url: str | None
    code_url: str | None
    code_metadata: dict | None
    test_url: str | None
    test_note: str | None
    development_checklist: list[dict]
    created_at: datetime
    updated_at: datetime


class WeightFactors(ORMModel):
    complexity: int = Field(ge=1, le=5)
    estimated_hours: int = Field(ge=1, le=80)
    importance: int = Field(ge=1, le=5)
    risk: int = Field(ge=1, le=5)


class WeightSuggestionOut(WeightFactors):
    suggested_score: int
    rationale: str


class WeightConfirmIn(WeightFactors):
    confirmed_score: int = Field(ge=1, le=100)
    adjustment_reason: str = Field(default="", max_length=500)

    @field_validator("adjustment_reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        return value.strip()


class TaskWeightOut(WeightSuggestionOut):
    task_id: int
    confirmed_score: int
    adjustment_reason: str
    confirmed_by_id: int
    updated_at: datetime


class TaskDependenciesIn(BaseModel):
    depends_on_ids: list[int] = Field(max_length=30)


class TaskDependenciesOut(BaseModel):
    task_id: int
    depends_on_ids: list[int]


class PlannedTask(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=2000)
    acceptance_criteria: str = Field(max_length=1000)
    estimated_hours: int = Field(ge=1, le=80)
    required_skills: list[str] = Field(max_length=10)
    depends_on: list[int] = Field(max_length=20)
    rationale: str = Field(max_length=1000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return meaningful(value)

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        return clean_skill_names(value)


class PlanningSuggestion(BaseModel):
    summary: str
    tasks: list[PlannedTask]


class PlanningDraftOut(ORMModel):
    id: int
    project_id: int
    status: Literal["pending", "confirmed"]
    suggestion: PlanningSuggestion
    created_at: datetime


class PlanningConfirmTask(BaseModel):
    source_index: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    acceptance_criteria: str = Field(default="", max_length=1000)
    estimated_hours: int = Field(ge=1, le=80)
    required_skills: list[str] = Field(default_factory=list, max_length=10)
    depends_on: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return meaningful(value)

    @field_validator("required_skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        return clean_skill_names(value)


class PlanningConfirmIn(BaseModel):
    tasks: list[PlanningConfirmTask] = Field(min_length=1, max_length=20)


class AssignmentRecommendation(BaseModel):
    task_id: int
    assignee_id: int
    reason: str = Field(min_length=1, max_length=1000)
    risk_note: str = Field(default="", max_length=500)


class AssignmentSuggestion(BaseModel):
    summary: str = Field(max_length=1000)
    recommendations: list[AssignmentRecommendation]


class AssignmentDraftOut(ORMModel):
    id: int
    project_id: int
    status: Literal["pending", "confirmed"]
    suggestion: AssignmentSuggestion
    created_at: datetime


class AssignmentDecision(BaseModel):
    task_id: int
    assignee_id: int


class AssignmentConfirmIn(BaseModel):
    assignments: list[AssignmentDecision] = Field(min_length=1)


class ProgressFinding(BaseModel):
    code: str
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    task_ids: list[int]
    member_id: int | None = None


class ProgressWorkload(BaseModel):
    member_id: int
    member_name: str
    open_task_count: int
    estimated_hours: int


class ProgressSnapshot(BaseModel):
    as_of: date
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    status_counts: dict[str, int]
    workload: list[ProgressWorkload]
    findings: list[ProgressFinding]


class ProgressAction(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=600)
    related_task_ids: list[int] = Field(default_factory=list)


class ProgressDiagnosis(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    actions: list[ProgressAction] = Field(max_length=8)


class ProgressReportOut(ORMModel):
    id: int
    project_id: int
    snapshot: ProgressSnapshot
    diagnosis: ProgressDiagnosis
    created_at: datetime


class AnalyticsMember(BaseModel):
    member_id: int | None
    member_name: str
    status_counts: dict[str, int]
    estimated_hours: int


class AnalyticsWeight(BaseModel):
    task_id: int
    task_title: str
    confirmed_score: int


class AnalyticsScheduleItem(BaseModel):
    task_id: int
    task_title: str
    due_date: date
    status: str
    assignee_name: str | None


class AnalyticsTrendPoint(BaseModel):
    date: date
    total_tasks: int
    completed_tasks: int
    completion_rate: float


class ProjectAnalytics(BaseModel):
    as_of: date
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    status_counts: dict[str, int]
    members: list[AnalyticsMember]
    weights: list[AnalyticsWeight]
    schedule: list[AnalyticsScheduleItem]
    trend: list[AnalyticsTrendPoint]


class EvidenceIn(BaseModel):
    note: str | None = None
    url: HttpUrl | None = None
    code_url: HttpUrl | None = None
    test_url: HttpUrl | None = None
    test_note: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def has_content(self):
        if not any((self.note and self.note.strip(), self.url, self.code_url, self.test_url, self.test_note and self.test_note.strip())):
            raise ValueError("请填写成果说明、代码或测试证据")
        return self


class ChecklistItem(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(default="", max_length=500)
    kind: Literal["implementation", "test"]
    checked: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return meaningful(value)


class ChecklistUpdateIn(BaseModel):
    items: list[ChecklistItem] = Field(min_length=1, max_length=12)


class TaskReviewSnapshotOut(BaseModel):
    id: int
    task_id: int
    snapshot: dict
    is_current: bool
    created_at: datetime


class ReviewFinding(BaseModel):
    criterion: str = Field(min_length=1, max_length=300)
    assessment: Literal["supported", "uncertain", "manual_check"]
    explanation: str = Field(min_length=1, max_length=1000)
    evidence_paths: list[str] = Field(default_factory=list, max_length=5)


class ReviewAdvice(BaseModel):
    security_warning: bool = False
    security_message: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=1500)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=8)
    manual_tests: list[str] = Field(default_factory=list, max_length=6)


class ReviewConsentIn(BaseModel):
    acknowledged_risk: bool
    confirmed_send: bool
    confirmation_text: str


class TaskReviewAdviceOut(BaseModel):
    id: int
    snapshot_id: int
    advice: ReviewAdvice
    created_at: datetime


class DecisionIn(BaseModel):
    note: str = ""


class TaskEventOut(ORMModel):
    id: int
    task_id: int
    actor_id: int
    actor_name: str
    action: str
    note: str
    created_at: datetime
