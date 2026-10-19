import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import DashboardView from '../views/DashboardView.vue'
import ProjectView from '../views/ProjectView.vue'
import PlanningView from '../views/PlanningView.vue'
import AssignmentView from '../views/AssignmentView.vue'
import ProgressView from '../views/ProgressView.vue'
import InvitationsView from '../views/InvitationsView.vue'
import ProfileView from '../views/ProfileView.vue'
import AdminUsersView from '../views/AdminUsersView.vue'
import AdminUserDetailView from '../views/AdminUserDetailView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/projects' },
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/register', component: RegisterView, meta: { public: true } },
    { path: '/projects', component: DashboardView },
    { path: '/projects/:id', component: ProjectView },
    { path: '/projects/:id/requirements', component: () => import('../views/RequirementsView.vue') },
    { path: '/projects/:id/planning', component: PlanningView },
    { path: '/projects/:id/assignments', component: AssignmentView },
    { path: '/projects/:id/progress', component: ProgressView },
    { path: '/projects/:id/analytics', component: () => import('../views/AnalyticsView.vue') },
    { path: '/invitations', component: InvitationsView },
    { path: '/profile', component: ProfileView },
    { path: '/admin/users', component: AdminUsersView, meta: { admin: true } },
    { path: '/admin/users/:id', component: AdminUserDetailView, meta: { admin: true } },
    { path: '/admin/activities', redirect: '/admin/users', meta: { admin: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (auth.token && !auth.user) await auth.load()
  if (!to.meta.public && !auth.token) return '/login'
  if (to.meta.admin && !auth.user?.is_admin) return '/projects'
  if (to.meta.public && auth.token) return '/projects'
})

export default router
