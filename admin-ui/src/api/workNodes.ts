import { get, post } from './request'
import type { WorkNode, WorkNodeExperienceCard } from '../utils/workNodes'

export type WorkNodeSkill = {
  skill_id: string
  domain: string
  capability_type?: string
  task_type?: string
  title: string
  summary?: string
  input_summary?: string
  quality_score?: number
  member_id?: string
  task_id?: string
  created_at?: string
}

export type WorkNodeArchiveMeta = {
  status?: string
  reason?: string | null
  gitee_path?: string
  local_root?: string
  target_repo?: string
  target_url?: string
  branch?: string
  files?: string[]
  verified_files?: string[]
  remote_uploaded_files?: string[]
  integrity_verified?: boolean
  synced_at?: string
  archived_at?: string
  next_action?: string
}

export type WorkNodeApiItem = WorkNode & {
  archive?: WorkNodeArchiveMeta | null
  experience_cards?: WorkNodeExperienceCard[]
}

export function getWorkNodes(params: {
  tenant_id?: string
  work_type_id?: string
  member_id?: string
  node_id?: string
} = {}) {
  const query = new URLSearchParams()
  if (params.tenant_id) query.set('tenant_id', params.tenant_id)
  if (params.work_type_id) query.set('work_type_id', params.work_type_id)
  if (params.member_id) query.set('member_id', params.member_id)
  if (params.node_id) query.set('node_id', params.node_id)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<{ items: WorkNodeApiItem[]; total: number }>(`/api/autonomy/work-nodes${suffix}`)
}

export function getWorkNodeSkills(params: {
  tenant_id?: string
  work_type_id?: string
  member_id?: string
  limit?: number
} = {}) {
  const query = new URLSearchParams()
  if (params.tenant_id) query.set('tenant_id', params.tenant_id)
  if (params.work_type_id) query.set('work_type_id', params.work_type_id)
  if (params.member_id) query.set('member_id', params.member_id)
  if (params.limit) query.set('limit', String(params.limit))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<{ items: WorkNodeSkill[]; total: number }>(`/api/autonomy/work-nodes/skills${suffix}`)
}

export function archiveWorkNode(taskId: string, payload: { tenant_id?: string } = {}) {
  return post<{ archive: WorkNodeArchiveMeta; autonomy?: Record<string, unknown> }>(
    `/api/autonomy/work-nodes/${encodeURIComponent(taskId)}/archive`,
    payload,
  )
}

export function retryWorkNodeArchive(taskId: string, payload: { tenant_id?: string } = {}) {
  return post<{ archive: WorkNodeArchiveMeta; autonomy?: Record<string, unknown> }>(
    `/api/autonomy/work-nodes/${encodeURIComponent(taskId)}/archive/retry`,
    payload,
  )
}
