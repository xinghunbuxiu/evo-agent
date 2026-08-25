import type { AutonomyFormalTask, CollaborationRequest } from '../api/plugins'

export type IntegrationPending = {
  collaboration_request_id?: string
  phase?: string
  updated_at?: string | null
  provider_member_id?: string | null
  provider_task_id?: string | null
}

export const formatCollaborationStatus = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'open') return '待指派'
  if (normalized === 'assigned') return '已指派'
  if (normalized === 'provider_submitted') return '提供方已提交'
  if (normalized === 'approved') return '已通过审核'
  if (normalized === 'integrated') return '已对接'
  if (normalized === 'closed') return '已关闭'
  if (normalized === 'cancelled') return '已取消'
  return normalized
}

export const formatIntegrationPhase = (value?: string | null, fallback = '--') => {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback
  if (normalized === 'waiting_assignment') return '等待育成师指派'
  if (normalized === 'waiting_delivery') return '等待提供方交付'
  if (normalized === 'ready_to_integrate') return '可对接'
  if (normalized === 'integrated') return '已对接'
  return normalized
}

export const formatCapabilityLabel = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'auth_api') return '认证 API'
  if (normalized === 'rest_api') return 'REST API'
  if (normalized === 'api_contract') return 'API 契约'
  if (normalized === 'asset_delivery') return '资产交付'
  if (normalized === 'design_asset') return '设计资产'
  return normalized
}

export const isCollaborationPipelineStatus = (status?: string | null) => {
  const normalized = String(status || '').trim()
  return normalized && !['closed', 'integrated', 'cancelled'].includes(normalized)
}

export const readTaskIntegrationPending = (task?: AutonomyFormalTask | null): IntegrationPending | null => {
  const pending = task?.integration_pending
  if (!pending || typeof pending !== 'object') return null
  const phase = String(pending.phase || '').trim()
  if (!phase || phase === 'integrated') return null
  return pending as IntegrationPending
}

export const integrationBannerTone = (phase?: string | null) => {
  const normalized = String(phase || '').trim()
  if (normalized === 'ready_to_integrate') {
    return {
      container: 'border-sky-300 bg-sky-50',
      badge: 'bg-sky-600 text-white',
      label: '待对接',
    }
  }
  return {
    container: 'border-amber-300 bg-amber-50',
    badge: 'bg-amber-600 text-white',
    label: '协作进行中',
  }
}

export const buildCapabilityOptions = (templates: Array<{ capability_types?: string[]; title?: string }>) => {
  const seen = new Set<string>()
  const options: Array<{ value: string; label: string }> = []
  for (const template of templates) {
    for (const capability of template.capability_types || []) {
      const value = String(capability || '').trim()
      if (!value || seen.has(value)) continue
      seen.add(value)
      options.push({ value, label: formatCapabilityLabel(value) })
    }
  }
  if (!options.length) {
    options.push(
      { value: 'api_contract', label: formatCapabilityLabel('api_contract') },
      { value: 'rest_api', label: formatCapabilityLabel('rest_api') },
    )
  }
  return options
}

export const summarizeCollaborationRequest = (request: CollaborationRequest) => {
  const assignment = request.assignment && typeof request.assignment === 'object'
    ? request.assignment as Record<string, unknown>
    : null
  return {
    providerMemberId: String(assignment?.provider_member_id || '').trim(),
    providerTaskId: String(assignment?.provider_task_id || '').trim(),
  }
}
