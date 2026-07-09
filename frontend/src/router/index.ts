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
import FcProjectDetailView from '@/views/fc-projects/FcProjectDetailView.vue'
import FcProjectListView from '@/views/fc-projects/FcProjectListView.vue'
import FcCasesTab from '@/views/fc-projects/tabs/FcCasesTab.vue'
import FcExperienceCasesTab from '@/views/fc-projects/tabs/FcExperienceCasesTab.vue'
import FcGenerateTab from '@/views/fc-projects/tabs/FcGenerateTab.vue'
import FcHistoryTab from '@/views/fc-projects/tabs/FcHistoryTab.vue'
import FcOverviewTab from '@/views/fc-projects/tabs/FcOverviewTab.vue'
import FcRequirementDocsTab from '@/views/fc-projects/tabs/FcRequirementDocsTab.vue'
import FcReviewTab from '@/views/fc-projects/tabs/FcReviewTab.vue'
import PtProjectDetailView from '@/views/pt-projects/PtProjectDetailView.vue'
import PtProjectListView from '@/views/pt-projects/PtProjectListView.vue'
import PtOverviewTab from '@/views/pt-projects/tabs/PtOverviewTab.vue'
import PtRunsTab from '@/views/pt-projects/tabs/PtRunsTab.vue'
import PtScenariosTab from '@/views/pt-projects/tabs/PtScenariosTab.vue'
import PtScenarioScriptView from '@/views/pt-projects/PtScenarioScriptView.vue'
import PtRunDetailView from '@/views/pt-projects/PtRunDetailView.vue'

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
          path: 'fc-projects',
          name: 'fc-projects',
          component: FcProjectListView,
        },
        {
          path: 'fc-projects/:id',
          component: FcProjectDetailView,
          children: [
            {
              path: '',
              name: 'fc-project-overview',
              component: FcOverviewTab,
            },
            {
              path: 'docs',
              name: 'fc-project-docs',
              component: FcRequirementDocsTab,
            },
            {
              path: 'experience',
              name: 'fc-project-experience',
              component: FcExperienceCasesTab,
            },
            {
              path: 'generate',
              name: 'fc-project-generate',
              component: FcGenerateTab,
            },
            {
              path: 'review',
              name: 'fc-project-review',
              component: FcReviewTab,
            },
            {
              path: 'cases',
              name: 'fc-project-cases',
              component: FcCasesTab,
            },
            {
              path: 'history',
              name: 'fc-project-history',
              component: FcHistoryTab,
            },
          ],
        },
        {
          path: 'pt-projects',
          name: 'pt-projects',
          component: PtProjectListView,
        },
        {
          path: 'pt-projects/:id/runs/:runId',
          name: 'pt-project-run-detail',
          component: PtRunDetailView,
        },
        {
          path: 'pt-projects/:id/scenarios/:scenarioId/script',
          name: 'pt-scenario-script',
          component: PtScenarioScriptView,
        },
        {
          path: 'pt-projects/:id',
          component: PtProjectDetailView,
          children: [
            {
              path: '',
              name: 'pt-project-overview',
              component: PtOverviewTab,
            },
            {
              path: 'scenarios',
              name: 'pt-project-scenarios',
              component: PtScenariosTab,
            },
            {
              path: 'runs',
              name: 'pt-project-runs',
              component: PtRunsTab,
            },
          ],
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
