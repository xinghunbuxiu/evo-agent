import type {
  AutonomyFormalTask,
  AutonomyFormalTaskRecommendation,
  AutonomyStatus,
  BrainOverview,
  ChildMemberRuntimeProfile,
} from '../api/plugins'
import type { FinanceOverview, FinanceSummary } from '../api/finance'
import type { WorkTypeItem } from '../api/workTypes'

export type OrgNode = {
  id: string
  kind: 'parent' | 'trainer' | 'child' | 'finance'
  kindLabel: string
  label: string
  role: string
  focus?: string
  nextAction?: string
  stage?: string
  status?: string
  headline?: string
  currentWorkLabel?: string
  currentWorkRoute?: string
  currentWorkStatus?: string
  recentGrowthSummary?: string
  needsAttention?: string
  attentionLevel?: 'stable' | 'watch' | 'priority'
  description?: string
  link?: string
}

export type BusinessProjectCard = {
  id: string
  title: string
  channels: string
  status: string
  projectStateLabel: string
  summary: string
  owner: string
  ownerLabel: string
  ownerNodeId?: string
  ownerLink?: string
  ownerRole?: string
  currentWork: string
  progressSummary: string
  blockerSummary: string
  revenueSummary: string
  nextMilestone?: string
  workspaceLink?: string
  detailRoute?: string
  stage?: string
  badgeClass: string
}

export type ProjectBucket = {
  key: 'running' | 'advancing' | 'experiment' | 'testing' | 'blocked'
  label: string
  items: BusinessProjectCard[]
  badgeClass: string
}

export type TrainerChildGroup = {
  trainerId: string
  trainerLabel: string
  children: OrgNode[]
}

export type WorkTypeMemberGroup = {
  workTypeId: string
  workTypeTitle: string
  children: OrgNode[]
}

export type DepartmentOrgGroup = {
  departmentId: string
  departmentLabel: string
  workTypeGroups: WorkTypeMemberGroup[]
  memberCount: number
}

const DEPARTMENT_ORDER = ['operations', 'rnd', 'unassigned'] as const
const DEPARTMENT_LABELS: Record<string, string> = {
  operations: '运营',
  rnd: '研发',
  unassigned: '未分组',
}

export type OrganizationModel = {
  parentNodeLabel: string
  parentNode: OrgNode
  runtimeChildMembers: ChildMemberRuntimeProfile[]
  trainerNodes: OrgNode[]
  childNodes: OrgNode[]
  financeNode: OrgNode
  supportNodes: OrgNode[]
  trainerChildGroups: TrainerChildGroup[]
  departmentChildGroups: DepartmentOrgGroup[]
  allNodes: OrgNode[]
  businessProjects: BusinessProjectCard[]
  projectBuckets: ProjectBucket[]
  attentionNodes: OrgNode[]
}

const normalize = (value?: string | null) => String(value || '').trim()
const normalizeLower = (value?: string | null) => normalize(value).toLowerCase()
const normalizeCompanyLabel = (value?: string | null) => {
  const normalized = normalize(value)
  if (!normalized) return '公司'
  if (['parent node', 'parent', '父节点'].includes(normalizeLower(normalized))) return '公司'
  return normalized
}

const normalizeCompanyRole = (value?: string | null) => {
  const normalized = normalize(value)
  if (!normalized) return '公司管理者'
  if (['parent node', 'parent', '父节点'].includes(normalizeLower(normalized))) return '公司管理者'
  return normalized
}

const stageLabel = (value?: string | null, fallback = '待安排') => {
  const normalized = normalize(value)
  if (!normalized) return fallback
  if (normalized === 'profile_initialized') return '已建档'
  if (normalized === 'portrait_created') return '画像已建立'
  if (normalized === 'trainer_taken_over') return '育成官已接手'
  if (normalized === 'ready_for_first_case') return '待进入首轮案例'
  if (normalized === 'first_case_running') return '首轮案例进行中'
  if (normalized === 'reflection_pending') return '待补复盘'
  if (normalized === 'first_reflection_done') return '首轮复盘完成'
  if (normalized === 'commercial_delivery_done') return '商业交付已结算'
  if (normalized === 'active_training') return '持续成长中'
  if (normalized === 'completed_cycle') return '本轮闭环完成'
  if (normalized === 'archived') return '已归档'
  if (normalized === 'foundation') return '基础建立中'
  if (normalized === 'planned') return '待启用'
  return normalized
}

const jobStatusLabel = (value?: string | null, fallback = '待安排') => {
  const normalized = normalizeLower(value)
  if (!normalized) return fallback
  if (normalized === 'planned') return '待安排'
  if (normalized === 'assigned') return '待执行'
  if (normalized === 'submitted') return '待确认'
  if (normalized === 'approved' || normalized === 'completed') return '已完成'
  if (normalized === 'waiting_login') return '等待接入'
  if (normalized === 'bootstrapping') return '推进中'
  if (normalized === 'running' || normalized === 'in_progress') return '推进中'
  if (normalized === 'testing' || normalized === 'validating') return '验证中'
  if (normalized === 'blocked') return '已卡住'
  if (normalized === 'failed' || normalized === 'executor_missing') return '需处理'
  return fallback === '待安排' ? '推进中' : fallback
}

const derivedStatusLabel = (value?: string | null, fallback = '正常推进') => {
  const normalized = normalizeLower(value)
  if (!normalized) return fallback
  if (normalized === 'idle') return '待启动'
  if (normalized === 'needs_learning') return '待补学习'
  if (normalized === 'awaiting_assignment') return '等待分配'
  if (normalized === 'training_children') return '带教中'
  if (normalized === 'active_training') return '持续成长中'
  if (normalized === 'validating') return '验证中'
  if (normalized === 'stable') return '稳定推进'
  if (normalized === 'delivering') return '交付中'
  if (normalized === 'blocked') return '已卡住'
  if (normalized === 'failed') return '需处理'
  return fallback
}

const attentionLevelFromText = (text?: string | null): 'stable' | 'watch' | 'priority' => {
  const normalized = normalizeLower(text)
  if (!normalized) return 'stable'
  if (
    normalized.includes('blocked')
    || normalized.includes('fail')
    || normalized.includes('missing')
    || normalized.includes('卡住')
    || normalized.includes('阻塞')
    || normalized.includes('失败')
    || normalized.includes('缺少')
  ) return 'priority'
  if (
    normalized.includes('review')
    || normalized.includes('等待')
    || normalized.includes('待')
    || normalized.includes('验证')
    || normalized.includes('巡检')
  ) return 'watch'
  return 'stable'
}

const attentionMeta = (level: 'stable' | 'watch' | 'priority') => {
  if (level === 'priority') {
    return { label: '需要介入', badgeClass: 'bg-rose-100 text-rose-700' }
  }
  if (level === 'watch') {
    return { label: '需要关注', badgeClass: 'bg-amber-100 text-amber-700' }
  }
  return { label: '正常推进', badgeClass: 'bg-emerald-100 text-emerald-700' }
}

const currentTaskForMember = (
  items: AutonomyFormalTask[] | undefined,
  memberId: string,
) => {
  const list = (items || [])
    .filter((item) => normalize(item.member_id) === memberId)
    .slice()
    .sort((left, right) => normalize(right.assigned_at).localeCompare(normalize(left.assigned_at)))
  return list.find((item) => normalizeLower(item.status) !== 'approved') || list[0] || null
}

const currentRecommendationForMember = (
  items: AutonomyFormalTaskRecommendation[] | undefined,
  memberId: string,
) => {
  const list = (items || [])
    .filter((item) => normalize(item.member_id) === memberId)
    .slice()
    .sort((left, right) => normalize(right.created_at).localeCompare(normalize(left.created_at)))
  return list.find((item) => normalizeLower(item.status) === 'suggested') || list[0] || null
}

const conversationPreviewForMember = (autonomyStatus: AutonomyStatus | null | undefined, memberId: string) => {
  const thread = autonomyStatus?.relationship_center?.conversation_threads?.find((item) => (
    normalize(item.thread_id) === `trainer:${memberId}`
  ))
  const latest = thread?.messages?.slice().sort((left, right) => (
    normalize(right.created_at).localeCompare(normalize(left.created_at))
  ))[0]
  return normalize(latest?.content)
}

const firstSentence = (value?: string | null, fallback = '暂无更新') => {
  const normalized = normalize(value)
  if (!normalized) return fallback
  return normalized.replace(/\s+/g, ' ').slice(0, 80)
}

const financeVerdictLabel = (verdict?: string | null) => {
  const key = normalizeLower(verdict)
  if (key === 'profitable') return '有盈利'
  if (key === 'break_even') return '收支平衡'
  if (key === 'loss') return '亏损'
  return '待确认'
}

export const formatFinanceHeadline = (finance?: FinanceSummary | null) => {
  if (!finance || !finance.updated_at) {
    return '等待接入经营数据。'
  }
  const period = normalize(finance.period)
  const net = Number.isFinite(finance.net) ? finance.net : 0
  const revenue = Number.isFinite(finance.revenue) ? finance.revenue : 0
  const verdict = financeVerdictLabel(finance.verdict)
  if (revenue > 0 || net !== 0) {
    return `${period} 净收益 ${net.toFixed(2)} 元（${verdict}）`
  }
  if (finance.views > 0) {
    return `${period} 阅读 ${finance.views}，互动 ${finance.likes + finance.comments}（${verdict}）`
  }
  return firstSentence(finance.headline, `${period} 经营数据已接入（${verdict}）`)
}

export const formatProjectRevenueSummary = (
  projectId: string,
  finance?: FinanceSummary | null,
  fallback = '营收链路待接入',
) => {
  if (!finance || !finance.updated_at) return fallback
  const financeProject = normalize(finance.project_id)
  const target = normalize(projectId)
  if (financeProject && financeProject !== target) {
    return fallback
  }
  return formatFinanceHeadline(finance)
}

const inferProjectMeta = (jobId?: string | null, title?: string | null) => {
  const normalized = normalize(jobId)
  const normalizedTitle = normalize(title)
  const derivedChannel = normalizedTitle || normalized || '待定义岗位'
  return {
    id: normalized || normalizedTitle.toLowerCase().replace(/\s+/g, '_') || 'unnamed_project',
    title: normalizedTitle || normalized || '未命名项目',
    channels: derivedChannel,
  }
}

const projectStatusMeta = (value?: string | null) => {
  const normalized = normalizeLower(value)
  if (['running', 'active', 'online', 'in_progress'].includes(normalized)) {
    return {
      key: 'running' as const,
      projectStateLabel: '营业中',
      badgeClass: 'bg-emerald-100 text-emerald-700',
    }
  }
  if (['planned', 'assigned', 'submitted', 'waiting_login'].includes(normalized)) {
    return {
      key: 'advancing' as const,
      projectStateLabel: '推进中',
      badgeClass: 'bg-cyan-100 text-cyan-700',
    }
  }
  if (['bootstrapping', 'researching', 'draft', 'learning'].includes(normalized)) {
    return {
      key: 'experiment' as const,
      projectStateLabel: '实验中',
      badgeClass: 'bg-sky-100 text-sky-700',
    }
  }
  if (['testing', 'validating', 'review'].includes(normalized)) {
    return {
      key: 'testing' as const,
      projectStateLabel: '测试中',
      badgeClass: 'bg-violet-100 text-violet-700',
    }
  }
  if (['failed', 'blocked', 'executor_missing'].includes(normalized)) {
    return {
      key: 'blocked' as const,
      projectStateLabel: '已停滞',
      badgeClass: 'bg-rose-100 text-rose-700',
    }
  }
  return {
    key: 'advancing' as const,
    projectStateLabel: '推进中',
    badgeClass: 'bg-cyan-100 text-cyan-700',
  }
}

const resolveMemberDepartment = (
  member: ChildMemberRuntimeProfile,
  workTypes: WorkTypeItem[],
): { departmentId: string; departmentLabel: string } => {
  const orgDeptId = normalize(member.organization?.department_id)
  if (orgDeptId) {
    return {
      departmentId: orgDeptId,
      departmentLabel: normalize(member.organization?.department_label) || DEPARTMENT_LABELS[orgDeptId] || orgDeptId,
    }
  }
  const workTypeId = normalize(member.current_jobs?.[0]?.job_id) || normalize(member.primary_role)
  const matched = workTypes.find((item) => normalize(item.work_type_id) === workTypeId)
  if (matched?.department_id) {
    const deptId = normalize(matched.department_id)
    return {
      departmentId: deptId,
      departmentLabel: normalize(matched.department_label) || DEPARTMENT_LABELS[deptId] || deptId,
    }
  }
  return { departmentId: 'unassigned', departmentLabel: DEPARTMENT_LABELS['unassigned'] }
}

const buildDepartmentChildGroups = (
  runtimeChildMembers: ChildMemberRuntimeProfile[],
  childNodes: OrgNode[],
  workTypes: WorkTypeItem[],
): DepartmentOrgGroup[] => {
  const nodeByMemberId = new Map(
    childNodes.map((node) => [node.id.replace(/^child:/, ''), node]),
  )
  const departmentBuckets = new Map<string, Map<string, { title: string; nodes: OrgNode[] }>>()

  for (const member of runtimeChildMembers) {
    if (normalize(member.primary_role) === 'talent_development') continue
    if (normalize(member.status || 'active') === 'archived') continue
    const memberId = normalize(member.member_id)
    const node = nodeByMemberId.get(memberId)
    if (!node) continue
    const { departmentId } = resolveMemberDepartment(member, workTypes)
    const workTypeId = normalize(member.current_jobs?.[0]?.job_id) || normalize(member.primary_role) || 'unknown'
    const matchedWt = workTypes.find((item) => normalize(item.work_type_id) === workTypeId)
    const workTypeTitle = normalize(matchedWt?.title) || normalize(member.persona?.role_label) || workTypeId

    if (!departmentBuckets.has(departmentId)) {
      departmentBuckets.set(departmentId, new Map())
    }
    const workTypeMap = departmentBuckets.get(departmentId)!
    if (!workTypeMap.has(workTypeId)) {
      workTypeMap.set(workTypeId, { title: workTypeTitle, nodes: [] })
    }
    workTypeMap.get(workTypeId)!.nodes.push(node)
  }

  const result: DepartmentOrgGroup[] = []
  const seenDept = new Set<string>()
  for (const deptId of [...DEPARTMENT_ORDER, ...departmentBuckets.keys()]) {
    if (seenDept.has(deptId) || !departmentBuckets.has(deptId)) continue
    seenDept.add(deptId)
    const workTypeMap = departmentBuckets.get(deptId)!
    const workTypeGroups = Array.from(workTypeMap.entries())
      .map(([workTypeId, payload]) => ({
        workTypeId,
        workTypeTitle: payload.title,
        children: payload.nodes,
      }))
      .sort((left, right) => left.workTypeTitle.localeCompare(right.workTypeTitle, 'zh-CN'))
    const memberCount = workTypeGroups.reduce((sum, group) => sum + group.children.length, 0)
    if (!memberCount) continue
    result.push({
      departmentId: deptId,
      departmentLabel: DEPARTMENT_LABELS[deptId] || deptId,
      workTypeGroups,
      memberCount,
    })
  }
  return result
}

export function buildOrganizationModel(
  autonomyStatus: AutonomyStatus | null | undefined,
  brainOverview?: BrainOverview | null,
  financeOverview?: FinanceOverview | null,
  workTypes: WorkTypeItem[] = [],
): OrganizationModel {
  const financeByProject = new Map<string, FinanceSummary>(
    (financeOverview?.items || []).map((item) => [normalize(item.project_id), item]),
  )
  const financeSummary = financeOverview?.primary || null
  const runtimeChildMembers = autonomyStatus?.child_members?.items || []
  const taskItems = autonomyStatus?.task_center?.items || []
  const recommendationItems = autonomyStatus?.task_center?.recommendations || []

  const trainerNodes: OrgNode[] = runtimeChildMembers
    .filter((item) => normalize(item.primary_role) === 'talent_development' && normalize(item.status || 'active') !== 'archived')
    .map((item) => {
      const memberId = normalize(item.member_id)
      const nextTarget = item.training_overview?.next_target
      const currentWorkLabel = normalize(nextTarget?.name)
        ? `正在巡检 ${normalize(nextTarget?.name)}`
        : '正在巡检员工成长'
      const currentWorkRoute = `/organization/trainer/${encodeURIComponent(memberId || 'talent_development_officer')}/workspace?mode=review&member=${encodeURIComponent(normalize(nextTarget?.member_id) || memberId || 'talent_development_officer')}`
      const recentGrowthSummary = firstSentence(
        item.self_development?.next_milestone
          || item.training_overview?.next_target?.next_action
          || item.self_development?.current_objective,
        '最近主要在优化带教判断和巡检节奏。',
      )
      const needsAttention = firstSentence(
        item.training_overview?.next_target?.next_action
          || item.world_observation?.blocked_by?.[0]
          || item.self_development?.missing_capabilities?.[0],
        '当前巡检正常推进。',
      )
      const attentionLevel = attentionLevelFromText(needsAttention)
      return {
        id: `trainer:${memberId}`,
        kind: 'trainer',
        kindLabel: '育成师',
        label: normalize(item.name) || memberId || '育成师',
        role: normalize(item.persona?.role_label) || '育成师',
        focus: firstSentence(item.growth_state?.current_focus || item.self_development?.current_objective, '正在巡检多位员工。'),
        nextAction: firstSentence(item.training_overview?.next_target?.next_action || item.training_plan?.next_action, '继续巡检下一位员工。'),
        stage: stageLabel(item.training_plan?.stage, '持续带教中'),
        status: derivedStatusLabel(item.derived_state?.status, '带教中'),
        headline: firstSentence(
          item.growth_state?.current_focus || item.self_development?.current_objective,
          '负责带教员工并推进成长闭环。',
        ),
        currentWorkLabel,
        currentWorkRoute,
        currentWorkStatus: derivedStatusLabel(item.derived_state?.status, '带教中'),
        recentGrowthSummary,
        needsAttention,
        attentionLevel,
        description: firstSentence(item.persona?.self_description, '负责员工画像、带教安排和成长推动。'),
        link: `/organization/trainer/${encodeURIComponent(memberId || 'talent_development_officer')}/workspace?mode=portrait&portraitTab=summary`,
      }
    })

  const fallbackIdentity = autonomyStatus?.child_agent?.identity
  const fallbackRoleMemory = autonomyStatus?.child_agent?.role_memory
  if (!trainerNodes.some((item) => item.id === 'trainer:talent_development_officer') && normalize(fallbackRoleMemory?.primary_identity) === 'talent_development') {
    trainerNodes.unshift({
      id: 'trainer:talent_development_officer',
      kind: 'trainer',
      kindLabel: '育成师',
      label: normalize(fallbackIdentity?.name) || '育成师',
      role: '育成师',
      focus: '正在等待接手新的员工。',
      nextAction: '继续建立第一份正式员工画像。',
      stage: '基础建立中',
      status: '待接手',
      headline: '正在等待接手新的员工。',
      currentWorkLabel: '正在建立新员工画像',
      currentWorkRoute: '/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary',
      currentWorkStatus: '待安排',
      recentGrowthSummary: firstSentence(fallbackRoleMemory?.long_term_goal, '正在完善带教方法和画像能力。'),
      needsAttention: '当前需要建立第一份正式员工画像。',
      attentionLevel: 'watch',
      description: firstSentence(fallbackIdentity?.self_description, '负责员工画像、带教安排和成长推动。'),
      link: '/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary',
    })
  }

  const childNodes: OrgNode[] = runtimeChildMembers
    .filter((item) => normalize(item.primary_role) !== 'talent_development' && normalize(item.status || 'active') !== 'archived')
    .map((item) => {
      const memberId = normalize(item.member_id)
      const task = currentTaskForMember(taskItems, memberId)
      const recommendation = currentRecommendationForMember(recommendationItems, memberId)
      const messagePreview = conversationPreviewForMember(autonomyStatus, memberId)
      const memoryHub = item.memory_hub
      const currentWorkLabel = normalize(task?.title)
        || normalize(memoryHub?.decision_summary?.primary_plan)
        || normalize(recommendation?.title)
        || normalize(item.growth_state?.current_focus)
        || normalize(item.training_plan?.next_action)
        || '等待进入下一轮工作'
      const currentWorkStatus = normalize(memoryHub?.decision_state?.status)
        ? derivedStatusLabel(memoryHub?.decision_state?.status, jobStatusLabel(task?.status, derivedStatusLabel(item.derived_state?.status)))
        : jobStatusLabel(task?.status, derivedStatusLabel(item.derived_state?.status))
      const recentGrowthSummary = firstSentence(
        memoryHub?.decision_summary?.summary
          || item.professional_view?.reflection_summary
          || item.experience_journal?.cards?.[0]?.summary
          || item.growth_state?.next_goal,
        '最近还没有形成新的成长记录。',
      )
      const needsAttention = firstSentence(
        memoryHub?.decision_summary?.escalation_reason
          || memoryHub?.decision_summary?.stop_reason
          || item.derived_state?.blocked_reason
          || task?.review_note
          || recommendation?.reason
          || messagePreview,
        currentWorkStatus === '已卡住' ? '当前存在卡点需要处理。' : '当前暂无额外提醒。',
      )
      const attentionLevel = attentionLevelFromText(
        `${normalize(item.derived_state?.blocked_reason)} ${normalize(task?.status)} ${normalize(item.derived_state?.status)}`,
      )
      return {
        id: `child:${memberId}`,
        kind: 'child',
      kindLabel: '员工',
      label: normalize(item.name) || memberId || '员工成员',
        role: normalize(item.persona?.role_label) || normalize(item.primary_role) || '岗位成员',
        focus: firstSentence(memoryHub?.decision_intent || item.growth_state?.current_focus || item.professional_view?.current_judgement, currentWorkLabel),
        nextAction: firstSentence(memoryHub?.next_action || item.training_plan?.next_action || recommendation?.objective || task?.objective, '等待进入下一轮工作。'),
        stage: stageLabel(item.training_plan?.stage || item.onboarding?.status, '待进入岗位'),
        status: currentWorkStatus,
        headline: firstSentence(
          memoryHub?.decision_summary?.summary
            || memoryHub?.decision_state?.primary_plan
            || item.growth_state?.current_focus
            || item.professional_view?.current_judgement
            || task?.objective,
          '正在围绕岗位目标持续推进。',
        ),
        currentWorkLabel,
        currentWorkRoute: `/organization/child/${encodeURIComponent(memberId)}/workspace`,
        currentWorkStatus,
        recentGrowthSummary,
        needsAttention,
        attentionLevel,
        description: firstSentence(item.persona?.self_description, '这是一个正在成长中的岗位成员。'),
        link: `/organization/child/${encodeURIComponent(memberId)}/workspace`,
      }
    })

  const financeEnabled = Boolean(financeSummary?.updated_at)
  const financeHeadline = formatFinanceHeadline(financeSummary)
  const financeNode: OrgNode = {
    id: 'finance',
    kind: 'finance',
    kindLabel: '财务职能',
    label: '财务',
    role: '经营结算与资源分配',
    focus: financeEnabled ? financeHeadline : '等待头条分析任务写入经营数据。',
    nextAction: financeEnabled ? '查看项目看板中的收益摘要' : '先完成一次 operation_analytics（income/works）',
    stage: financeEnabled ? '已接入' : '待启用',
    status: financeEnabled ? '有数据' : '未启用',
    headline: financeHeadline,
    currentWorkLabel: financeEnabled ? '经营数据已同步' : '等待接入经营数据',
    currentWorkRoute: '/organization/finance',
    currentWorkStatus: financeEnabled ? '有数据' : '待启用',
    recentGrowthSummary: financeEnabled
      ? `本周结论：${financeVerdictLabel(financeSummary?.verdict)}。`
      : '当前还没有真实财务流水接入。',
    needsAttention: financeEnabled
      ? (financeSummary?.verdict === 'loss' ? '当前周期净收益为负，建议复盘内容与成本。' : '经营数据已接入，可结合项目看板决策。')
      : '先跑通头条 analytics 任务以生成收益/阅读指标。',
    attentionLevel: financeSummary?.verdict === 'loss' ? 'watch' : 'stable',
    description: '负责公司经营闭环，不直接参与内容执行。',
    link: '/organization/finance',
  }

  const trainerChildGroups: TrainerChildGroup[] = trainerNodes.map((node) => ({
    trainerId: node.id,
    trainerLabel: node.label,
    children: [],
  }))
  const fallbackGroup: TrainerChildGroup = {
    trainerId: 'trainer:unassigned',
    trainerLabel: '待分配育成师',
    children: [],
  }
  const groupMap = new Map(trainerChildGroups.map((item) => [item.trainerId.replace('trainer:', ''), item]))
  for (const node of childNodes) {
    const member = runtimeChildMembers.find((item) => `child:${normalize(item.member_id)}` === node.id)
    const ownerId = normalize(member?.onboarding?.training_owner_member_id || member?.training_plan?.owner_member_id)
    if (ownerId && groupMap.has(ownerId)) {
      groupMap.get(ownerId)?.children.push(node)
    } else {
      fallbackGroup.children.push(node)
    }
  }
  const groupedChildren = trainerChildGroups.filter((item) => item.children.length > 0)
  if (fallbackGroup.children.length > 0) groupedChildren.push(fallbackGroup)

  const departmentChildGroups = buildDepartmentChildGroups(runtimeChildMembers, childNodes, workTypes)

  const parentNodeLabel = normalizeCompanyLabel(autonomyStatus?.parent_profile?.display_name)
  const supportNodes = [...trainerNodes, financeNode]
  const parentAttention = childNodes
    .filter((item) => item.attentionLevel === 'priority')
    .slice(0, 2)
    .map((item) => `${item.label}：${item.needsAttention || item.currentWorkLabel || '需要关注'}`)
    .join('；')
  const parentNode: OrgNode = {
    id: 'parent',
    kind: 'parent',
    kindLabel: '公司',
    label: parentNodeLabel,
    role: normalizeCompanyRole(autonomyStatus?.parent_profile?.role_label),
    focus: firstSentence(autonomyStatus?.training_review?.last_message, '当前主要关注公司结构与重点项目。'),
    nextAction: parentAttention || childNodes[0]?.currentWorkLabel || '进入一个节点继续查看详情。',
    stage: autonomyStatus?.enabled ? '公司运行中' : '待启动',
    status: autonomyStatus?.enabled ? '正常运作' : '待启动',
    headline: firstSentence(
      autonomyStatus?.parent_profile?.description || autonomyStatus?.training_review?.last_message,
      '负责定义边界、资源和组织方向。',
    ),
    currentWorkLabel: '查看公司结构与重点项目',
    currentWorkRoute: '/organization/parent/workspace',
    currentWorkStatus: autonomyStatus?.enabled ? '正常运作' : '待启动',
    recentGrowthSummary: firstSentence(
      autonomyStatus?.training_review?.last_message,
      `当前有 ${childNodes.length} 位员工、${supportNodes.length} 个职能节点。`,
    ),
    needsAttention: parentAttention || '当前没有需要老板立刻介入的重点提醒。',
    attentionLevel: parentAttention ? 'watch' : 'stable',
    description: firstSentence(autonomyStatus?.parent_profile?.description, '负责公司制度、资源和组织边界。'),
    link: '/organization/parent/workspace',
  }

  const allNodes = [parentNode, ...supportNodes, ...childNodes]

  const projectMap = new Map<string, BusinessProjectCard>()
  for (const member of runtimeChildMembers) {
    if (normalize(member.primary_role) === 'talent_development' || normalize(member.status || 'active') === 'archived') continue
    const ownerLabel = normalize(member.name) || normalize(member.member_id) || '待分配成员'
    const ownerMemberId = normalize(member.member_id)
    const jobs = member.current_jobs || []
    for (const job of jobs) {
      const meta = inferProjectMeta(job.job_id, job.title)
      const statusMeta = projectStatusMeta(job.runtime_state?.status || job.status)
      const blocker = normalize(member.derived_state?.blocked_reason || job.runtime_state?.tenant_state?.blocked_reason)
      const progressSummary = firstSentence(
        job.runtime_state?.next_action || member.derived_state?.next_action || member.growth_state?.current_focus,
        '正在持续推进中。',
      )
      const summary = firstSentence(
        job.target_outcome || job.notes || job.runtime_state?.tenant_state?.target_outcome,
        `${meta.title} 正在稳定推进。`,
      )
      const revenueSummary = formatProjectRevenueSummary(
        meta.id,
        financeByProject.get(normalize(meta.id)) || null,
        statusMeta.key === 'running' ? '营收链路待接入' : '尚未进入营收阶段',
      )
      projectMap.set(meta.id, {
        id: meta.id,
        title: meta.title,
        channels: meta.channels,
        status: statusMeta.key,
        projectStateLabel: statusMeta.projectStateLabel,
        summary,
        owner: ownerLabel,
        ownerLabel,
        ownerNodeId: ownerMemberId ? `child:${ownerMemberId}` : undefined,
        ownerLink: ownerMemberId ? `/organization/child/${encodeURIComponent(ownerMemberId)}/workspace` : undefined,
        ownerRole: normalize(member.persona?.role_label) || normalize(member.primary_role) || '岗位成员',
        currentWork: progressSummary,
        progressSummary,
        blockerSummary: blocker || '当前无明显阻塞',
        revenueSummary,
        nextMilestone: firstSentence(member.training_plan?.next_action || member.growth_state?.next_goal, '等待下一里程碑'),
        workspaceLink: ownerMemberId ? `/organization/child/${encodeURIComponent(ownerMemberId)}/workspace` : undefined,
        detailRoute: ownerMemberId ? `/organization/child/${encodeURIComponent(ownerMemberId)}/workspace` : undefined,
        stage: stageLabel(member.training_plan?.stage || member.onboarding?.status),
        badgeClass: statusMeta.badgeClass,
      })
    }
  }

  const businessProjects = Array.from(projectMap.values())
  const projectBuckets: ProjectBucket[] = [
    {
      key: 'running',
      label: '营业中',
      items: businessProjects.filter((item) => item.status === 'running'),
      badgeClass: 'bg-emerald-100 text-emerald-700',
    },
    {
      key: 'advancing',
      label: '推进中',
      items: businessProjects.filter((item) => item.status === 'advancing'),
      badgeClass: 'bg-cyan-100 text-cyan-700',
    },
    {
      key: 'experiment',
      label: '实验中',
      items: businessProjects.filter((item) => item.status === 'experiment'),
      badgeClass: 'bg-sky-100 text-sky-700',
    },
    {
      key: 'testing',
      label: '测试中',
      items: businessProjects.filter((item) => item.status === 'testing'),
      badgeClass: 'bg-violet-100 text-violet-700',
    },
    {
      key: 'blocked',
      label: '已停滞',
      items: businessProjects.filter((item) => item.status === 'blocked'),
      badgeClass: 'bg-rose-100 text-rose-700',
    },
  ]

  const attentionNodes = allNodes
    .filter((item) => item.attentionLevel && item.attentionLevel !== 'stable')
    .sort((left, right) => {
      const leftWeight = left.attentionLevel === 'priority' ? 2 : 1
      const rightWeight = right.attentionLevel === 'priority' ? 2 : 1
      return rightWeight - leftWeight
    })

  if (!businessProjects.length && brainOverview?.summary?.mission_running) {
    parentNode.needsAttention = '当前检测到运行中的任务链路，但项目实体还没有完全建立。'
    parentNode.attentionLevel = 'watch'
  }

  return {
    parentNodeLabel,
    parentNode,
    runtimeChildMembers,
    trainerNodes,
    childNodes,
    financeNode,
    supportNodes,
    trainerChildGroups: groupedChildren,
    departmentChildGroups,
    allNodes,
    businessProjects,
    projectBuckets,
    attentionNodes,
  }
}

export const organizationAttentionMeta = attentionMeta
