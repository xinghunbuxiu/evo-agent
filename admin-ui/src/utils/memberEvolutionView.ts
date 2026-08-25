import type { LearningTask } from '../api/plugins'

type MemberLike = object | null | undefined

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' ? value as Record<string, unknown> : {}
)

export const buildMemberEvolutionThinking = (member: MemberLike) => {
  const memberRecord = asRecord(member)
  const memoryHub = asRecord(memberRecord.memory_hub)
  const decisionState = asRecord(memoryHub.decision_state)
  const status = String(decisionState.status || '').trim()
  const statusLabel = status === 'ready_to_execute'
    ? '可执行'
    : status === 'needs_external_learning'
      ? '需外部学习'
      : status === 'blocked'
        ? '受阻'
        : (status || '待思考')
  return {
    status,
    statusLabel,
    primaryPlan: String(decisionState.primary_plan || '').trim(),
    fallbackPlan: String(decisionState.fallback_plan || '').trim(),
    verificationGoal: String(decisionState.verification_goal || '').trim(),
    escalationReason: String(decisionState.escalation_reason || '').trim(),
    decisionIntent: String(memoryHub.decision_intent || '').trim(),
    externalLearningRequired: Boolean(
      asRecord(memoryHub.decision_summary).external_learning_required,
    ),
  }
}

export const buildMemberIndependenceReadiness = (member: MemberLike) => {
  const memberRecord = asRecord(member)
  const trainingPlan = asRecord(memberRecord.training_plan)
  const readiness = asRecord(trainingPlan.independence_readiness)
  const criteria = Array.isArray(readiness.criteria)
    ? readiness.criteria.map((item) => {
      const row = asRecord(item)
      return {
        id: String(row.id || ''),
        label: String(row.label || ''),
        met: Boolean(row.met),
      }
    })
    : []
  return {
    ready: Boolean(readiness.ready_for_independence),
    metCount: Number(readiness.met_criteria_count || 0),
    total: Number(readiness.total_criteria || criteria.length || 0),
    criteria,
  }
}

export const formatLearningTaskStatus = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return '--'
  if (normalized === 'needs_learning') return '待补知识'
  if (normalized === 'researching') return '调研中'
  if (normalized === 'candidate_found') return '已有候选'
  if (normalized === 'ready_for_validation') return '待验证'
  if (normalized === 'validating') return '验证中'
  if (normalized === 'validated_improved') return '验证通过'
  if (normalized === 'resolved') return '已解决'
  return normalized
}

export const buildMemberIndependenceHandoff = (member: MemberLike) => {
  const trainingPlan = asRecord(asRecord(member).training_plan)
  const handoff = asRecord(trainingPlan.independence_handoff)
  const readiness = asRecord(trainingPlan.independence_readiness)
  const notifiedAt = String(trainingPlan.independence_notified_at || handoff.notified_at || '').trim()
  return {
    ready: Boolean(readiness.ready_for_independence),
    notified: Boolean(notifiedAt),
    notifiedAt,
    metCount: Number(readiness.met_criteria_count || handoff.met_criteria_count || 0),
    total: Number(readiness.total_criteria || handoff.total_criteria || 0),
    nextAction: String(trainingPlan.next_action || '').trim(),
  }
}

export const buildMemberKnowledgeLearningPlan = (member: MemberLike) => {
  const trainingPlan = asRecord(asRecord(member).training_plan)
  return {
    taskId: String(trainingPlan.knowledge_learning_task_id || '').trim(),
    status: String(trainingPlan.knowledge_learning_status || '').trim(),
    summary: String(trainingPlan.knowledge_learning_summary || '').trim(),
    nextAction: String(trainingPlan.next_action || '').trim(),
    updatedAt: String(trainingPlan.knowledge_learning_updated_at || '').trim(),
    followupRecommendationId: String(trainingPlan.knowledge_followup_recommendation_id || '').trim(),
  }
}

export const findMemberKnowledgeLearningTask = (
  member: MemberLike,
  learningTasks: LearningTask[],
) => {
  const memberRecord = asRecord(member)
  const memberId = String(memberRecord.member_id || '').trim()
  if (!memberId) return null
  const trainingPlan = asRecord(memberRecord.training_plan)
  const linkedId = String(trainingPlan.knowledge_learning_task_id || '').trim()
  if (linkedId) {
    const linked = learningTasks.find((item) => String(item.task_id || '').trim() === linkedId)
    if (linked) return linked
  }
  return learningTasks.find((item) => {
    const taskMemberId = String((item as LearningTask & { member_id?: string }).member_id || '').trim()
    const source = String(item.source || '').trim()
    return taskMemberId === memberId && (source === 'memory_hub_auto' || item.mission_kind === 'autonomy_training')
  }) || null
}
