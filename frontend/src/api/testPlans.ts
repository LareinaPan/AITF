import request from './request'

export interface TestPlan {
  id: string
  project_id: string
  name: string
  cron_expression: string | null
  environment_id: string
  environment_name: string
  is_enabled: boolean
  notify_on_complete: boolean
  created_at: string
  case_count: number
}

export interface PlanCaseItem {
  case_id: string
  case_name: string
  sort_order: number
  status: string
}

export interface TestPlanDetail extends TestPlan {
  cases: PlanCaseItem[]
}

export interface TestPlanCreatePayload {
  name: string
  environment_id: string
  cron_expression?: string | null
  is_enabled?: boolean
  notify_on_complete?: boolean
}

export interface TestPlanUpdatePayload {
  name?: string
  environment_id?: string
  cron_expression?: string | null
  is_enabled?: boolean
  notify_on_complete?: boolean
}

export const PLAN_CASE_MAX_COUNT = 500

export interface PlanRun {
  id: string
  plan_id: string
  status: string
  total_count: number
  pass_count: number
  fail_count: number
  allure_report_url: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export async function fetchTestPlans(projectId: string): Promise<TestPlan[]> {
  const { data } = await request.get<TestPlan[]>(`/projects/${projectId}/plans`)
  return data
}

export async function fetchTestPlan(projectId: string, planId: string): Promise<TestPlanDetail> {
  const { data } = await request.get<TestPlanDetail>(`/projects/${projectId}/plans/${planId}`)
  return data
}

export async function createTestPlan(
  projectId: string,
  payload: TestPlanCreatePayload,
): Promise<TestPlan> {
  const { data } = await request.post<TestPlan>(`/projects/${projectId}/plans`, payload)
  return data
}

export async function updateTestPlan(
  projectId: string,
  planId: string,
  payload: TestPlanUpdatePayload,
): Promise<TestPlan> {
  const { data } = await request.put<TestPlan>(`/projects/${projectId}/plans/${planId}`, payload)
  return data
}

export async function deleteTestPlan(projectId: string, planId: string): Promise<void> {
  await request.delete(`/projects/${projectId}/plans/${planId}`)
}

export async function bindPlanCases(
  projectId: string,
  planId: string,
  caseIds: string[],
): Promise<TestPlanDetail> {
  const { data } = await request.post<TestPlanDetail>(
    `/projects/${projectId}/plans/${planId}/cases`,
    { case_ids: caseIds },
  )
  return data
}

export async function unbindPlanCase(
  projectId: string,
  planId: string,
  caseId: string,
): Promise<TestPlanDetail> {
  const { data } = await request.delete<TestPlanDetail>(
    `/projects/${projectId}/plans/${planId}/cases/${caseId}`,
  )
  return data
}

export async function runTestPlan(projectId: string, planId: string): Promise<PlanRun> {
  const { data } = await request.post<PlanRun>(`/projects/${projectId}/plans/${planId}/run`)
  return data
}

export async function fetchPlanRuns(projectId: string, planId: string): Promise<PlanRun[]> {
  const { data } = await request.get<PlanRun[]>(
    `/projects/${projectId}/plans/${planId}/runs`,
  )
  return data
}
