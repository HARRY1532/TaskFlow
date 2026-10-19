export interface User {
  id: number; name: string; email: string; is_admin: boolean
  is_active: boolean; avatar_url: string | null
}
export interface AdminUser extends User {
  project_activity_count: number
  unread_project_activity_count: number
}
export interface Invitation {
  id: number; project_id: number; project_name: string
  invited_user_id: number; invited_user_name: string
  invited_by_id: number; inviter_name: string
  status: 'pending' | 'accepted' | 'declined' | 'cancelled'
  created_at: string; responded_at: string | null
}
export interface ProjectActivity {
  id: number; project_id: number; project_name: string
  actor_name: string; action: 'created' | 'deleted'
  created_at: string; is_read: boolean
}
export interface Project {
  id: number; name: string; goal: string; requirements: string; tech_stack: string
  github_repo_url: string | null
  start_date: string | null; end_date: string | null; owner_id: number; created_at: string
}
export interface Member { user: User; role: 'owner' | 'member' }
export type SkillCategory = 'language' | 'frontend' | 'backend' | 'database' | 'testing' | 'other'
export interface Skill { category: SkillCategory; name: string; level: number }
export interface SkillProfile {
  user_id: number; weekly_hours: number; learning_goal: string
  skills: Skill[]; updated_at: string | null
}
export interface MemberSkillProfile { user: User; role: Member['role']; profile: SkillProfile }
export type TaskStatus = 'todo' | 'in_progress' | 'review' | 'done'
export interface Task {
  id: number; project_id: number; title: string; description: string
  priority: 'low' | 'medium' | 'high'; due_date: string | null
  acceptance_criteria: string; estimated_hours: number | null; required_skills: string[]
  assignee_id: number | null; status: TaskStatus
  assignee_name: string | null
  evidence_note: string | null; evidence_url: string | null
  code_url: string | null; test_url: string | null; test_note: string | null
  code_metadata: CodeMetadata | null
  development_checklist: ChecklistItem[]
  created_at: string; updated_at: string
}
export interface Requirement {
  id: number; project_id: number; title: string; description: string
  acceptance_criteria: string; priority: 'low' | 'medium' | 'high'
  status: 'active' | 'archived'; task_ids: number[]
  created_at: string; updated_at: string
}
export type RequirementInput = Pick<Requirement, 'title' | 'description' | 'acceptance_criteria' | 'priority' | 'status'>
export interface RequirementMatchSuggestion {
  summary: string
  recommendations: { task_id: number; reason: string }[]
  context_signature: string
}
export interface CodeMetadata {
  kind: 'pull' | 'commit'; title: string; author: string
  state: string; sha: string; number: number | null; checked_at: string
}
export interface PullRequestFile {
  path: string; status: string; additions: number; deletions: number; patch: string | null
}
export interface TaskReviewSnapshot {
  id: number; task_id: number; is_current: boolean; created_at: string
  snapshot: {
    task_signature: string
    pr: {
      repository: string; number: number; url: string; title: string; head_sha: string
      author: string; state: string; fetched_at: string; files: PullRequestFile[]
    }
  }
}
export interface ReviewFinding {
  criterion: string; assessment: 'supported' | 'uncertain' | 'manual_check'
  explanation: string; evidence_paths: string[]
}
export interface TaskReviewAdvice {
  id: number; snapshot_id: number; created_at: string
  advice: {
    security_warning: boolean; security_message: string; summary: string
    findings: ReviewFinding[]; manual_tests: string[]
  }
}
export interface ChecklistItem {
  title: string; detail: string; kind: 'implementation' | 'test'; checked: boolean
}
export interface TaskEvent {
  id: number; task_id: number; actor_id: number; actor_name: string
  action: string; note: string; created_at: string
}
export interface WeightFactors {
  complexity: number; estimated_hours: number; importance: number; risk: number
}
export interface WeightSuggestion extends WeightFactors { suggested_score: number; rationale: string }
export interface TaskWeight extends WeightSuggestion {
  task_id: number; confirmed_score: number; adjustment_reason: string
  confirmed_by_id: number; updated_at: string
}
export interface TaskDependencies { task_id: number; depends_on_ids: number[] }
export interface PlannedTask {
  title: string; description: string; acceptance_criteria: string
  estimated_hours: number; required_skills: string[]; depends_on: number[]; rationale: string
}
export interface PlanningDraft {
  id: number; project_id: number; status: 'pending' | 'confirmed'
  suggestion: { summary: string; tasks: PlannedTask[] }; created_at: string
}
export interface PlanningConfirmTask {
  source_index: number; title: string; description: string
  acceptance_criteria: string; estimated_hours: number; required_skills: string[]; depends_on: number[]
}
export interface AssignmentRecommendation {
  task_id: number; assignee_id: number; reason: string; risk_note: string
}
export interface AssignmentDraft {
  id: number; project_id: number; status: 'pending' | 'confirmed'
  suggestion: { summary: string; recommendations: AssignmentRecommendation[] }
  created_at: string
}
export interface AssignmentDecision { task_id: number; assignee_id: number }
export interface ProgressFinding {
  code: string; severity: 'high' | 'medium' | 'low'; title: string; detail: string
  task_ids: number[]; member_id: number | null
}
export interface ProgressWorkload {
  member_id: number; member_name: string; open_task_count: number; estimated_hours: number
}
export interface ProgressSnapshot {
  as_of: string; total_tasks: number; completed_tasks: number; completion_rate: number
  status_counts: Record<string, number>; workload: ProgressWorkload[]; findings: ProgressFinding[]
}
export interface ProgressReport {
  id: number; project_id: number; snapshot: ProgressSnapshot
  diagnosis: { summary: string; actions: { title: string; detail: string; related_task_ids: number[] }[] }
  created_at: string
}
export interface AnalyticsMember {
  member_id: number | null; member_name: string
  status_counts: Record<string, number>; estimated_hours: number
}
export interface AnalyticsTrendPoint {
  date: string; total_tasks: number; completed_tasks: number; completion_rate: number
}
export interface ProjectAnalytics {
  as_of: string; total_tasks: number; completed_tasks: number; completion_rate: number
  status_counts: Record<string, number>; members: AnalyticsMember[]
  weights: { task_id: number; task_title: string; confirmed_score: number }[]
  schedule: { task_id: number; task_title: string; due_date: string; status: string; assignee_name: string | null }[]
  trend: AnalyticsTrendPoint[]
}
