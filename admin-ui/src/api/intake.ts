import { get, post } from './request'
import type { AutonomyStatus } from './plugins'

export type IntakeStatus =
  | 'received'
  | 'analyzing'
  | 'assigned'
  | 'in_progress'
  | 'delivered'
  | 'settled'
  | 'cancelled'

export type IntakeRoutingCandidate = {
  member_id?: string
  name?: string
  work_type_id?: string | null
  department_id?: string | null
  score?: number
  capability_overlap?: string[]
  busy?: boolean
  independent_ready?: boolean
  feedback_bonus?: number
  journal_bonus?: number
  reasons?: string[]
}

export type IntakeItem = {
  intake_id: string
  title?: string | null
  description?: string | null
  expected_deliverables?: string[]
  needed_capabilities?: string[]
  source?: string
  status?: IntakeStatus | string
  budget?: number | null
  quoted_amount?: number | null
  settled_amount?: number | null
  currency?: string
  client_label?: string | null
  deadline_at?: string | null
  member_id?: string | null
  task_id?: string | null
  project_id?: string | null
  work_type_id?: string | null
  routing?: {
    policy_id?: string
    resolve_by?: string
    expanded_capabilities?: string[]
    candidates?: IntakeRoutingCandidate[]
    recommended_member_id?: string | null
    assigned_member_id?: string | null
    is_override?: boolean
    override_reason?: string | null
    assigned_by?: string | null
    assigned_at?: string | null
    analyzed_at?: string
  }
  fulfillment?: {
    worker_id?: string | null
    work_type_id?: string | null
    has_operation_automation?: boolean
    suggested_operation_types?: string[]
    primary_operation_type?: string | null
    job_ids?: string[]
    status?: string
    artifacts?: Array<{
      kind?: string
      path?: string
      label?: string
      job_id?: string | null
      exists?: boolean | null
      operation_type?: string | null
      attached_at?: string | null
      meta?: Record<string, unknown>
    }>
    last_artifact_at?: string | null
    last_operation_type?: string | null
    last_job_id?: string | null
  }
  finance?: Record<string, unknown>
  created_at?: string
  updated_at?: string
  assigned_at?: string | null
  delivered_at?: string | null
  settled_at?: string | null
}

export type IntakeFunnel = {
  counts?: Record<string, number>
  open_count?: number
  pipeline_value?: number
  settled_value?: number
  currency?: string
  item_count?: number
}

export function listIntakes(params: {
  tenant_id?: string
  status?: string
  member_id?: string
} = {}) {
  const query = new URLSearchParams()
  if (params.tenant_id) query.set('tenant_id', params.tenant_id)
  if (params.status) query.set('status', params.status)
  if (params.member_id) query.set('member_id', params.member_id)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<{
    items?: IntakeItem[]
    funnel?: IntakeFunnel
    intake_center?: Record<string, unknown>
  }>(`/api/autonomy/intake${suffix}`)
}

export function getIntakePolicies() {
  return get<{
    default_policy_id?: string
    policies?: Array<{ policy_id?: string; title?: string; rule_count?: number }>
    capabilities?: Array<{ capability?: string; work_type_ids?: string[] }>
  }>('/api/autonomy/intake/policies')
}

export function createIntake(payload: {
  tenant_id?: string
  title: string
  description?: string
  expected_deliverables?: string[]
  needed_capabilities?: string[]
  source?: string
  budget?: number | null
  quoted_amount?: number | null
  currency?: string
  client_label?: string
  auto_analyze?: boolean
}) {
  return post<{ intake?: IntakeItem; autonomy?: AutonomyStatus }>('/api/autonomy/intake', payload)
}

export function analyzeIntake(intakeId: string, payload: { tenant_id?: string } = {}) {
  return post<{ intake?: IntakeItem; autonomy?: AutonomyStatus }>(
    `/api/autonomy/intake/${encodeURIComponent(intakeId)}/analyze`,
    payload,
  )
}

export function assignIntake(
  intakeId: string,
  payload: {
    tenant_id?: string
    member_id?: string
    assigned_by?: string
    override_reason?: string
  },
) {
  return post<{
    intake?: IntakeItem
    task?: Record<string, unknown>
    fulfillment?: Record<string, unknown>
    autonomy?: AutonomyStatus
  }>(`/api/autonomy/intake/${encodeURIComponent(intakeId)}/assign`, payload)
}

export function settleIntake(
  intakeId: string,
  payload: {
    tenant_id?: string
    settled_amount?: number | null
    cost?: number | null
    note?: string
  },
) {
  return post<{
    intake?: IntakeItem
    finance?: Record<string, unknown>
    autonomy?: AutonomyStatus
  }>(`/api/autonomy/intake/${encodeURIComponent(intakeId)}/settle`, payload)
}

export function cancelIntake(intakeId: string, payload: { tenant_id?: string; reason?: string } = {}) {
  return post<{ intake?: IntakeItem; autonomy?: AutonomyStatus }>(
    `/api/autonomy/intake/${encodeURIComponent(intakeId)}/cancel`,
    payload,
  )
}
