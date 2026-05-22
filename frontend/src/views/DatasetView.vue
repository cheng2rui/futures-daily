<template>
  <div class="dataset">
    <div class="page-head">
      <div>
        <h2 class="page-title">数据资产</h2>
        <p class="muted">{{ data.trade_date || '暂无日期' }} ｜ 将合约行情、席位排名、结构化席位归档收敛成可直接分析的品种级数据集。</p>
      </div>
      <button class="primary" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="loading" class="notice">正在加载数据资产...</div>

    <div class="kpi-row">
      <KpiCard label="品种数" :value="data.count || 0" color="#e94560" />
      <KpiCard label="交易所" :value="exchangeRows.length" color="#0f3460" />
      <KpiCard label="归档品种" :value="data.summary?.archive_count || 0" color="#16c79a" />
      <KpiCard label="缺口" :value="gapAnalysis.count || gaps.length" color="#f5a623" />
      <KpiCard label="可行动缺口" :value="gapAnalysis.actionable_count ?? actionableGapCount" :color="(gapAnalysis.actionable_count ?? actionableGapCount) ? '#e94560' : '#16c79a'" />
    </div>

    <SectionCard title="六所覆盖矩阵">
      <SimpleTable :columns="['交易所', '品种数', '席位覆盖', '结构信号', '日行情', '席位状态', '归档状态', '说明']" :data="exchangeRows" />
    </SectionCard>

    <SectionCard title="数据缺口" style="margin-top:16px">
      <div v-if="!gapRows.length" class="empty-state small">暂无 open 缺口记录；注意旧数据在 crawler_runs 引入前不会自动生成缺口。</div>
      <SimpleTable v-else :columns="['日期', '交易所', '类型', '级别', '行数', '原因']" :data="gapRows" />
    </SectionCard>

    <SectionCard title="缺口原因分类" style="margin-top:16px">
      <div class="section-note">
        可行动缺口 {{ gapAnalysis.actionable_count ?? actionableGapCount }} 个；已解释缺口 {{ gapAnalysis.explained_count ?? explainedGapCount }} 个。
        下表先显示原因汇总，下面只展开可行动明细。
      </div>
      <SimpleTable :columns="['原因代码', '数量']" :data="reasonSummaryRows" />
      <div class="section-note detail-note">可行动明细 Top 80</div>
      <div v-if="!gapAnalysisRows.length" class="empty-state small success">当前没有可行动缺口；剩余缺口均已解释为源不覆盖、不适用、冷门/停用或第三方为空。</div>
      <SimpleTable v-else :columns="['交易所', '代码', '名称', '类型', '原因', '可处理']" :data="gapAnalysisRows" />
    </SectionCard>

    <SectionCard title="品种级可用数据集" style="margin-top:16px">
      <div class="filters">
        <input v-model="keyword" placeholder="搜索品种/代码/交易所，如 RB / 玻璃 / DCE" />
        <select v-model="qualityFilter">
          <option value="">全部</option>
          <option value="seat_missing">缺席位排名</option>
          <option value="archive_missing">缺结构化信号</option>
          <option value="complete">席位+信号都有</option>
        </select>
      </div>
      <SimpleTable :columns="['交易所', '代码', '名称', '主力', '涨跌幅', '总成交', '总持仓', '席位', '结构信号', '净变化', '资金流', '基差率', '仓单变化', '曲合净持仓']" :data="varietyRows" />
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import KpiCard from '../components/KpiCard.vue'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { contractName, exchangeName } from '../exchange.js'

const loading = ref(false)
const data = ref({ rows: [], summary: {} })
const gaps = ref([])
const coverage = ref([])
const facts = ref([])
const gapAnalysis = ref({ gaps: [] })
const keyword = ref('')
const qualityFilter = ref('')

const exchangeRows = computed(() => coverage.value.map(x => [exchangeName(x.exchange), x.varieties, `${x.with_seat_rank}/${x.varieties}`, `${x.with_archive_signal}/${x.varieties}`, x.daily_status, x.seat_status, x.archive_status, x.message || '-']))
const gapRows = computed(() => gaps.value.map(x => [x.trade_date, exchangeName(x.exchange), x.kind, x.severity, x.rows, x.message || '-']))
const gapAnalysisRows = computed(() => (gapAnalysis.value.gaps || []).filter(x => x.actionable).slice(0, 80).map(x => [exchangeName(x.exchange), x.symbol, x.name, x.kind, x.reason, x.actionable ? '是' : '否']))
const actionableGapCount = computed(() => (gapAnalysis.value.gaps || []).filter(x => x.actionable).length)
const explainedGapCount = computed(() => Math.max(0, (gapAnalysis.value.count || (gapAnalysis.value.gaps || []).length) - actionableGapCount.value))
const reasonSummaryRows = computed(() => Object.entries(gapAnalysis.value.summary || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, v]))
const varietyRows = computed(() => filteredRows.value.map(x => [
  exchangeName(x.exchange),
  x.symbol,
  x.name,
  contractName(x.main_contract, x.symbol),
  x.main_change_pct == null ? '-' : `${x.main_change_pct}%`,
  fmtNum(x.total_volume),
  fmtNum(x.total_open_interest),
  qualityValue(x, 'seat_rank'),
  qualityValue(x, 'archive_signal'),
  fmtSigned(x.archive_signal?.netDelta ?? x.archive_net_delta),
  fmtYi(x.external_signals?.capital_flow?.amount),
  fmtPct(x.external_signals?.basis?.basis_rate),
  fmtSigned(x.external_signals?.warehouse_receipt?.increase_number),
  fmtSigned(x.external_signals?.history_holding?.net_total),
]))
const filteredRows = computed(() => {
  const q = keyword.value.trim().toUpperCase()
  return (facts.value.length ? facts.value : data.value.rows || []).filter(x => {
    if (q && !`${x.exchange} ${x.symbol} ${x.name} ${x.main_contract}`.toUpperCase().includes(q)) return false
    if (qualityFilter.value === 'seat_missing' && qualityValue(x, 'seat_rank') !== 'missing') return false
    if (qualityFilter.value === 'archive_missing' && qualityValue(x, 'archive_signal') !== 'missing') return false
    if (qualityFilter.value === 'complete' && (qualityValue(x, 'seat_rank') !== 'ok' || qualityValue(x, 'archive_signal') !== 'ok')) return false
    return true
  })
})

function qualityValue(x, key) {
  return x.quality?.[key] || x[`quality_${key}`] || '-'
}

function fmtYi(v) {
  if (v == null) return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return v
  return `${(n / 100000000).toFixed(2)}亿`
}

function fmtPct(v) {
  if (v == null) return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return v
  return `${n}%`
}

function fmtNum(v) {
  if (v == null) return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return v
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toFixed(0)
}
function fmtSigned(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}` : `${v}` }

async function load() {
  loading.value = true
  try {
    const datasetResp = await api.get('/dataset/varieties/latest')
    data.value = datasetResp.data || { rows: [], summary: {} }
    const date = data.value.trade_date
    const [factsResp, coverageResp, gapsResp, gapAnalysisResp] = await Promise.all([
      api.get(`/dataset/facts/${date}`),
      api.get(`/dataset/coverage/${date}`),
      api.get('/dataset/gaps'),
      api.get(`/dataset/gap-analysis/${date}`),
    ])
    facts.value = factsResp.data || []
    coverage.value = coverageResp.data || []
    gaps.value = gapsResp.data || []
    gapAnalysis.value = gapAnalysisResp.data || { gaps: [] }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:18px; gap:12px; }
.page-title { color:#1a1a2e; }
.muted { color:#888; margin-top:4px; line-height:1.6; }
.kpi-row { display:grid; grid-template-columns: repeat(5, 1fr); gap:16px; margin-bottom:16px; }
.primary { background:#e94560; color:white; border:0; border-radius:10px; padding:10px 16px; font-weight:700; cursor:pointer; }
.primary:disabled { opacity:.6; cursor:wait; }
.notice { margin-bottom:16px; padding:11px 14px; background:#f6f8ff; color:#526184; border:1px solid #e4e9ff; border-radius:10px; }
.filters { display:grid; grid-template-columns: 1fr 180px; gap:8px; margin-bottom:12px; }
.filters input, .filters select { border:1px solid #ddd; border-radius:8px; padding:9px 10px; }
.empty-state { padding:24px; text-align:center; color:#888; background:#fafafa; border-radius:10px; }
.section-note { color:#888; font-size:13px; margin-bottom:10px; }
.detail-note { margin-top:14px; }
.empty-state.small { padding:18px; }
.empty-state.success { color:#15845f; background:#effaf5; border:1px solid #d6f3e5; }
@media (max-width: 900px) { .kpi-row, .filters { grid-template-columns:1fr; } .page-head { flex-direction:column; } }
</style>
