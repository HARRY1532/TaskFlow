import { api, json } from './client'
import type { MemberSkillProfile, SkillProfile } from '../types'

export const skillsApi = {
  mine: () => api<SkillProfile>('/profile/skills'),
  save: (data: Pick<SkillProfile, 'weekly_hours' | 'learning_goal' | 'skills'>) =>
    api<SkillProfile>('/profile/skills', json('PUT', data)),
  project: (projectId: number) => api<MemberSkillProfile[]>(`/projects/${projectId}/skills`),
}
