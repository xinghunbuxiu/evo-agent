import type { AutonomyFormalTask, ChildMemberRuntimeProfile } from '../api/plugins'
import type { WorkTypeItem } from '../api/workTypes'
import { formatIntegrationPhase } from './collaborationView'
import { resolveMemberWorkTypeId } from './formalTaskRecommendation'
import { formatTaskStatusLabel } from './workTypeDashboard'

export type WorkNodePhaseKey =
  | 'thinking'
  | 'assigned'
  | 'execution'
  | 'submitted'
  | 'approved'
  | 'experience'
  | 'archive'

export type WorkNodePhaseStatus = 'done' | 'current' | 'pending' | 'skipped'

export type WorkNodePhase = {
  key: WorkNodePhaseKey
  label: string
  status: WorkNodePhaseStatus
  summary?: string
  detail?: string
  at?: string | null
}

export type WorkNodeExperienceCard = {
  card_id?: string | null
  title?: string | null
  summary?: string | null
  stage?: string | null
  current_pattern?: string | null
  professional_risk?: string | null
  next_experiment?: string | null
  created_at?: string | null
}

export type WorkNodeStatus = 'thinking' | 'running' | 'submitted' | 'approved' | 'archived'

export type WorkNodeArchiveMeta = {
  status?: string
  reason?: string | null
  gitee_path?: string
  local_root?: string
  target_repo?: string
  target_url?: string
  files?: string[]
  archived_at?: string
  next_action?: string
}

export type WorkNode = {
  node_id: string
  task_id: string
  work_type_id: string
  work_type_title: string
  member_id: string
  member_name: string
  assigned_by_member_id?: string
  assigned_by_name?: string
  objective?: string
  deliverables?: string[]
  department_id?: string
  department_label?: string
  title: string
  status: WorkNodeStatus
  status_label: string
  updated_at?: string | null
  phases: WorkNodePhase[]
  experience_cards: WorkNodeExperienceCard[]
  archive?: WorkNodeArchiveMeta | null
  archive_hint?: string
  member_link: string
  trainer_link: string
}

const phaseLabels: Record<WorkNodePhaseKey, string> = {
  thinking: '思考决策',
  assigned: '任务分配',
  execution: '执行协作',
  submitted: '提交复盘',
  approved: '育成确认',
  experience: '经验沉淀',
  archive: 'Gitee 归档',
}

const normalize = (value?: string | null) => String(value || '').trim()

const mapTaskStatus = (status: string): WorkNodeStatus => {
  if (status === 'submitted') return 'submitted'
  if (status === 'approved') return 'approved'
  return 'running'
}

const phaseStatusFor = (
  phaseKey: WorkNodePhaseKey,
  taskStatus: string,
  hasThinking: boolean,
  hasExecution: boolean,
  hasExperience: boolean,
  archived: boolean,
): WorkNodePhaseStatus => {
  const order: WorkNodePhaseKey[] = ['thinking', 'assigned', 'execution', 'submitted', 'approved', 'experience', 'archive']
  const idx = order.indexOf(phaseKey)

  if (phaseKey === 'thinking') {
    if (!hasThinking) return 'skipped'
    if (taskStatus === 'assigned' && hasThinking) return 'done'
    return hasThinking ? 'done' : 'pending'
  }
  if (phaseKey === 'assigned') {
    return taskStatus ? 'done' : 'pending'
  }
  if (phaseKey === 'execution') {
    if (!hasExecution) return 'skipped'
    if (taskStatus === 'assigned') return 'current'
    return 'done'
  }
  if (phaseKey === 'submitted') {
    if (['submitted', 'approved'].includes(taskStatus)) return 'done'
    if (taskStatus === 'assigned') return 'pending'
    return 'pending'
  }
  if (phaseKey === 'approved') {
    if (taskStatus === 'approved') return 'done'
    if (taskStatus === 'submitted') return 'current'
    return 'pending'
  }
  if (phaseKey === 'experience') {
    if (!hasExperience) return taskStatus === 'approved' ? 'current' : 'pending'
    return 'done'
  }
  if (phaseKey === 'archive') {
    if (archived) return 'done'
    if (taskStatus === 'approved') return 'current'
    return 'pending'
  }

  return idx >= 0 ? 'pending' : 'skipped'
}

const buildPhases = (input: {
  task: AutonomyFormalTask
  member: ChildMemberRuntimeProfile | null
  experienceCards: WorkNodeExperienceCard[]
  archived: boolean
}): WorkNodePhase[] => {
  const { task, member, experienceCards, archived } = input
  const taskStatus = normalize(task.status)
  const memoryHub = member?.memory_hub
  const decisionState = memoryHub?.decision_state
  const decisionHistory = memoryHub?.decision_history || []
  const lastDecision = decisionHistory[decisionHistory.length - 1]
  const thinkingSummary = normalize(decisionState?.primary_plan || lastDecision?.decision_state?.primary_plan)
    || normalize(memoryHub?.decision_intent)
    || normalize(lastDecision?.decision_summary?.primary_plan)
    || normalize(lastDecision?.decision_summary?.summary)
  const thinkingDetail = [
    decisionState?.verification_goal ? `验证目标：${decisionState.verification_goal}` : '',
    decisionState?.fallback_plan ? `备选：${decisionState.fallback_plan}` : '',
  ].filter(Boolean).join('\n')

  const integration = task.integration_pending
  const hasExecution = Boolean(integration?.phase && integration.phase !== 'integrated')
  const executionSummary = integration?.phase
    ? formatIntegrationPhase(integration.phase)
    : undefined

  const hasThinking = Boolean(thinkingSummary || thinkingDetail)
  const hasExperience = experienceCards.length > 0

  const defs: Array<{ key: WorkNodePhaseKey; summary?: string; detail?: string; at?: string | null }> = [
    {
      key: 'thinking',
      summary: thinkingSummary || undefined,
      detail: thinkingDetail || undefined,
      at: lastDecision?.created_at || null,
    },
    {
      key: 'assigned',
      summary: normalize(task.objective) || undefined,
      detail: (task.deliverables || []).length ? `交付物：${(task.deliverables || []).join('、')}` : undefined,
      at: task.assigned_at || null,
    },
    {
      key: 'execution',
      summary: executionSummary,
      detail: integration?.collaboration_request_id
        ? `协作请求 ${integration.collaboration_request_id}`
        : undefined,
      at: integration?.updated_at || null,
    },
    {
      key: 'submitted',
      summary: normalize(task.result_summary) || undefined,
      detail: normalize(task.reflection) || undefined,
      at: task.submitted_at || null,
    },
    {
      key: 'approved',
      summary: normalize(task.review_note) || undefined,
      at: task.approved_at || null,
    },
    {
      key: 'experience',
      summary: experienceCards[0]?.summary || experienceCards[0]?.title || undefined,
      detail: experienceCards[0]?.current_pattern || undefined,
      at: experienceCards[0]?.created_at || null,
    },
    {
      key: 'archive',
      summary: archived
        ? (task.work_node_archive?.gitee_path
          ? `已写入 Gitee：${task.work_node_archive.gitee_path}`
          : task.work_node_archive?.local_root
            ? `已落盘本地：${task.work_node_archive.local_root}`
            : '已完成归档，暂无可展示路径')
        : '任务确认后可归档到 Gitee experiences 仓库',
      at: archived ? task.work_node_archive?.archived_at || null : null,
    },
  ]

  return defs.map((item) => ({
    key: item.key,
    label: phaseLabels[item.key],
    status: phaseStatusFor(
      item.key,
      taskStatus,
      hasThinking,
      hasExecution,
      hasExperience,
      archived,
    ),
    summary: item.summary,
    detail: item.detail,
    at: item.at,
  }))
}

const matchExperienceCards = (
  member: ChildMemberRuntimeProfile | null,
  task: AutonomyFormalTask,
): WorkNodeExperienceCard[] => {
  const cards = member?.experience_journal?.cards || []
  const taskId = normalize(task.task_id)
  const taskTitle = normalize(task.title)
  return cards
    .filter((card) => {
      const reflections = card.source_reflections || []
      if (reflections.some((item) => item.includes(taskId))) return true
      if (taskTitle && normalize(card.title) === taskTitle) return true
      return false
    })
    .map((card) => ({
      card_id: card.card_id,
      title: card.title,
      summary: card.summary,
      stage: card.stage,
      current_pattern: card.current_pattern,
      professional_risk: card.professional_risk,
      next_experiment: card.next_experiment,
      created_at: card.created_at,
    }))
}

export function buildWorkNodes(input: {
  workTypes: WorkTypeItem[]
  members: ChildMemberRuntimeProfile[]
  tasks: AutonomyFormalTask[]
}): WorkNode[] {
  const { workTypes, members, tasks } = input
  const workTypeTitleById = new Map(
    workTypes.map((item) => [String(item.work_type_id || '').trim(), String(item.title || item.work_type_id || '').trim()]),
  )
  workTypeTitleById.set('__unbound__', '未绑定工种')

  const memberById = new Map(
    members.map((item) => [String(item.member_id || '').trim(), item]),
  )

  return tasks
    .slice()
    .sort((left, right) => normalize(right.assigned_at || right.submitted_at).localeCompare(normalize(left.assigned_at || left.submitted_at)))
    .map((task) => {
      const memberId = normalize(task.member_id)
      const member = memberById.get(memberId) || null
      const workTypeId = resolveMemberWorkTypeId(member) || '__unbound__'
      const taskId = normalize(task.task_id) || `task:${memberId}:${normalize(task.assigned_at)}`
      const taskStatus = normalize(task.status)
      const experienceCards = matchExperienceCards(member, task)
      const archiveMeta = task.work_node_archive
      const archiveStatus = normalize(archiveMeta?.status)
      const archived = ['archived', 'exported', 'local_only'].includes(archiveStatus)
      const status = archived ? 'archived' : mapTaskStatus(taskStatus)

      const phases = buildPhases({
        task,
        member,
        experienceCards,
        archived,
      })

      return {
        node_id: `node:${taskId}`,
        task_id: taskId,
        work_type_id: workTypeId,
        work_type_title: workTypeTitleById.get(workTypeId) || workTypeId,
        member_id: memberId,
        member_name: normalize(member?.name || member?.identity?.name || memberId),
        assigned_by_member_id: normalize(task.assigned_by_member_id) || undefined,
        assigned_by_name: normalize(memberById.get(normalize(task.assigned_by_member_id))?.name || memberById.get(normalize(task.assigned_by_member_id))?.identity?.name || task.assigned_by_member_id) || undefined,
        objective: normalize(task.objective) || undefined,
        deliverables: (task.deliverables || []).filter((item) => normalize(item)),
        department_id: normalize(member?.organization?.department_id) || undefined,
        department_label: normalize(member?.organization?.department_label) || undefined,
        title: normalize(task.title) || '未命名任务',
        status,
        status_label: archived ? '已归档' : formatTaskStatusLabel(taskStatus),
        updated_at: task.approved_at || task.submitted_at || task.assigned_at || null,
        phases,
        experience_cards: experienceCards,
        archive: archiveMeta || undefined,
        archive_hint: archiveMeta?.gitee_path || archiveMeta?.local_root || (archived
          ? '已完成归档，但当前记录未提供可展示的路径'
          : '任务确认并沉淀经验后可归档'),
        member_link: `/organization/child/${encodeURIComponent(memberId)}/workspace`,
        trainer_link: `/organization/trainer/talent_development_officer/workspace?mode=dispatch&member=${encodeURIComponent(memberId)}`,
      } satisfies WorkNode
    })
}

export function filterWorkNodes(nodes: WorkNode[], filter: {
  work_type_id?: string
  member_id?: string
  node_id?: string
}): WorkNode[] {
  let result = nodes
  if (filter.work_type_id) {
    result = result.filter((item) => item.work_type_id === filter.work_type_id)
  }
  if (filter.member_id) {
    result = result.filter((item) => item.member_id === filter.member_id)
  }
  if (filter.node_id) {
    result = result.filter((item) => item.node_id === filter.node_id)
  }
  return result
}

export function collectExperienceCards(nodes: WorkNode[]): WorkNodeExperienceCard[] {
  const seen = new Set<string>()
  const cards: WorkNodeExperienceCard[] = []
  for (const node of nodes) {
    for (const card of node.experience_cards) {
      const key = String(card.card_id || `${card.title}-${card.created_at}`)
      if (seen.has(key)) continue
      seen.add(key)
      cards.push(card)
    }
  }
  return cards.sort((left, right) => normalize(right.created_at).localeCompare(normalize(left.created_at)))
}

export function workNodeStatusClass(status: WorkNodeStatus): string {
  if (status === 'archived') return 'bg-slate-100 text-slate-700'
  if (status === 'approved') return 'bg-emerald-100 text-emerald-800'
  if (status === 'submitted') return 'bg-violet-100 text-violet-800'
  if (status === 'running') return 'bg-cyan-100 text-cyan-800'
  return 'bg-amber-100 text-amber-800'
}
