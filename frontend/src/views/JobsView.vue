<template>
  <div>
    <h2 class="page-title">任务记录</h2>
    <SectionCard title="最近任务">
      <SimpleTable :columns="columns" :data="rows" />
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { statusLabel } from '../labels.js'

const jobs = ref([])
const columns = ['ID', '任务', '状态', '交易日', '开始', '结束', '消息', '详情']
const rows = computed(() => jobs.value.map(j => [j.id, j.name, statusLabel(j.status), j.trade_date || '-', fmt(j.started_at), fmt(j.finished_at), j.message || '-', detail(j)]))
function fmt(v) { return v ? String(v).replace('T', ' ').slice(0, 19) : '-' }
function detail(j) {
  if (!j.result_json) return '-'
  try {
    const data = JSON.parse(j.result_json)
    if (data.dispatch) {
      return data.dispatch.map(channelResult).join(' / ')
    }
    if (j.name === 'recollect_report' || data.exchange || data.kinds) {
      return recollectDetail(data)
    }
    if (data.collect || data.seats || data.quhe || data.news) {
      return ['collect', 'seats', 'quhe', 'news'].filter(k => data[k]).join(' / ') || '-'
    }
    return Object.keys(data).slice(0, 4).join(' / ') || '-'
  } catch {
    return String(j.result_json).slice(0, 60)
  }
}
function recollectDetail(data) {
  if (data.summary) return data.summary
  const parts = []
  if (data.exchange) parts.push(`交易所：${data.exchange}`)
  if (data.kinds?.length) parts.push(`类型：${data.kinds.map(kindLabel).join('、')}`)
  if (data.collect) parts.push(`行情保存 ${savedRows(data.collect)} 行`)
  if (data.seats) parts.push(`席位保存 ${savedRows(data.seats)} 行`)
  const q = data.quality || data.data_quality
  if (q?.overall_coverage_pct != null) parts.push(`可信度 ${q.overall_coverage_pct}%`)
  return parts.join(' / ') || '-'
}
function savedRows(result) {
  return (result.results || []).reduce((sum, x) => sum + Number(x.saved || 0), 0)
}
function kindLabel(kind) {
  return ({ daily: '行情', seat_rank: '席位' })[kind] || kind
}
function channelResult(x) {
  const name = channelLabel(x.channel)
  if (x.ok === true) return `${name}：成功`
  if (x.skipped) return `${name}：未启用`
  const reason = x.error || x.reason || x.body || (x.status_code ? `HTTP ${x.status_code}` : '失败')
  return `${name}：${String(reason).slice(0, 36)}`
}
function channelLabel(channel) {
  return ({ telegram: 'Telegram', wecom: '企业微信', wechatbot: 'WeChatBot' })[channel] || channel || '-'
}
onMounted(async () => { jobs.value = (await api.get('/jobs')).data })
</script>

<style scoped>
.page-title { margin-bottom: 20px; color: #1a1a2e; }
</style>
