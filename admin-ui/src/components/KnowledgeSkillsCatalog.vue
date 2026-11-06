<template>
  <div class="rounded-2xl border border-slate-200 bg-white shadow-sm">
    <table class="w-full">
      <thead class="border-b bg-slate-50">
        <tr class="text-left text-sm text-slate-500">
          <th class="px-4 py-3 font-medium">技能名称</th>
          <th class="px-4 py-3 font-medium">领域</th>
          <th class="px-4 py-3 font-medium">信任级别</th>
          <th class="px-4 py-3 font-medium">来源 / 任务</th>
          <th class="px-4 py-3 font-medium">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="skill in skills" :key="`${skill.domain}-${skill.name}`" class="border-b last:border-0 hover:bg-slate-50">
          <td class="px-4 py-3 font-mono text-sm">{{ skill.name }}</td>
          <td class="px-4 py-3">{{ skill.domain || '-' }}</td>
          <td class="px-4 py-3">
            <StatusBadge :status="skill.trust_level || 'draft'" />
          </td>
          <td class="px-4 py-3">
            <div>{{ skill.source || 'local' }}</div>
            <div v-if="skill.provenance?.mission_run_id" class="mt-1 text-xs text-slate-500">
              Mission: {{ skill.provenance.mission_run_id }}
            </div>
            <div v-if="skill.provenance?.evidence_ids?.length" class="mt-1 text-xs text-slate-500">
              经验证据 {{ skill.provenance.evidence_ids.length }} 条
            </div>
          </td>
          <td class="px-4 py-3">
            <button
              @click="viewSkill(skill)"
              class="text-sm text-teal-600 hover:text-teal-800"
            >
              查看
            </button>
          </td>
        </tr>
        <tr v-if="skills.length === 0">
          <td colspan="5" class="px-4 py-8 text-center text-gray-500">
            <div v-if="loading" class="loading">加载中...</div>
            <div v-else>当前租户暂无本地技能</div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="selectedSkill" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div class="max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg bg-white p-6">
        <h2 class="mb-4 text-xl font-bold">技能详情</h2>
        <div class="space-y-4 text-sm">
          <section class="rounded-lg border border-slate-200 p-4">
            <div class="font-semibold text-slate-900">{{ selectedSkill.name }}</div>
            <p class="mt-1 text-slate-600">{{ selectedSkill.description || '暂无描述' }}</p>
            <div class="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-600">
              <div><span class="text-slate-400">领域</span><div class="mt-1">{{ selectedSkill.domain || '-' }}</div></div>
              <div><span class="text-slate-400">能力类型</span><div class="mt-1">{{ selectedSkill.capability_type || '-' }}</div></div>
              <div><span class="text-slate-400">来源</span><div class="mt-1">{{ selectedSkill.source || 'local' }}</div></div>
              <div><span class="text-slate-400">版本</span><div class="mt-1">{{ selectedSkill.version || '-' }}</div></div>
              <div><span class="text-slate-400">使用次数</span><div class="mt-1">{{ selectedSkill.usage_count ?? 0 }}</div></div>
              <div><span class="text-slate-400">成功率</span><div class="mt-1">{{ selectedSkill.success_rate ?? '-' }}</div></div>
            </div>
          </section>

          <section class="rounded-lg border border-slate-200 p-4">
            <h3 class="font-semibold text-slate-900">来源与任务链路</h3>
            <p class="mt-1 text-xs text-amber-700">信任级别是技能文件的存储层级标记；当前技能注册表的自动验证与云端发布入口处于关闭保护状态，不能仅凭“verified”标记认定技能已通过真实回放验证。</p>
            <dl class="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
              <div><dt class="text-slate-400">Mission Run</dt><dd class="mt-1 break-all">{{ selectedSkill.provenance?.mission_run_id || selectedSkill.parameters?.mission_run_id || '-' }}</dd></div>
              <div><dt class="text-slate-400">Mission Node</dt><dd class="mt-1 break-all">{{ selectedSkill.provenance?.mission_node_id || selectedSkill.parameters?.mission_node_id || '-' }}</dd></div>
              <div><dt class="text-slate-400">主路由 Worker</dt><dd class="mt-1 break-all">{{ selectedSkill.provenance?.primary_worker_id || selectedSkill.parameters?.primary_worker_id || selectedSkill.provenance?.worker_id || selectedSkill.parameters?.worker_id || selectedSkill.parameters?.source_worker_id || '未记录' }}</dd></div>
              <div><dt class="text-slate-400">经验证据</dt><dd class="mt-1">{{ selectedSkill.provenance?.evidence_ids?.length || (Array.isArray(selectedSkill.parameters?.evidence_ids) ? selectedSkill.parameters.evidence_ids.length : 0) }} 条</dd></div>
            </dl>
            <div v-if="selectedSkill.parameters?.validation_evidence" class="mt-3">
              <div class="text-xs font-medium text-slate-500">验证证据</div>
              <pre class="mt-1 overflow-auto rounded bg-slate-50 p-3 text-xs">{{ JSON.stringify(selectedSkill.parameters.validation_evidence, null, 2) }}</pre>
            </div>
            <div v-if="selectedSkill.provenance?.source_experiences?.length" class="mt-3">
              <div class="text-xs font-medium text-slate-500">聚合来源经验（{{ selectedSkill.provenance.source_experiences.length }} 条）</div>
              <div class="mt-2 space-y-2">
                <div
                  v-for="source in selectedSkill.provenance.source_experiences"
                  :key="source.experience_id || source.mission_run_id || source.mission_node_id"
                  class="rounded bg-slate-50 p-3 text-xs"
                >
                  <div class="font-medium text-slate-700 break-all">Experience: {{ source.experience_id || '未记录' }}</div>
                  <div class="mt-1 break-all">Mission: {{ source.mission_run_id || '未记录' }} <span v-if="source.mission_node_id">/ Node: {{ source.mission_node_id }}</span></div>
                  <div class="mt-1 break-all">Worker: {{ source.primary_worker_id || '未记录' }}</div>
                  <div class="mt-1">任务证据: {{ source.evidence_ids?.length || 0 }} 条</div>
                  <details v-if="source.validation_evidence || source.decision_trace" class="mt-2">
                    <summary class="cursor-pointer text-slate-500">查看该经验的验证与决策记录</summary>
                    <pre class="mt-1 overflow-auto rounded bg-white p-2">{{ JSON.stringify({ validation_evidence: source.validation_evidence, decision_trace: source.decision_trace }, null, 2) }}</pre>
                  </details>
                </div>
              </div>
            </div>
            <div v-if="selectedSkill.provenance?.source_mission_run_ids?.length || selectedSkill.provenance?.source_worker_ids?.length" class="mt-3 text-xs text-slate-600">
              <div>来源 Missions: {{ selectedSkill.provenance?.source_mission_run_ids?.join(', ') || '未记录' }}</div>
              <div class="mt-1">来源 Workers: {{ selectedSkill.provenance?.source_worker_ids?.join(', ') || '未记录' }}</div>
            </div>
            <div v-if="selectedSkill.parameters?.decision_trace" class="mt-3">
              <div class="text-xs font-medium text-slate-500">决策轨迹</div>
              <pre class="mt-1 overflow-auto rounded bg-slate-50 p-3 text-xs">{{ JSON.stringify(selectedSkill.parameters.decision_trace, null, 2) }}</pre>
            </div>
            <p class="mt-3 text-xs text-slate-500">未记录的来源字段会显示为“未记录”，不会根据任务名称或文件位置推断。</p>
          </section>

          <details class="rounded-lg border border-slate-200 p-4">
            <summary class="cursor-pointer font-medium text-slate-700">查看完整技能数据</summary>
            <pre class="mt-3 overflow-auto rounded bg-gray-50 p-3 text-xs">{{ JSON.stringify(selectedSkill, null, 2) }}</pre>
          </details>
        </div>
        <div class="mt-4 flex justify-end">
          <button
            @click="selectedSkill = null"
            class="rounded-lg bg-gray-200 px-4 py-2 text-gray-700 hover:bg-gray-300"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import StatusBadge from './StatusBadge.vue'
import { getKnowledgeSkillDetail, type KnowledgeSkill } from '../api/knowledge'

const props = defineProps<{
  tenantId: string
  skills: KnowledgeSkill[]
  loading: boolean
}>()

const selectedSkill = ref<KnowledgeSkill | null>(null)
let detailRequestVersion = 0

watch(() => props.tenantId, () => {
  detailRequestVersion += 1
  selectedSkill.value = null
})

const viewSkill = async (skill: KnowledgeSkill) => {
  const requestVersion = ++detailRequestVersion
  const tenantId = props.tenantId || 'default'
  try {
    const response = await getKnowledgeSkillDetail(
      tenantId,
      skill.domain || 'unknown',
      skill.name
    )
    if (requestVersion !== detailRequestVersion || tenantId !== (props.tenantId || 'default')) return
    selectedSkill.value = response.success && response.data ? response.data : skill
  } catch {
    if (requestVersion === detailRequestVersion && tenantId === (props.tenantId || 'default')) {
      selectedSkill.value = skill
    }
  }
}
</script>
