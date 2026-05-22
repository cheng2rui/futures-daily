<template>
  <div class="jobs-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">任务记录</h2>
        <p>查看日报生成、盘中刷新、补采和推送任务的执行状态。</p>
      </div>
      <button class="refresh" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新' }}</button>
    </div>

    <SectionCard title="任务筛选">
      <div class="filters">
        <label>
          <span>任务类型</span>
          <select v-model="typeFilter">
            <option value="all">全部</option>
            <option value="generate_report">生成日报</option>
            <option value="refresh_intraday">盘中刷新</option>
            <option value="recollect_report">数据补采</option>
            <option value="push_report">日报推送</option>
          </select>
        </label>
        <label>
          <span>状态</span>
          <select v-model="statusFilter">
            <option value="all">全部</option>
            <option value="success">成功</option>
            <option value="partial">部分成功</option>
            <option value="failed">失败</option>
            <option value="running">运行中</option>
          </select>
        </label>
        <label>
          <span>搜索</span>
          <input v-model="query" placeholder="任务名 / 交易日 / 消息" />
        </label>
      </div>
    </SectionCard>

    <SectionCard title="最近任务" style="margin-top:16px">
      <div class="job-list">
        <div v-for="job in filteredJobs" :key="job.id" class="job-card" :class="statusTone(job.status)">
          <div class="job-main" @click="toggle(job.id)">
            <div class="job-id">#{{ job.id }}</div>
            <div class="job-name">
              <b>{{ jobLabel(job.name) }}</b>
              <span>{{ job.name }}</span>
            </div>
            <div class="job-status">{{ statusLabel(job.status) }}</div>
            <div class="job-date">{{ job.trade_date || '-' }}</div>
            <div class="job-time">
              <span>{{ fmt(job.started_at) }}</span>
              <small>{{ duration(job) }}</small>
            </div>
            <div class="job-message">{{ job.message || '-' }}</div>
            <button class="expand">{{ expandedIds.includes(job.id) ? '收起' : '详情' }}</button>
          </div>
          <div v-if="expandedIds.includes(job.id)" class="job-detail">
            <div class="summary-line">{{ detail(job) }}</div>
            <div v-if="parsed(job)?.collect" class="exchange-results">
              <div v-for="x in parsed(job).collect.results || []" :key="`c-${x.exchange}`" class="result-row" :class="x.error ? 'bad' : 'ok'">
                <b>{{ x.exchange }}</b><span>行情 {{ x.saved ?? 0 }}/{{ x.rows ?? 0 }} 行</span><small>{{ x.error || '正常' }}</small>
              </div>
            </div>
            <div v-if="parsed(job)?.seats" class="exchange-results">
              <div v-for="x in parsed(job).seats.results || []" :key="`s-${x.exchange}`" class="result-row" :class="x.error ? 'bad' : 'ok'">
                <b>{{ x.exchange }}</b><span>席位 {{ x.saved ?? 0 }}/{{ x.rows ?? 0 }} 行</span><small>{{ x.error || '正常' }}</small>
              </div>
            </div>
            <div v-if="parsed(job)?.dispatch" class="exchange-results">
              <div v-for="x in parsed(job).dispatch" :key="x.channel || x.reason" class="result-row" :class="x.ok === true ? 'ok' : x.skipped ? 'skip' : 'bad'">
                <b>{{ channelLabel(x.channel) }}</b><span>{{ x.ok === true ? '成功' : x.skipped ? '跳过' : '失败' }}</span><small>{{ x.error || x.reason || x.body || '-' }}</small>
              </div>
            </div>
            <pre v-if="showRaw(job)">{{ prettyJson(job.result_json) }}</pre>
          </div>
        </div>
        <div v-if="!filteredJobs.length" class="empty">暂无匹配任务</div>
      </div>
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'
import { statusLabel } from '../labels.js'

const jobs = ref([])
const loading = ref(false)
const typeFilter = ref('all')
const statusFilter = ref('all')
const query = ref('')
const expandedIds = ref([])

const filteredJobs = computed(() => jobs.value.filter(j => {
  if (typeFilter.value !== 'all' && j.name !== typeFilter.value) return false
  if (statusFilter.value !== 'all' && j.status !== statusFilter.value) return false
  const q = query.value.trim().toLowerCase()
  if (!q) return true
  return [j.name, j.status, j.trade_date, j.message].some(x => String(x || '').toLowerCase().includes(q))
}))

async function load() {
  loading.value = true
  try { jobs.value = (await api.get('/jobs', { params: { limit: 100 } })).data } finally { loading.value = false }
}
function toggle(id) { expandedIds.value = expandedIds.value.includes(id) ? expandedIds.value.filter(x => x !== id) : [...expandedIds.value, id] }
function fmt(v) { return v ? String(v).replace('T', ' ').slice(0, 19) : '-' }
function duration(j) {
  if (!j.started_at || !j.finished_at) return j.status === 'running' ? '运行中' : '-'
  const ms = new Date(j.finished_at) - new Date(j.started_at)
  if (!Number.isFinite(ms) || ms < 0) return '-'
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}
function statusTone(status) { return status === 'success' ? 'ok' : status === 'failed' ? 'bad' : status === 'running' ? 'running' : 'partial' }
function jobLabel(name) { return ({ generate_report: '生成日报', refresh_intraday: '盘中刷新', recollect_report: '数据补采', push_report: '日报推送' })[name] || name }
function parsed(j) { try { return JSON.parse(j.result_json || '{}') } catch { return null } }
function detail(j) {
  const data = parsed(j)
  if (!data) return String(j.result_json || '-').slice(0, 80)
  if (data.summary) return data.summary
  if (data.dispatch) return data.dispatch.map(channelResult).join(' / ')
  if (j.name === 'refresh_intraday') return `行情保存 ${savedRows(data.collect)} 行${data.snapshot?.updated_at ? `｜更新 ${data.snapshot.updated_at}` : ''}`
  if (j.name === 'recollect_report' || data.exchange || data.kinds) return recollectDetail(data)
  if (data.collect || data.seats || data.quhe || data.news) return ['collect', 'seats', 'quhe', 'news'].filter(k => data[k]).join(' / ') || '-'
  return Object.keys(data).slice(0, 4).join(' / ') || '-'
}
function recollectDetail(data) {
  const parts = []
  if (data.exchange) parts.push(`交易所：${data.exchange}`)
  if (data.kinds?.length) parts.push(`类型：${data.kinds.map(kindLabel).join('、')}`)
  if (data.collect) parts.push(`行情保存 ${savedRows(data.collect)} 行`)
  if (data.seats) parts.push(`席位保存 ${savedRows(data.seats)} 行`)
  const q = data.quality || data.data_quality
  if (q?.overall_coverage_pct != null) parts.push(`可信度 ${q.overall_coverage_pct}%`)
  return parts.join(' / ') || '-'
}
function savedRows(result) { return (result?.results || []).reduce((sum, x) => sum + Number(x.saved || 0), 0) }
function kindLabel(kind) { return ({ daily: '行情', seat_rank: '席位' })[kind] || kind }
function channelResult(x) {
  const name = channelLabel(x.channel)
  if (x.ok === true) return `${name}：成功`
  if (x.skipped) return `${name}：未启用`
  const reason = x.error || x.reason || x.body || (x.status_code ? `HTTP ${x.status_code}` : '失败')
  return `${name}：${String(reason).slice(0, 36)}`
}
function channelLabel(channel) { return ({ telegram: 'Telegram', wecom: '企业微信', wechatbot: 'WeChatBot' })[channel] || channel || '-' }
function showRaw(job) { const data = parsed(job); return data && !data.collect && !data.seats && !data.dispatch }
function prettyJson(raw) { try { return JSON.stringify(JSON.parse(raw || '{}'), null, 2) } catch { return raw || '' } }

onMounted(load)
</script>

<style scoped>
.jobs-page { display:grid; gap:0; }
.page-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:20px; }
.page-title { margin:0 0 6px; color:#1a1a2e; }
.page-head p { margin:0; color:#64748b; }
.refresh { background:#3f5efb; color:#fff; border:0; border-radius:10px; padding:9px 14px; font-weight:900; cursor:pointer; }
.filters { display:grid; grid-template-columns:180px 180px 1fr; gap:12px; }
.filters label { display:grid; gap:6px; color:#64748b; font-weight:800; }
.filters select, .filters input { border:1px solid #dbe3ef; border-radius:10px; padding:9px 10px; background:#fff; }
.job-list { display:grid; gap:10px; }
.job-card { border:1px solid #e8edf5; border-radius:16px; background:#fff; overflow:hidden; box-shadow:0 8px 18px rgba(15,23,42,.04); }
.job-card.ok { border-left:5px solid #16a34a; } .job-card.bad { border-left:5px solid #dc2626; } .job-card.partial { border-left:5px solid #f59e0b; } .job-card.running { border-left:5px solid #3f5efb; }
.job-main { display:grid; grid-template-columns:70px 150px 88px 96px 160px minmax(180px,1fr) 72px; gap:10px; align-items:center; padding:12px 14px; cursor:pointer; }
.job-id { color:#94a3b8; font-weight:900; }
.job-name b { display:block; color:#0f172a; } .job-name span, .job-time small { display:block; color:#94a3b8; font-size:12px; margin-top:3px; }
.job-status { font-weight:900; color:#334155; }
.job-date, .job-time, .job-message { color:#475569; font-size:13px; }
.job-message { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.expand { border:0; border-radius:999px; padding:7px 10px; background:#f1f5ff; color:#3157d5; font-weight:900; cursor:pointer; }
.job-detail { border-top:1px solid #eef2f7; background:#fbfdff; padding:13px 16px; display:grid; gap:10px; }
.summary-line { color:#334155; font-weight:800; }
.exchange-results { display:grid; gap:7px; }
.result-row { display:grid; grid-template-columns:90px 150px 1fr; gap:10px; align-items:center; padding:8px 10px; border-radius:10px; background:#fff; border:1px solid #eef2f7; }
.result-row.ok { border-left:4px solid #16a34a; } .result-row.bad { border-left:4px solid #dc2626; } .result-row.skip { border-left:4px solid #94a3b8; }
.result-row small { color:#64748b; word-break:break-all; }
pre { margin:0; max-height:320px; overflow:auto; border-radius:12px; background:#0f172a; color:#dbeafe; padding:12px; font-size:12px; }
.empty { color:#94a3b8; text-align:center; padding:28px; background:#f8fafc; border-radius:14px; }
@media (max-width:1100px) { .filters, .job-main { grid-template-columns:1fr; } .job-message { white-space:normal; } .result-row { grid-template-columns:1fr; } }
</style>
