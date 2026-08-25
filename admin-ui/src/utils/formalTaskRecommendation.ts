import type { MissionTemplate } from '../api/missions'
import type { WorkTypeItem } from '../api/workTypes'
import type { ChildMemberRuntimeProfile } from '../api/plugins'

export type FormalTaskRecommendation = {
  title: string
  objective: string
  deliverables: string[]
  mission_kind?: string
  work_type_id?: string
  capability_type?: string
  template_title?: string
  source: 'work_type_template' | 'generic'
}

export function resolveMemberWorkTypeId(member: ChildMemberRuntimeProfile | null | undefined): string {
  const jobId = String(member?.current_jobs?.[0]?.job_id || '').trim()
  const primaryRole = String(member?.primary_role || member?.role_memory?.primary_identity || '').trim()
  if (jobId && jobId !== 'pending_role') return jobId
  if (primaryRole && primaryRole !== 'pending_role') return primaryRole
  return ''
}

export function findWorkTypeForMember(
  member: ChildMemberRuntimeProfile | null | undefined,
  workTypes: WorkTypeItem[],
): WorkTypeItem | null {
  const workTypeId = resolveMemberWorkTypeId(member)
  if (!workTypeId) return null
  return workTypes.find((item) => item.work_type_id === workTypeId) || null
}

export function resolveWorkTypeMissionKind(workType: WorkTypeItem | null | undefined): string {
  if (!workType) return ''
  return String(
    workType.mission_kind
    || workType.runtime_route?.mission_kind
    || '',
  ).trim()
}

export function buildFormalTaskRecommendation(input: {
  member: ChildMemberRuntimeProfile
  workTypes: WorkTypeItem[]
  missionTemplates: MissionTemplate[]
  accountId?: string
}): FormalTaskRecommendation {
  const { member, workTypes, missionTemplates, accountId = 'default' } = input
  const memberName = String(member.name || member.identity?.name || member.member_id || '当前员工').trim()
  const workType = findWorkTypeForMember(member, workTypes)
  const workTypeId = workType?.work_type_id || resolveMemberWorkTypeId(member)
  const roleLabel = String(workType?.title || member.persona?.role_label || member.primary_role || '岗位员工').trim()
  const missionKind = resolveWorkTypeMissionKind(workType)
  let template = missionKind
    ? missionTemplates.find((item) => item.mission_kind === missionKind) || null
    : null
  if (!template && workType?.capability_type) {
    template = missionTemplates.find((item) => item.primary_capability_type === workType.capability_type) || null
  }
  const resolvedMissionKind = missionKind || String(template?.mission_kind || '').trim()
  const defaultGoal = String(workType?.goal_schema?.default_goal || member.role_memory?.long_term_goal || '').trim()
  const normalizedAccountId = String(accountId || 'default').trim() || 'default'

  if (workType && template) {
    const deliveryTargets = Array.isArray(template.delivery_targets) ? template.delivery_targets : []
    const deliverables = deliveryTargets.length
      ? deliveryTargets.map((item) => `交付：${item}`)
      : [
        `完成一轮 ${roleLabel} 真实实践（账号/场景 ${normalizedAccountId}）`,
        '提交结果总结与过程证据',
        '沉淀阻塞点与有效动作',
        '给出下一轮优化方向',
      ]
    return {
      title: `${memberName} · ${template.title || roleLabel}首轮任务`,
      objective: defaultGoal
        || String(template.description || '').trim()
        || `围绕 ${roleLabel} 在当前场景 ${normalizedAccountId} 完成第一轮 ${template.title || resolvedMissionKind} 闭环。`,
      deliverables,
      mission_kind: resolvedMissionKind,
      work_type_id: workTypeId || undefined,
      capability_type: String(workType.capability_type || template.primary_capability_type || '').trim() || undefined,
      template_title: String(template.title || '').trim() || undefined,
      source: 'work_type_template',
    }
  }

  if (workType) {
    return {
      title: `${memberName} · ${roleLabel}首轮岗位任务`,
      objective: defaultGoal
        || `围绕 ${roleLabel} 在当前账号/场景 ${normalizedAccountId} 完成第一轮真实任务闭环，拿到结果样本、过程证据和首轮复盘。`,
      deliverables: [
        `完成一轮 ${roleLabel} 真实实践，并说明场景 ${normalizedAccountId} 下的执行目标`,
        '提交结果总结',
        '沉淀阻塞与有效动作',
        '给出下一轮优化方向',
      ],
      mission_kind: resolvedMissionKind || undefined,
      work_type_id: workTypeId || undefined,
      capability_type: String(workType.capability_type || '').trim() || undefined,
      source: 'generic',
    }
  }

  return {
    title: `${memberName} 首轮岗位任务`,
    objective: `围绕 ${roleLabel} 在当前账号/场景 ${normalizedAccountId} 完成第一轮真实任务闭环，拿到结果样本、过程证据和首轮复盘。`,
    deliverables: [
      `完成一轮 ${roleLabel} 真实实践，并说明场景 ${normalizedAccountId} 下的执行目标`,
      '提交结果总结',
      '沉淀阻塞与有效动作',
      '给出下一轮优化方向',
    ],
    source: 'generic',
  }
}

export function formatFormalTaskRecommendationHint(recommendation: FormalTaskRecommendation | null): string {
  if (!recommendation) return ''
  if (recommendation.source === 'work_type_template' && recommendation.work_type_id) {
    const templateLabel = recommendation.template_title || recommendation.mission_kind || 'Mission 模板'
    return `已按工种 ${recommendation.work_type_id} / ${templateLabel} 生成任务草案`
  }
  if (recommendation.work_type_id) {
    return `已按工种 ${recommendation.work_type_id} 生成通用任务草案（未匹配 Mission 模板）`
  }
  return '尚未绑定岗位工种，使用通用首轮任务模板'
}
