import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '@/components/layout/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import HomeView from '@/views/HomeView.vue'
import LoginView from '@/views/LoginView.vue'
import ProjectDetailView from '@/views/projects/ProjectDetailView.vue'
import ProjectListView from '@/views/projects/ProjectListView.vue'
import ProjectOverviewTab from '@/views/projects/tabs/ProjectOverviewTab.vue'
import ProjectAiReviewTab from '@/views/projects/tabs/ProjectAiReviewTab.vue'
import ProjectApisTab from '@/views/projects/tabs/ProjectApisTab.vue'
import ProjectCasesTab from '@/views/projects/tabs/ProjectCasesTab.vue'
import TestCaseEditorView from '@/views/projects/TestCaseEditorView.vue'
import ProjectPlansTab from '@/views/projects/tabs/ProjectPlansTab.vue'
import ProjectPlanDetailView from '@/views/projects/ProjectPlanDetailView.vue'
import ProjectSettingsTab from '@/views/projects/tabs/ProjectSettingsTab.vue'
import RegisterView from '@/views/RegisterView.vue'
import EnvironmentView from '@/views/environments/EnvironmentView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { guestOnly: true },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { guestOnly: true },
    },
    {
      path: '/',
      component: AppShell,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: HomeView,
        },
        {
          path: 'projects',
          name: 'projects',
          component: ProjectListView,
        },
        {
          path: 'environments',
          name: 'environments',
          component: EnvironmentView,
        },
        {
          path: 'projects/:id',
          component: ProjectDetailView,
          children: [
            {
              path: '',
              name: 'project-overview',
              component: ProjectOverviewTab,
            },
            {
              path: 'apis',
              name: 'project-apis',
              component: ProjectApisTab,
            },
            {
              path: 'cases',
              name: 'project-cases',
              component: ProjectCasesTab,
            },
            {
              path: 'cases/new',
              name: 'project-case-create',
              component: TestCaseEditorView,
            },
            {
              path: 'cases/:caseId',
              name: 'project-case-edit',
              component: TestCaseEditorView,
            },
            {
              path: 'ai-review',
              name: 'project-ai-review',
              component: ProjectAiReviewTab,
            },
            {
              path: 'plans',
              name: 'project-plans',
              component: ProjectPlansTab,
            },
            {
              path: 'plans/:planId',
              name: 'project-plan-detail',
              component: ProjectPlanDetailView,
            },
            {
              path: 'settings',
              name: 'project-settings',
              component: ProjectSettingsTab,
            },
          ],
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()

  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth)

  if (requiresAuth && !authStore.isAuthenticated) {
    return {
      name: 'login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.meta.guestOnly && authStore.isAuthenticated) {
    return { name: 'home' }
  }

  return true
})

export default router
