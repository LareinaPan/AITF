import request from './request'

export type TestCasePriority = 'P0' | 'P1' | 'P2' | 'P3'
export type TestCaseStatus = 'draft' | 'active'
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'
export type BodyType = 'none' | 'json' | 'raw' | 'form'

export interface KeyValueItem {
  key: string
  value: string
}

export interface TestCaseRequestJson {
  method: string
  url: string
  headers: KeyValueItem[]
  query: KeyValueItem[]
  body: { type: BodyType; content: string }
}

export interface TestCaseAssertionsJson {
  status_code: number
  max_response_time_ms: number
  body_rules: BodyRule[]
}

export type BodyRuleType = 'contains' | 'json_path'

export interface ContainsBodyRule {
  type: 'contains'
  value: string
}

export interface JsonPathBodyRule {
  type: 'json_path'
  path: string
  operator: 'eq'
  expected: string
}

export type BodyRule = ContainsBodyRule | JsonPathBodyRule

export interface BodyRuleRow {
  _rowId: string
  type: BodyRuleType
  value: string
  path: string
  expected: string
}

export interface TestCase {
  id: string
  project_id: string
  name: string
  description: string | null
  request_json: TestCaseRequestJson
  assertions_json: TestCaseAssertionsJson
  priority: TestCasePriority
  status: TestCaseStatus
  api_endpoint_id: string | null
  created_at: string
}

export interface TestCaseCreatePayload {
  name: string
  description?: string | null
  priority?: TestCasePriority
  status?: TestCaseStatus
  request_json?: TestCaseRequestJson
  assertions_json?: TestCaseAssertionsJson
  api_endpoint_id?: string | null
}

export interface TestCaseUpdatePayload {
  name?: string
  description?: string | null
  priority?: TestCasePriority
  status?: TestCaseStatus
  request_json?: TestCaseRequestJson
  assertions_json?: TestCaseAssertionsJson
  api_endpoint_id?: string | null
}

export interface FetchTestCasesOptions {
  apiEndpointId?: string
}

export async function fetchTestCases(
  projectId: string,
  options: FetchTestCasesOptions = {},
): Promise<TestCase[]> {
  const { data } = await request.get<TestCase[]>(`/projects/${projectId}/cases`, {
    params: options.apiEndpointId ? { api_endpoint_id: options.apiEndpointId } : undefined,
  })
  return data
}

export async function fetchTestCase(projectId: string, caseId: string): Promise<TestCase> {
  const { data } = await request.get<TestCase>(`/projects/${projectId}/cases/${caseId}`)
  return data
}

export async function createTestCase(
  projectId: string,
  payload: TestCaseCreatePayload,
): Promise<TestCase> {
  const { data } = await request.post<TestCase>(`/projects/${projectId}/cases`, payload)
  return data
}

export async function updateTestCase(
  projectId: string,
  caseId: string,
  payload: TestCaseUpdatePayload,
): Promise<TestCase> {
  const { data } = await request.put<TestCase>(`/projects/${projectId}/cases/${caseId}`, payload)
  return data
}

export async function deleteTestCase(projectId: string, caseId: string): Promise<void> {
  await request.delete(`/projects/${projectId}/cases/${caseId}`)
}

export async function confirmTestCase(projectId: string, caseId: string): Promise<TestCase> {
  const { data } = await request.post<TestCase>(`/projects/${projectId}/cases/${caseId}/confirm`)
  return data
}

export interface PreparedRequestSnapshot {
  method: string
  url: string
  headers: Record<string, string>
  params: Record<string, string>
  body_type: string
  body_content: string
}

export interface HttpResponseSnapshot {
  status_code: number
  body: string
  elapsed_ms: number
}

export interface AssertionCheckResult {
  name: string
  passed: boolean
  message: string
  rule_type: string | null
}

export interface AssertionsEvaluationResult {
  passed: boolean
  checks: AssertionCheckResult[]
}

export interface TestCaseRunResult {
  case_id: string
  case_name: string
  environment_id: string
  environment_name: string
  passed: boolean
  error: string | null
  prepared_request: PreparedRequestSnapshot
  response: HttpResponseSnapshot | null
  assertions: AssertionsEvaluationResult | null
}

export async function runTestCase(
  projectId: string,
  caseId: string,
  environmentId: string,
): Promise<TestCaseRunResult> {
  const { data } = await request.post<TestCaseRunResult>(
    `/projects/${projectId}/cases/${caseId}/run`,
    { environment_id: environmentId },
  )
  return data
}

export function formatResponseBody(body: string): string {
  if (!body) {
    return ''
  }
  try {
    return JSON.stringify(JSON.parse(body), null, 2)
  } catch {
    return body
  }
}

export function createDefaultAssertionsJson(): TestCaseAssertionsJson {
  return {
    status_code: 200,
    max_response_time_ms: 3000,
    body_rules: [],
  }
}

export function bodyRulesToRows(rules: BodyRule[]): BodyRuleRow[] {
  return rules.map((rule) => {
    if (rule.type === 'contains') {
      return {
        _rowId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: 'contains',
        value: rule.value,
        path: '',
        expected: '',
      }
    }
    return {
      _rowId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: 'json_path',
      value: '',
      path: rule.path,
      expected: rule.expected,
    }
  })
}

export function rowsToBodyRules(rows: BodyRuleRow[]): BodyRule[] {
  const rules: BodyRule[] = []

  for (const row of rows) {
    if (row.type === 'contains') {
      const value = row.value.trim()
      if (!value) {
        continue
      }
      rules.push({ type: 'contains', value })
      continue
    }

    const path = row.path.trim()
    const expected = row.expected.trim()
    if (!path || !expected) {
      continue
    }
    rules.push({
      type: 'json_path',
      path,
      operator: 'eq',
      expected,
    })
  }

  return rules
}

export function buildAssertionsPayloadFromForm(
  statusCode: number,
  maxResponseTimeMs: number,
  rows: BodyRuleRow[],
): TestCaseAssertionsJson {
  return {
    status_code: statusCode,
    max_response_time_ms: maxResponseTimeMs,
    body_rules: rowsToBodyRules(rows),
  }
}

export function createDefaultRequestJson(): TestCaseRequestJson {
  return {
    method: 'GET',
    url: '',
    headers: [],
    query: [],
    body: { type: 'none', content: '' },
  }
}

export function sanitizeKeyValueItems(items: KeyValueItem[]): KeyValueItem[] {
  return items
    .map((item) => ({ key: item.key.trim(), value: item.value }))
    .filter((item) => item.key.length > 0)
}

export function buildRequestPayload(request: TestCaseRequestJson): TestCaseRequestJson {
  return {
    method: request.method.toUpperCase(),
    url: request.url.trim(),
    headers: sanitizeKeyValueItems(request.headers),
    query: sanitizeKeyValueItems(request.query),
    body: {
      type: request.body.type,
      content: request.body.content,
    },
  }
}
