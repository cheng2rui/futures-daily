<template>
  <div class="diagnostics">
    <div class="page-head">
      <div>
        <h2 class="page-title">数据源诊断</h2>
        <p class="muted">{{ tradeDate || '暂无日期' }} ｜ 聚焦 DCE / INE：覆盖矩阵、弱源诊断、原始响应和 parser replay。</p>
      </div>
      <div class="head-actions">
        <input v-model="tradeDateInput" placeholder="YYYYMMDD" @keyup.enter="load" />
        <button class="primary" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="notice" class="notice success">{{ notice }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <SectionCard v-if="operationResult" title="最近一次操作结果" class="op-card">
      <div class="op-summary">{{ operationResult.summary || '暂无总结' }}</div>
      <div class="replay-stats">
        <span>核心覆盖 {{ operationResult.coverage_diff?.core_coverage_after ?? 0 }}% <em>({{ fmtDelta(operationResult.coverage_diff?.core_coverage_delta) }})</em></span>
        <span>综合覆盖 {{ operationResult.coverage_diff?.overall_coverage_after ?? 0 }}% <em>({{ fmtDelta(operationResult.coverage_diff?.overall_coverage_delta) }})</em></span>
        <span>改善 {{ operationResult.coverage_diff?.improved_cells ?? 0 }}</span>
        <span>回退 {{ operationResult.coverage_diff?.regressed_cells ?? 0 }}</span>
      </div>
      <div class="op-tail">{{ operationResult.note || operationResult.message || '-' }}</div>
    </SectionCard>

    <div class="kpi-row">
      <KpiCard label="核心覆盖" :value="`${coverageSummary.core_coverage_pct ?? 0}%`" color="#3f5efb" />
      <KpiCard label="综合覆盖" :value="`${coverageSummary.overall_coverage_pct ?? 0}%`" color="#16c79a" />
      <KpiCard label="部分交易所" :value="coverageSummary.partial_exchanges || 0" color="#f5a623" />
      <KpiCard label="源健康均分" :value="sourceHealthSummary.average_score ?? 0" :color="sourceHealthColor" />
    </div>

    <SectionCard title="数据源健康">
      <div class="source-health-head">
        <b>{{ sourceHealthSummary.summary || '暂无来源健康数据' }}</b>
        <span>Top: {{ (sourceHealthSummary.top_sources || []).join(' / ') || '-' }}</span>
      </div>
      <div class="source-grid">
        <article v-for="src in sourceHealthRows" :key="src.source" class="source-card" :class="`source-${src.status}`">
          <div class="source-top">
            <b>{{ src.source }}</b>
            <em>{{ src.score }}</em>
          </div>
          <p>{{ src.summary }}</p>
          <div class="source-metrics">
            <span>成功率 {{ src.success_rate }}%</span>
            <span>运行 {{ src.runs_success }}/{{ src.runs_total }}</span>
            <span>归档 {{ src.archives_count }}</span>
            <span>缺口 {{ src.open_gaps }}</span>
          </div>
          <div v-if="src.latest_error" class="source-error">{{ src.latest_error }}</div>
        </article>
      </div>
    </SectionCard>

    <SectionCard title="自动补采计划" style="margin-top:16px">
      <div class="retry-head">
        <div>
          <b>{{ retryPlan.summary?.summary || '暂无补采建议' }}</b>
          <span>跳过 {{ retryPlan.summary?.skipped ?? 0 }} 项不可自动处理数据。</span>
        </div>
        <button class="secondary" :disabled="loadingPlan || !retryPlanSteps.length" @click="runFirstRetryStep">{{ loadingPlan ? '执行中...' : '执行第一步' }}</button>
      </div>
      <div v-if="!retryPlanSteps.length" class="empty-state small success">当前没有建议自动补采的步骤。</div>
      <div v-else class="retry-list">
        <article v-for="step in retryPlanSteps" :key="`${step.order}-${step.type}-${step.exchange}-${step.kind}`" class="retry-step">
          <div class="retry-top">
            <b>#{{ step.order }} {{ step.type }} · {{ exchangeName(step.exchange) }} · {{ kindLabel(step.kind) }}</b>
            <em>优先级 {{ step.priority }}</em>
          </div>
          <p>{{ step.reason }}</p>
          <div class="retry-meta">
            <span>源：{{ step.source }} / {{ step.source_status }}</span>
            <span>预期：{{ step.expected_effect }}</span>
            <span>风险：{{ step.risk }}</span>
          </div>
          <button class="mini-action" :disabled="loadingPlan" @click="runRetryStep(step)">执行这一步</button>
        </article>
      </div>
      <details v-if="retryPlanSkipped.length" class="skip-details">
        <summary>查看跳过项 {{ retryPlanSkipped.length }} 个</summary>
        <div class="skip-list">
          <span v-for="item in retryPlanSkipped" :key="`${item.exchange}-${item.kind}`">{{ exchangeName(item.exchange) }} · {{ kindLabel(item.kind) }}：{{ item.reason }}</span>
        </div>
      </details>
    </SectionCard>

    <SectionCard title="覆盖矩阵" style="margin-top:16px">
      <div class="matrix-table">
        <table>
          <thead><tr><th>交易所</th><th v-for="kind in coverageKinds" :key="kind.key">{{ kind.label }}</th><th>结论</th></tr></thead>
          <tbody>
            <tr v-for="row in coverageRows" :key="row.exchange">
              <td>{{ exchangeName(row.exchange) }}</td>
              <td v-for="kind in coverageKinds" :key="`${row.exchange}-${kind.key}`">
                <span class="status-pill" :class="`status-${cell(row, kind.key).status}`" :title="cell(row, kind.key).message">
                  {{ cellLabel(cell(row, kind.key)) }}
                </span>
              </td>
              <td class="note-cell">{{ row.summary || '-' }}</td>
            </tr>
            <tr v-if="!coverageRows.length"><td class="empty-cell" colspan="9">暂无覆盖矩阵</td></tr>
          </tbody>
        </table>
      </div>
    </SectionCard>

    <div class="exchange-grid">
      <SectionCard v-for="item in diagnostics" :key="item.exchange" :title="`${exchangeName(item.exchange)} 诊断`">
        <div class="diag-summary" :class="`diag-${item.status}`">{{ item.summary || statusLabel(item.status) }}</div>
        <div v-if="!item.issues?.length" class="empty-state small success">暂无明显问题。</div>
        <div v-else class="issue-list">
          <article v-for="issue in item.issues" :key="`${item.exchange}-${issue.kind}-${issue.status}`" class="issue-card" :class="`issue-${issue.severity}`">
            <div class="issue-head">
              <b>{{ kindLabel(issue.kind) }}</b>
              <span :class="`status-text-${issue.status}`">{{ statusLabel(issue.status) }}</span>
            </div>
            <p>{{ issue.message }}</p>
            <div class="issue-meta">
              <span>run: {{ issue.latest_run ? `${issue.latest_run.status} / saved ${issue.latest_run.saved}` : '-' }}</span>
              <span>gap: {{ issue.latest_gap ? `${issue.latest_gap.status} / ${issue.latest_gap.message}` : '-' }}</span>
              <span>raw: {{ issue.latest_archive ? `#${issue.latest_archive.id} / ${fmtBytes(issue.latest_archive.size_bytes)}` : '-' }}</span>
            </div>
          </article>
        </div>
        <div class="action-list">
          <button
            v-for="action in item.actions || []"
            :key="`${item.exchange}-${action.type}-${action.kind || action.note}`"
            class="mini-action"
            :disabled="runningAction === `${item.exchange}-${action.kind}` || action.type !== 'recollect'"
            :title="action.note || action.endpoint || ''"
            @click="runRecollect(item.exchange, action.kind)"
          >
            {{ action.type === 'recollect' ? `补采${kindLabel(action.kind)}` : action.type }}
          </button>
        </div>
      </SectionCard>
    </div>

    <SectionCard title="Raw Archive / Parser Replay" style="margin-top:16px">
      <div class="archive-toolbar">
        <select v-model="archiveExchange" @change="loadArchives">
          <option value="">全部交易所</option>
          <option value="DCE">DCE</option>
          <option value="INE">INE</option>
        </select>
        <select v-model="archiveKind" @change="loadArchives">
          <option value="">全部类型</option>
          <option value="daily">日行情</option>
          <option value="seat_rank">席位</option>
          <option value="basis">基差</option>
          <option value="warehouse_receipt">仓单</option>
        </select>
        <button class="secondary" :disabled="loadingArchives" @click="loadArchives">刷新原始响应</button>
      </div>
      <div class="archive-table">
        <table>
          <thead><tr><th>ID</th><th>交易所</th><th>类型</th><th>来源</th><th>行数</th><th>大小</th><th>错误</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="row in archives" :key="row.id">
              <td>#{{ row.id }}</td>
              <td>{{ exchangeName(row.exchange) }}</td>
              <td>{{ kindLabel(row.kind) }}</td>
              <td>{{ row.source }}</td>
              <td>{{ row.rows }}</td>
              <td>{{ fmtBytes(row.size_bytes) }}</td>
              <td class="note-cell">{{ row.error || '-' }}</td>
              <td><button class="mini-action" :disabled="replaying === row.id" @click="replay(row)">{{ replaying === row.id ? '重放中...' : 'Replay' }}</button></td>
            </tr>
            <tr v-if="!archives.length"><td class="empty-cell" colspan="8">暂无 raw archive</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="replayResult" class="replay-result">
        <div class="replay-head">
          <b>Replay #{{ replayResult.file?.id }} · {{ statusLabel(replayResult.status) }}</b>
          <span>{{ replayResult.message }}</span>
        </div>
        <div class="replay-stats">
          <span>输入 {{ replayResult.input_rows ?? 0 }}</span>
          <span>解析 {{ replayResult.parsed_rows ?? 0 }}</span>
          <span>成功率 {{ replayResult.success_rate ?? 0 }}%</span>
          <span>跳过 {{ replayResult.skipped_rows ?? 0 }}</span>
          <span>错误 {{ replayResult.error_count ?? 0 }}</span>
        </div>
        <pre>{{ JSON.stringify({ stats: replayResult.stats, sample: replayResult.sample, errors: replayResult.errors }, null, 2) }}</pre>
      </div>
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import KpiCard from '../components/KpiCard.vue'
import SectionCard from '../components/SectionCard.vue'
import { exchangeName } from '../exchange.js'
import { kindLabel, statusLabel } from '../labels.js'

const loading = ref(false)
const loadingArchives = ref(false)
const tradeDate = ref('')
const tradeDateInput = ref('')
const coverage = ref({ rows: [], kinds: [], summary: {} })
const sourceHealth = ref({ sources: [], summary: {} })
const retryPlan = ref({ steps: [], skipped: [], summary: {} })
const diagnosticData = ref({ exchanges: [] })
const archives = ref([])
const archiveExchange = ref('')
const archiveKind = ref('')
const replayResult = ref(null)
const replaying = ref(null)
const runningAction = ref('')
const loadingPlan = ref(false)
const operationResult = ref(null)
const notice = ref('')
const error = ref('')

const coverageRows = computed(() => coverage.value.rows || [])
const coverageKinds = computed(() => coverage.value.kinds || [])
const coverageSummary = computed(() => coverage.value.summary || {})
const sourceHealthRows = computed(() => sourceHealth.value.sources || [])
const sourceHealthSummary = computed(() => sourceHealth.value.summary || {})
const sourceHealthColor = computed(() => sourceHealthSummary.value.status === 'good' ? '#16c79a' : sourceHealthSummary.value.status === 'warn' ? '#f5a623' : '#e94560')
const retryPlanSteps = computed(() => retryPlan.value.steps || [])
const retryPlanSkipped = computed(() => retryPlan.value.skipped || [])
const diagnostics = computed(() => diagnosticData.value.exchanges || [])

function cell(row, kind) { return row?.cells?.[kind] || { status: 'missing', rows: 0, message: '未采集' } }
function cellLabel(c) {
  const labels = { ok: '✓', fallback: '备', partial: '!', missing: '—', failed: '×', not_supported: 'NA' }
  const base = labels[c.status] || '?'
  return ['ok', 'fallback', 'partial'].includes(c.status) && c.rows ? `${base} ${fmtNum(c.rows)}` : base
}
function fmtNum(v) { const n = Number(v || 0); if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return String(Math.round(n)) }
function fmtBytes(v) { const n = Number(v || 0); if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`; if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`; return `${n} B` }
function fmtDelta(v) { const n = Number(v || 0); return n > 0 ? `+${n}%` : `${n}%` }

async function resolveLatestDate() {
  const { data } = await api.get('/dataset/varieties/latest')
  return data?.trade_date || ''
}

async function load() {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const date = tradeDateInput.value.trim() || tradeDate.value || await resolveLatestDate()
    if (!date) throw new Error('暂无可诊断日期')
    tradeDate.value = date
    tradeDateInput.value = date
    const [coverageResp, healthResp, planResp, diagResp] = await Promise.all([
      api.get(`/quality/coverage/${date}`),
      api.get(`/quality/source-health/${date}`),
      api.get(`/quality/retry-plan/${date}`),
      api.get(`/quality/diagnostics/${date}`),
    ])
    coverage.value = coverageResp.data || { rows: [], kinds: [], summary: {} }
    sourceHealth.value = healthResp.data || { sources: [], summary: {} }
    retryPlan.value = planResp.data || { steps: [], skipped: [], summary: {} }
    diagnosticData.value = diagResp.data || { exchanges: [] }
    await loadArchives()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadArchives() {
  if (!tradeDate.value) return
  loadingArchives.value = true
  try {
    const params = { trade_date: tradeDate.value, limit: 50 }
    if (archiveExchange.value) params.exchange = archiveExchange.value
    if (archiveKind.value) params.kind = archiveKind.value
    const { data } = await api.get('/dataset/raw-archives', { params })
    archives.value = data || []
  } finally {
    loadingArchives.value = false
  }
}

async function replay(row) {
  replaying.value = row.id
  replayResult.value = null
  try {
    const { data } = await api.post(`/dataset/raw-archives/${row.id}/replay`)
    replayResult.value = data
    operationResult.value = {
      summary: `Replay #${row.id}：解析 ${data.parsed_rows ?? 0}/${data.input_rows ?? 0} 行，成功率 ${data.success_rate ?? 0}%`,
      message: data.message,
      note: data.status === 'unsupported' ? '该类型暂未实现 parser replay。' : 'dry-run only，未修改数据库。',
      coverage_diff: null,
    }
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || 'Replay 失败'
  } finally {
    replaying.value = null
  }
}

async function runRecollect(exchange, kind) {
  return runRecollectInternal(exchange, kind)
}

async function runFirstRetryStep() {
  const step = retryPlanSteps.value[0]
  if (step) await runRetryStep(step)
}

async function runRetryStep(step) {
  if (!step) return
  if (step.type === 'recollect') return runRecollectInternal(step.exchange, step.kind)
  if (step.type === 'collect_quhe') return runCollectQuhe(step)
}

async function runRecollectInternal(exchange, kind) {
  if (!tradeDate.value || !exchange || !kind) return
  runningAction.value = `${exchange}-${kind}`
  loadingPlan.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/reports/${tradeDate.value}/recollect`, null, { params: { exchange, kinds: kind, rebuild: true } })
    notice.value = data?.summary || `${exchange} ${kindLabel(kind)}补采完成`
    operationResult.value = {
      summary: data?.coverage_diff?.summary || data?.summary || `${exchange} ${kindLabel(kind)}补采完成`,
      message: data?.summary,
      note: `job #${data?.job_id || '-'} · ${data?.job_status || '-'}`,
      coverage_diff: data?.coverage_diff || {},
    }
    await load()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '补采失败'
  } finally {
    runningAction.value = ''
    loadingPlan.value = false
  }
}

async function runCollectQuhe(step) {
  if (!tradeDate.value) return
  loadingPlan.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/dataset/collect-quhe/${tradeDate.value}`)
    notice.value = `${step?.source || '增强源'}刷新完成`
    operationResult.value = {
      summary: `增强源刷新完成：${data?.materialized?.count ?? 0} 个品种已物化`,
      message: step?.reason || '',
      note: '已刷新曲合/官方增强数据；请查看覆盖矩阵是否改善。',
      coverage_diff: {},
    }
    await load()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '增强源刷新失败'
  } finally {
    loadingPlan.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:18px; gap:12px; }
.page-title { color:#1a1a2e; }
.muted { color:#888; margin-top:4px; line-height:1.6; }
.head-actions { display:flex; gap:8px; align-items:center; }
.head-actions input, .archive-toolbar select { border:1px solid #ddd; border-radius:10px; padding:10px 12px; background:#fff; }
.primary { background:#e94560; color:white; border:0; border-radius:10px; padding:10px 16px; font-weight:800; cursor:pointer; }
.secondary, .mini-action { background:#f1f5ff; color:#3157d5; border:1px solid #dbe3ff; border-radius:10px; padding:8px 12px; font-weight:800; cursor:pointer; }
.primary:disabled, .secondary:disabled, .mini-action:disabled { opacity:.55; cursor:wait; }
.notice { margin-bottom:16px; padding:11px 14px; border-radius:10px; }
.notice.success { background:#effaf5; color:#15845f; border:1px solid #d6f3e5; }
.notice.error { background:#fff1f2; color:#be123c; border:1px solid #fecdd3; }
.op-card { margin-bottom:16px; }
.op-summary { color:#0f172a; font-weight:900; line-height:1.5; margin-bottom:10px; }
.op-tail { margin-top:10px; color:#64748b; font-size:13px; }
.replay-stats em { font-style:normal; color:#64748b; }
.kpi-row { display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:16px; }
.source-health-head { display:flex; justify-content:space-between; gap:12px; align-items:center; color:#334155; margin-bottom:12px; }
.source-health-head span { color:#64748b; font-size:13px; }
.source-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.source-card { border:1px solid #e8edf5; border-radius:14px; padding:13px; background:#fff; display:grid; gap:9px; }
.source-good { border-color:#bbf7d0; background:#f7fffb; }
.source-warn { border-color:#fed7aa; background:#fffaf0; }
.source-bad { border-color:#fecdd3; background:#fff8f9; }
.source-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.source-top b { color:#0f172a; }
.source-top em { font-style:normal; font-weight:950; color:#3157d5; background:#eef2ff; border:1px solid #dbe3ff; border-radius:999px; padding:4px 8px; }
.source-card p { margin:0; color:#475569; line-height:1.45; font-size:13px; }
.source-metrics { display:flex; flex-wrap:wrap; gap:6px; }
.source-metrics span { background:#f8fafc; color:#64748b; border:1px solid #e2e8f0; border-radius:999px; padding:4px 7px; font-size:12px; font-weight:850; }
.source-error { color:#be123c; background:#fff1f2; border:1px solid #fecdd3; border-radius:10px; padding:7px 9px; font-size:12px; line-height:1.4; }
.matrix-table, .archive-table { width:100%; overflow:auto; }
table { width:100%; min-width:860px; border-collapse:separate; border-spacing:0; font-size:13px; }
th { background:#f8fafc; color:#475569; text-align:left; padding:11px 12px; border-bottom:1px solid #e2e8f0; white-space:nowrap; }
td { padding:11px 12px; border-bottom:1px solid #f1f5f9; white-space:nowrap; }
.note-cell { white-space:normal; color:#64748b; min-width:220px; }
.status-pill { display:inline-flex; min-width:46px; justify-content:center; border-radius:999px; padding:4px 8px; font-weight:950; border:1px solid #e2e8f0; background:#f8fafc; color:#64748b; }
.status-ok { background:#ecfdf5; border-color:#bbf7d0; color:#047857; }
.status-fallback { background:#eef2ff; border-color:#dbe3ff; color:#3157d5; }
.status-partial { background:#fff7ed; border-color:#fed7aa; color:#b45309; }
.status-missing { background:#f8fafc; border-color:#e2e8f0; color:#94a3b8; }
.status-failed { background:#fff1f2; border-color:#fecdd3; color:#be123c; }
.status-not_supported { background:#f1f5f9; border-color:#e2e8f0; color:#94a3b8; }
.exchange-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
.diag-summary { padding:10px 12px; border-radius:12px; background:#f8fafc; color:#475569; margin-bottom:12px; font-weight:800; }
.diag-failed { background:#fff1f2; color:#be123c; } .diag-partial { background:#fff7ed; color:#b45309; } .diag-ok { background:#ecfdf5; color:#047857; }
.issue-list { display:grid; gap:10px; }
.issue-card { border:1px solid #e8edf5; border-radius:14px; padding:12px; background:#fff; }
.issue-error { border-color:#fecdd3; background:#fff8f9; } .issue-warning { border-color:#fed7aa; background:#fffaf0; }
.issue-head { display:flex; justify-content:space-between; gap:8px; font-weight:900; }
.issue-card p { color:#475569; line-height:1.5; margin:8px 0; }
.issue-meta { display:grid; gap:5px; color:#64748b; font-size:12px; }
.action-list, .archive-toolbar, .replay-stats { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.retry-head { display:flex; justify-content:space-between; gap:12px; align-items:center; color:#334155; margin-bottom:12px; }
.retry-head b { display:block; color:#0f172a; }
.retry-head span { display:block; margin-top:4px; color:#64748b; font-size:13px; }
.retry-list { display:grid; gap:10px; }
.retry-step { border:1px solid #e8edf5; border-radius:14px; padding:13px; background:#fff; display:grid; gap:9px; }
.retry-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.retry-top b { color:#0f172a; }
.retry-top em { font-style:normal; color:#b45309; background:#fff7ed; border:1px solid #fed7aa; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:950; }
.retry-step p { margin:0; color:#475569; line-height:1.5; }
.retry-meta { display:grid; gap:5px; color:#64748b; font-size:12px; }
.skip-details { margin-top:12px; color:#64748b; }
.skip-details summary { cursor:pointer; font-weight:900; color:#334155; }
.skip-list { display:grid; gap:6px; margin-top:8px; font-size:12px; }
.empty-state { padding:24px; text-align:center; color:#888; background:#fafafa; border-radius:10px; }
.empty-state.small { padding:18px; } .empty-state.success { color:#15845f; background:#effaf5; border:1px solid #d6f3e5; }
.empty-cell { text-align:center; color:#94a3b8; padding:24px !important; }
.replay-result { margin-top:14px; border:1px solid #e8edf5; border-radius:14px; padding:14px; background:#fbfdff; }
.replay-head { display:flex; justify-content:space-between; gap:12px; color:#334155; }
.replay-stats span { background:#eef2ff; color:#3157d5; border:1px solid #dbe3ff; border-radius:999px; padding:5px 9px; font-weight:900; font-size:12px; }
pre { margin-top:12px; max-height:360px; overflow:auto; background:#0f172a; color:#dbeafe; border-radius:12px; padding:12px; font-size:12px; }
@media (max-width: 980px) { .kpi-row, .exchange-grid, .source-grid { grid-template-columns:1fr; } .page-head, .head-actions, .source-health-head, .retry-head { flex-direction:column; align-items:stretch; } }
</style>
